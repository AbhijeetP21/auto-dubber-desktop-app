"""OpenAI TTS provider (API, higher quality).

Uses the ``tts-1-hd`` model. OpenAI returns MP3, which we convert to WAV via the
bundled FFmpeg so downstream code only ever deals with WAV. Batch synthesis runs
up to 5 requests concurrently with asyncio.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Callable

import soundfile as sf

from utils.cancellation import CancelCheck, check_cancelled
from utils.ffmpeg_utils import get_ffmpeg_path, run_ffmpeg

from .base import MAX_SEGMENT_ATTEMPTS, RETRY_BASE_DELAY_SECONDS, TTSProvider

_MODEL = "tts-1-hd"
_MAX_CONCURRENCY = 5
# Hard API limit on input length; longer text gets a 400. Segments this long
# are Whisper run-ons anyway, so truncation loses nothing intelligible.
_MAX_INPUT_CHARS = 4096


def _mp3_to_wav(mp3_path: Path, wav_path: Path) -> None:
    """Convert MP3 → WAV using the bundled FFmpeg."""
    proc = run_ffmpeg([get_ffmpeg_path(), "-i", str(mp3_path), "-y", str(wav_path)])
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"FFmpeg MP3→WAV conversion failed:\n{stderr}")


def _wav_duration(wav_path: Path) -> float:
    info = sf.info(str(wav_path))
    return float(info.frames) / float(info.samplerate)


class OpenAIProvider(TTSProvider):
    """API-backed TTS using OpenAI's tts-1-hd model."""

    def __init__(self, api_key: str, voice: str = "nova") -> None:
        self._api_key = api_key
        self._voice = voice

    @property
    def provider_id(self) -> str:
        return "openai"

    @property
    def display_name(self) -> str:
        return "OpenAI TTS (API — Better Quality)"

    def is_available(self) -> tuple[bool, str]:
        import importlib.util

        if importlib.util.find_spec("openai") is None:
            return (False, "openai package not installed")
        if not self._api_key:
            return (False, "No OpenAI API key set in settings")
        return (True, "")

    def synthesize(self, text: str, output_wav: Path) -> float:
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            mp3_path = Path(tmp.name)
        try:
            with client.audio.speech.with_streaming_response.create(
                model=_MODEL, voice=self._voice, input=text[:_MAX_INPUT_CHARS]
            ) as response:
                response.stream_to_file(str(mp3_path))
            _mp3_to_wav(mp3_path, output_wav)
        finally:
            mp3_path.unlink(missing_ok=True)
        return _wav_duration(output_wav)

    def synthesize_batch(
        self,
        segments: list[tuple[str, Path]],
        progress_callback: Callable[[int, int], None] | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> list[float]:
        return asyncio.run(
            self._synthesize_batch_async(segments, progress_callback, should_cancel)
        )

    async def _synthesize_batch_async(
        self,
        segments: list[tuple[str, Path]],
        progress_callback: Callable[[int, int], None] | None,
        should_cancel: CancelCheck | None,
    ) -> list[float]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key)
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)
        durations: list[float | None] = [None] * len(segments)
        errors: list[Exception] = []
        done = 0
        total = len(segments)
        lock = asyncio.Lock()

        async def synthesize_one(text: str, out: Path) -> float:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                mp3_path = Path(tmp.name)
            try:
                async with client.audio.speech.with_streaming_response.create(
                    model=_MODEL, voice=self._voice, input=text[:_MAX_INPUT_CHARS]
                ) as response:
                    await response.stream_to_file(str(mp3_path))
                # FFmpeg conversion is blocking; run it off the event loop.
                await asyncio.to_thread(_mp3_to_wav, mp3_path, out)
                return _wav_duration(out)
            finally:
                mp3_path.unlink(missing_ok=True)

        async def worker(idx: int, text: str, out: Path) -> None:
            nonlocal done
            async with sem:
                # Retry transient failures (429s, network blips) per segment;
                # a segment that still fails becomes silence in the pipeline
                # instead of aborting a batch that is mostly paid for and done.
                for attempt in range(MAX_SEGMENT_ATTEMPTS):
                    check_cancelled(should_cancel)
                    try:
                        durations[idx] = await synthesize_one(text, out)
                        break
                    except Exception as exc:  # noqa: BLE001 — retried, then degraded to silence
                        errors.append(exc)
                        if attempt < MAX_SEGMENT_ATTEMPTS - 1:
                            await asyncio.sleep(
                                RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
                            )
            async with lock:
                done += 1
                if progress_callback is not None:
                    progress_callback(done, total)

        await asyncio.gather(
            *(worker(i, text, out) for i, (text, out) in enumerate(segments))
        )
        if segments and all(d is None for d in durations):
            raise RuntimeError(f"TTS failed for every segment: {errors[-1]}")
        return [d if d is not None else 0.0 for d in durations]
