"""Extract a video's audio to 16kHz mono WAV (what faster-whisper expects)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from utils.ffmpeg_utils import get_ffmpeg_path, has_audio_stream


def extract_audio(video_path: Path, output_wav: Path) -> None:
    """Extract the first audio stream of ``video_path`` to ``output_wav``.

    Produces 16kHz mono signed-16-bit PCM. Raises ``ValueError`` if the source
    has no audio stream, or ``RuntimeError`` with captured stderr if FFmpeg
    exits non-zero.
    """
    if not has_audio_stream(video_path):
        raise ValueError(f"No audio stream found in {video_path.name}")

    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        get_ffmpeg_path(),
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-y", str(output_wav),
    ]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(
            f"Audio extraction failed for {video_path.name} (FFmpeg exit "
            f"{proc.returncode}):\n{stderr}"
        )
