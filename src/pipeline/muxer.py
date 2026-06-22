"""Mux video + original audio + English dub + subtitles into a multi-track MKV."""
from __future__ import annotations

import subprocess
from pathlib import Path

from utils.ffmpeg_utils import get_ffmpeg_path, has_audio_stream


def mux_output(
    video_path: Path,
    dubbed_audio_path: Path,
    subtitle_path: Path,
    output_path: Path,
    original_lang_code: str = "und",
    ffmpeg_path: str | None = None,
) -> None:
    """Mux the output MKV.

    Track layout:
      - video: copied (no re-encode)
      - audio 0: original, copied, not default
      - audio 1: English dub, AAC 192k, marked default (plays first)
      - subtitle 0: English ASS, marked default (shown by default)

    Raises ``ValueError`` if the source has no audio, ``RuntimeError`` on FFmpeg
    failure (with captured stderr).
    """
    if ffmpeg_path is None:
        ffmpeg_path = get_ffmpeg_path()

    if not has_audio_stream(video_path):
        raise ValueError(f"No audio stream found in {video_path.name}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        ffmpeg_path,
        # AVI (and some other containers) lack presentation timestamps; copying
        # their video into Matroska fails with "unknown timestamp" unless we
        # synthesize PTS. Harmless for formats that already carry timestamps.
        "-fflags", "+genpts",
        "-i", str(video_path),
        "-i", str(dubbed_audio_path),
        "-i", str(subtitle_path),
        "-map", "0:v:0",
        "-map", "0:a:0",
        "-map", "1:a:0",
        "-map", "2:0",
        "-c:v", "copy",
        "-c:a:0", "copy",
        "-c:a:1", "aac", "-b:a:1", "192k",
        "-c:s", "ass",
        "-metadata:s:a:0", "title=Original Audio",
        "-metadata:s:a:0", f"language={original_lang_code}",
        "-metadata:s:a:1", "title=English Dub",
        "-metadata:s:a:1", "language=eng",
        "-metadata:s:s:0", "title=English Subtitles",
        "-metadata:s:s:0", "language=eng",
        "-disposition:a:0", "0",
        "-disposition:a:1", "default",
        "-disposition:s:0", "default",
        "-y", str(output_path),
    ]

    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(
            f"Muxing failed (FFmpeg exit {proc.returncode}):\n{stderr}"
        )
