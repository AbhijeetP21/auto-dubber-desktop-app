"""FFmpeg binary resolution.

Always resolve the FFmpeg binary from the bundled ``imageio-ffmpeg`` package so
the pipeline never depends on a system-installed ``ffmpeg`` being on PATH. This
matters both for development consistency and for the packaged app, where no
system FFmpeg is guaranteed to exist.
"""
from __future__ import annotations

import functools
import subprocess
import sys
import threading
from pathlib import Path

# Pass as ``creationflags`` to every FFmpeg subprocess: in the windowed
# (no-console) frozen app on Windows, each spawn would otherwise flash a
# black console window. No-op on other platforms.
SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Every live FFmpeg child spawned via run_ffmpeg(), so the app can kill them
# on cancel or window close instead of orphaning them mid-encode.
_active_procs: set[subprocess.Popen] = set()
_active_lock = threading.Lock()


def run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run an FFmpeg command with output captured, tracking the live process.

    Behaves like ``subprocess.run(cmd, capture_output=True)`` but registers the
    child so :func:`terminate_active_ffmpeg` can kill it from another thread.
    ``-nostdin`` is prepended so ffmpeg never eats console input in CLI use.
    """
    full_cmd = [cmd[0], "-nostdin", *cmd[1:]]
    proc = subprocess.Popen(
        full_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        creationflags=SUBPROCESS_FLAGS,
    )
    with _active_lock:
        _active_procs.add(proc)
    try:
        stdout, stderr = proc.communicate()
    finally:
        with _active_lock:
            _active_procs.discard(proc)
    return subprocess.CompletedProcess(full_cmd, proc.returncode, stdout, stderr)


def terminate_active_ffmpeg() -> None:
    """Kill every FFmpeg child currently running (used on cancel/app close)."""
    with _active_lock:
        procs = list(_active_procs)
    for proc in procs:
        try:
            proc.kill()
        except OSError:
            pass


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

    Raises ``ValueError`` if FFmpeg cannot open the file at all (missing or
    corrupt input), so that case isn't misreported as "no audio stream".
    """
    proc = run_ffmpeg([get_ffmpeg_path(), "-i", str(video_path), "-hide_banner"])
    stderr = proc.stderr.decode("utf-8", errors="replace")
    if not any("Input #" in line for line in stderr.splitlines()):
        raise ValueError(
            f"Could not read {video_path.name} — the file may be missing or "
            f"corrupt:\n{stderr[-300:]}"
        )
    return any(
        "Stream #" in line and "Audio:" in line for line in stderr.splitlines()
    )
