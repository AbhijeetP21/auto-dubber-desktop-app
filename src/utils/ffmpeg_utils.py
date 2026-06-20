"""FFmpeg binary resolution.

Always resolve the FFmpeg binary from the bundled ``imageio-ffmpeg`` package so
the pipeline never depends on a system-installed ``ffmpeg`` being on PATH. This
matters both for development consistency and for the packaged app, where no
system FFmpeg is guaranteed to exist.
"""
from __future__ import annotations

import functools
import subprocess
from pathlib import Path


@functools.lru_cache(maxsize=1)
def get_ffmpeg_path() -> str:
    """Return the absolute path to the bundled FFmpeg binary.

    Uses ``imageio_ffmpeg.get_ffmpeg_exe()`` (the supported public API; the
    older ``imageio.plugins.ffmpeg.get_exe`` simply delegates to this). The
    result is cached for the process lifetime.
    """
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def has_audio_stream(video_path: Path) -> bool:
    """Return True if ``video_path`` contains at least one audio stream.

    imageio-ffmpeg ships ``ffmpeg`` but not ``ffprobe``, so we inspect FFmpeg's
    stream report (printed to stderr) from a no-output probe run. The non-zero
    exit code from "no output specified" is expected and ignored.
    """
    proc = subprocess.run(
        [get_ffmpeg_path(), "-i", str(video_path), "-hide_banner"],
        capture_output=True,
    )
    stderr = proc.stderr.decode("utf-8", errors="replace")
    return any(
        "Stream #" in line and "Audio:" in line for line in stderr.splitlines()
    )
