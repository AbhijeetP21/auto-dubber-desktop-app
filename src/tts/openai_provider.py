"""OpenAI TTS provider (API, higher quality).

Uses the ``tts-1-hd`` model. OpenAI returns MP3, which we convert to WAV via the
bundled FFmpeg so downstream code only ever deals with WAV. Batch synthesis runs
up to 5 requests concurrently with asyncio.
"""
from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import soundfile as sf

from utils.ffmpeg_utils import get_ffmpeg_path

from .base import TTSProvider

_MODEL = "tts-1-hd"
_MAX_CONCURRENCY = 5


def _mp3_to_wav(mp3_path: Path, wav_path: Path) -> None:
    """Convert MP3 → WAV using the bundled FFmpeg."""
    proc = subprocess.run(
        [get_ffmpeg_path(), "-i", str(mp3_path), "-y", str(wav_path)],
        capture_output=True,
    )
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
        try:
            import openai  # noqa: F401
        except ImportError:
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
                model=_MODEL, voice=self._voice, input=text
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
    ) -> list[float]:
        return asyncio.run(self._synthesize_batch_async(segments, progress_callback))

    async def _synthesize_batch_async(
        self,
        segments: list[tuple[str, Path]],
        progress_callback: Callable[[int, int], None] | None,
    ) -> list[float]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._api_key)
        sem = asyncio.Semaphore(_MAX_CONCURRENCY)
        durations: list[float | None] = [None] * len(segments)
        done = 0
        total = len(segments)
        lock = asyncio.Lock()

        async def worker(idx: int, text: str, out: Path) -> None:
            nonlocal done
            async with sem:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    mp3_path = Path(tmp.name)
                try:
                    async with client.audio.speech.with_streaming_response.create(
                        model=_MODEL, voice=self._voice, input=text
                    ) as response:
                        await response.stream_to_file(str(mp3_path))
                    # FFmpeg conversion is blocking; run it off the event loop.
                    await asyncio.to_thread(_mp3_to_wav, mp3_path, out)
                    durations[idx] = _wav_duration(out)
                finally:
                    mp3_path.unlink(missing_ok=True)
            async with lock:
                done += 1
                if progress_callback is not None:
                    progress_callback(done, total)

        await asyncio.gather(
            *(worker(i, text, out) for i, (text, out) in enumerate(segments))
        )
        return [d if d is not None else 0.0 for d in durations]
