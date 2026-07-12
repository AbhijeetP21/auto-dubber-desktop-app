"""Assemble the dubbed audio track, fitting each TTS clip to its time window.

Each subtitle segment owns a ``[start, end]`` window. The TTS clip for that
segment is padded with silence (if short) or sped up with FFmpeg's ``atempo``
filter (if long), so it lands exactly in its window. Clips are then mixed into
a preallocated sample buffer at their start offsets — O(total) work and memory,
unlike repeated pydub ``overlay`` which copies the whole track per segment and
made feature-length videos pathologically slow.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable

import numpy as np
import soundfile as sf
from pydub import AudioSegment

from utils.cancellation import CancelCheck, check_cancelled
from utils.ffmpeg_utils import get_ffmpeg_path, run_ffmpeg

from .transcriber import Segment

# Make pydub use the bundled FFmpeg rather than a system one.
AudioSegment.converter = get_ffmpeg_path()

_FADE_OUT_MS = 60
# Output format: Kokoro is natively 24kHz mono; OpenAI TTS decodes to the same.
# The muxer re-encodes to AAC, so there is no benefit to upsampling here.
_SAMPLE_RATE = 24000


def _speedup_ffmpeg(audio: AudioSegment, ratio: float, ffmpeg_path: str) -> AudioSegment:
    """Speed audio up by ``ratio`` using FFmpeg's atempo filter.

    atempo accepts 0.5–2.0 per instance, so ratios above 2.0 are split across two
    chained filters (sqrt each). Ratios above 4.0 are unreachable: settings clamp
    ``max_stretch_ratio`` to [1.0, 4.0].
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as inp:
        audio.export(inp.name, format="wav")
        inp_path = inp.name
    out_path = inp_path.replace(".wav", "_fast.wav")

    if ratio <= 2.0:
        atempo_filter = f"atempo={ratio:.4f}"
    else:
        r1 = ratio ** 0.5
        atempo_filter = f"atempo={r1:.4f},atempo={r1:.4f}"

    try:
        proc = run_ffmpeg(
            [ffmpeg_path, "-i", inp_path, "-filter:a", atempo_filter, "-y", out_path]
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace")[-500:]
            raise RuntimeError(
                f"FFmpeg atempo (ratio {ratio:.2f}) failed:\n{stderr}"
            )
        result = AudioSegment.from_wav(out_path)
    finally:
        for p in (inp_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass
    return result


def _fit_segment(
    tts_audio: AudioSegment,
    window_ms: int,
    max_stretch_ratio: float,
    ffmpeg_path: str,
) -> AudioSegment:
    """Return ``tts_audio`` resized to exactly ``window_ms`` milliseconds."""
    tts_ms = len(tts_audio)

    if tts_ms <= window_ms:
        return tts_audio + AudioSegment.silent(duration=window_ms - tts_ms)

    ratio = tts_ms / window_ms
    if ratio <= max_stretch_ratio:
        fitted = _speedup_ffmpeg(tts_audio, ratio, ffmpeg_path)
    else:
        # Speed up as much as we allow, then hard-truncate the overflow with a
        # short fade so the cut isn't jarring.
        fitted = _speedup_ffmpeg(tts_audio, max_stretch_ratio, ffmpeg_path)
        if len(fitted) > window_ms:
            # Fade can't exceed the clip length (windows shorter than the
            # fade would otherwise fail or go fully silent).
            fitted = fitted[:window_ms].fade_out(min(_FADE_OUT_MS, window_ms))

    # Normalize to exact window length (atempo output can be off by a few ms).
    if len(fitted) > window_ms:
        fitted = fitted[:window_ms]
    elif len(fitted) < window_ms:
        fitted = fitted + AudioSegment.silent(duration=window_ms - len(fitted))
    return fitted


def _to_samples(clip: AudioSegment) -> np.ndarray:
    """Convert a pydub clip to int16 mono samples at the track sample rate."""
    clip = clip.set_frame_rate(_SAMPLE_RATE).set_channels(1).set_sample_width(2)
    return np.frombuffer(clip.raw_data, dtype=np.int16)


def build_dubbed_track(
    segments: list[Segment],
    tts_wav_paths: list[Path],
    total_duration_seconds: float,
    output_wav: Path,
    max_stretch_ratio: float = 1.35,
    progress_callback: Callable[[float], None] | None = None,
    should_cancel: CancelCheck | None = None,
) -> None:
    """Build a full-length dubbed WAV from per-segment TTS clips.

    Args:
        segments: subtitle segments (provide the time windows).
        tts_wav_paths: one WAV per segment, in the same order.
        total_duration_seconds: length of the source video.
        output_wav: destination (24kHz mono WAV; the muxer re-encodes to AAC).
        max_stretch_ratio: max speed-up before truncating overflow.
        progress_callback: called with 0.0–1.0 as segments are placed.
        should_cancel: raises :class:`JobCancelled` mid-build when it reports True.
    """
    if len(segments) != len(tts_wav_paths):
        raise ValueError(
            f"segments ({len(segments)}) and tts_wav_paths "
            f"({len(tts_wav_paths)}) length mismatch"
        )

    ffmpeg_path = get_ffmpeg_path()
    total_frames = int(round(total_duration_seconds * _SAMPLE_RATE))
    # int32 accumulator so overlapping segments mix without wrapping; clipped
    # back to int16 at the end.
    track = np.zeros(max(total_frames, 1), dtype=np.int32)

    total = len(segments)
    for idx, (seg, wav_path) in enumerate(zip(segments, tts_wav_paths)):
        check_cancelled(should_cancel)
        window_ms = int(round((seg.end - seg.start) * 1000))
        if window_ms <= 0:
            continue
        tts_audio = AudioSegment.from_wav(str(wav_path))
        fitted = _fit_segment(tts_audio, window_ms, max_stretch_ratio, ffmpeg_path)
        samples = _to_samples(fitted).astype(np.int32)

        start = int(round(seg.start * _SAMPLE_RATE))
        if start >= total_frames:
            continue  # segment starts past the end of the source audio
        end = min(start + len(samples), total_frames)
        track[start:end] += samples[: end - start]
        if progress_callback is not None:
            progress_callback((idx + 1) / total)

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    final = np.clip(track, -32768, 32767).astype(np.int16)
    sf.write(str(output_wav), final, _SAMPLE_RATE, subtype="PCM_16")
