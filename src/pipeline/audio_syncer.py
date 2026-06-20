"""Assemble the dubbed audio track, fitting each TTS clip to its time window.

Each subtitle segment owns a ``[start, end]`` window. The TTS clip for that
segment is padded with silence (if short) or sped up with FFmpeg's ``atempo``
filter (if long), so it lands exactly in its window. Clips are then overlaid
onto a full-length silent track at their start offsets.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from pydub import AudioSegment

from utils.ffmpeg_utils import get_ffmpeg_path

from .transcriber import Segment

# Make pydub use the bundled FFmpeg rather than a system one.
AudioSegment.converter = get_ffmpeg_path()

_FADE_OUT_MS = 60


def _speedup_ffmpeg(audio: AudioSegment, ratio: float, ffmpeg_path: str) -> AudioSegment:
    """Speed audio up by ``ratio`` using FFmpeg's atempo filter.

    atempo accepts 0.5–2.0 per instance, so ratios above 2.0 are split across two
    chained filters (sqrt each).
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
        subprocess.run(
            [ffmpeg_path, "-i", inp_path, "-filter:a", atempo_filter, "-y", out_path],
            check=True,
            capture_output=True,
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
            fitted = fitted[:window_ms].fade_out(_FADE_OUT_MS)

    # Normalize to exact window length (atempo output can be off by a few ms).
    if len(fitted) > window_ms:
        fitted = fitted[:window_ms]
    elif len(fitted) < window_ms:
        fitted = fitted + AudioSegment.silent(duration=window_ms - len(fitted))
    return fitted


def build_dubbed_track(
    segments: list[Segment],
    tts_wav_paths: list[Path],
    total_duration_seconds: float,
    output_wav: Path,
    max_stretch_ratio: float = 1.35,
) -> None:
    """Build a full-length dubbed WAV from per-segment TTS clips.

    Args:
        segments: subtitle segments (provide the time windows).
        tts_wav_paths: one WAV per segment, in the same order.
        total_duration_seconds: length of the source video.
        output_wav: destination (44.1kHz stereo WAV).
        max_stretch_ratio: max speed-up before truncating overflow.
    """
    if len(segments) != len(tts_wav_paths):
        raise ValueError(
            f"segments ({len(segments)}) and tts_wav_paths "
            f"({len(tts_wav_paths)}) length mismatch"
        )

    ffmpeg_path = get_ffmpeg_path()
    total_ms = int(round(total_duration_seconds * 1000))
    full_track = AudioSegment.silent(duration=total_ms)

    for seg, wav_path in zip(segments, tts_wav_paths):
        tts_audio = AudioSegment.from_wav(str(wav_path))
        window_ms = int(round((seg.end - seg.start) * 1000))
        if window_ms <= 0:
            continue
        fitted = _fit_segment(tts_audio, window_ms, max_stretch_ratio, ffmpeg_path)
        position_ms = int(round(seg.start * 1000))
        full_track = full_track.overlay(fitted, position=position_ms)

    full_track = full_track.set_frame_rate(44100).set_channels(2)
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    full_track.export(str(output_wav), format="wav")
