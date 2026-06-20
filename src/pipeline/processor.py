"""Orchestrate the full dubbing pipeline for a single video file."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import soundfile as sf

from config.settings import AppSettings
from tts.base import TTSProvider
from utils.temp_dir import JobTempDir

from .audio_extractor import extract_audio
from .audio_syncer import build_dubbed_track
from .muxer import mux_output
from .subtitle_writer import write_ass
from .transcriber import transcribe

ProgressCallback = Callable[[str, float, str], None]


@dataclass
class ProcessingJob:
    input_path: Path
    output_dir: Path | None        # None = same directory as input
    language_hint: str | None      # ISO 639-1 code or None
    tts_provider: TTSProvider
    settings: AppSettings


@dataclass
class JobResult:
    success: bool
    output_path: Path | None
    detected_language: str | None
    error: str | None
    duration_seconds: float
    warnings: list[str] | None = None


def _report(cb: ProgressCallback | None, stage: str, progress: float, message: str) -> None:
    # The callback belongs to the display layer (CLI/UI). A misbehaving callback
    # (e.g. a console encoding error) must never corrupt the pipeline result.
    if cb is not None:
        try:
            cb(stage, progress, message)
        except Exception:
            pass


def _scaled(lo: float, hi: float, frac: float) -> float:
    """Map a 0–1 sub-stage fraction into the [lo, hi] overall-progress band."""
    return lo + (hi - lo) * max(0.0, min(frac, 1.0))


def process_video(
    job: ProcessingJob,
    progress_callback: ProgressCallback | None = None,
) -> JobResult:
    """Run extract → transcribe → subtitles → TTS → sync → mux for one video."""
    start_time = time.monotonic()
    warnings: list[str] = []
    tmp = JobTempDir()

    try:
        # 1. Extract audio --------------------------------------------------
        _report(progress_callback, "extracting", 0.0, "Extracting audio...")
        wav_path = tmp.file("audio.wav")
        extract_audio(job.input_path, wav_path)
        _report(progress_callback, "extracting", 0.15, "Extracting audio...")

        # Source duration drives the length of the dubbed track.
        info = sf.info(str(wav_path))
        total_duration = float(info.frames) / float(info.samplerate)

        # 2. Transcribe + translate ----------------------------------------
        def transcribe_progress(frac: float) -> None:
            _report(
                progress_callback,
                "transcribing",
                _scaled(0.15, 0.45, frac),
                "Transcribing and translating...",
            )

        result = transcribe(
            wav_path,
            language_hint=job.language_hint,
            model_size=job.settings.whisper_model,
            progress_callback=transcribe_progress,
        )
        lang = result.detected_language
        _report(
            progress_callback,
            "transcribing",
            0.45,
            f"Transcribing and translating [{lang}]...",
        )

        if not result.segments:
            raise RuntimeError(
                "No speech segments were transcribed (the audio may be silent "
                "or music-only)."
            )

        # 3. Write subtitles ------------------------------------------------
        _report(progress_callback, "writing_subtitles", 0.45, "Writing subtitles...")
        ass_path = tmp.file("subtitles.ass")
        write_ass(
            result.segments,
            ass_path,
            font_name=job.settings.subtitle_font,
            font_size=job.settings.subtitle_font_size,
        )
        _report(progress_callback, "writing_subtitles", 0.50, "Writing subtitles...")

        # 4. Synthesize TTS per segment ------------------------------------
        total_segs = len(result.segments)
        tts_paths: list[Path] = [
            tmp.file(f"tts_{i:05d}.wav") for i in range(total_segs)
        ]
        batch = [(seg.text, tts_paths[i]) for i, seg in enumerate(result.segments)]

        def tts_progress(done: int, total: int) -> None:
            _report(
                progress_callback,
                "synthesizing",
                _scaled(0.50, 0.80, done / total if total else 1.0),
                f"Synthesizing English dub ({done}/{total} segments)...",
            )

        durations = job.tts_provider.synthesize_batch(batch, tts_progress)

        # Edge case: a segment whose TTS failed/produced nothing → fill with
        # silence of the window length so the track stays aligned.
        for i, (seg, dur) in enumerate(zip(result.segments, durations)):
            if not tts_paths[i].exists() or dur <= 0.0:
                window_s = max(seg.end - seg.start, 0.05)
                _write_silence(tts_paths[i], window_s)
                warnings.append(f"Segment {i} TTS empty; filled with silence.")

        # 5. Build the dubbed track ----------------------------------------
        _report(progress_callback, "syncing", 0.80, "Syncing audio timing...")
        dub_path = tmp.file("dub.wav")
        build_dubbed_track(
            result.segments,
            tts_paths,
            total_duration,
            dub_path,
            max_stretch_ratio=job.settings.max_stretch_ratio,
        )
        _report(progress_callback, "syncing", 0.88, "Syncing audio timing...")

        # 6. Mux ------------------------------------------------------------
        _report(progress_callback, "muxing", 0.88, "Muxing output file...")
        out_dir = job.output_dir or job.input_path.parent
        output_path = out_dir / f"{job.input_path.stem}_dubbed.mkv"
        mux_output(
            job.input_path,
            dub_path,
            ass_path,
            output_path,
            original_lang_code=result.detected_language_code,
        )
        _report(progress_callback, "muxing", 0.98, "Muxing output file...")

        # 7. Done -----------------------------------------------------------
        _report(progress_callback, "done", 1.0, f"Done → {output_path}")
        tmp.cleanup()
        return JobResult(
            success=True,
            output_path=output_path,
            detected_language=lang,
            error=None,
            duration_seconds=time.monotonic() - start_time,
            warnings=warnings or None,
        )

    except Exception as exc:  # noqa: BLE001 — surface any failure as a JobResult
        tmp.keep()  # preserve intermediates for debugging
        error_msg = f"{exc}\n(Temp files preserved at: {tmp.path})"
        _report(progress_callback, "error", 1.0, str(exc))
        return JobResult(
            success=False,
            output_path=None,
            detected_language=None,
            error=error_msg,
            duration_seconds=time.monotonic() - start_time,
            warnings=warnings or None,
        )


def _write_silence(path: Path, duration_seconds: float) -> None:
    """Write a mono 24kHz silent WAV of the given duration."""
    import numpy as np

    sample_rate = 24000
    frames = int(duration_seconds * sample_rate)
    sf.write(str(path), np.zeros(frames, dtype="float32"), sample_rate)
