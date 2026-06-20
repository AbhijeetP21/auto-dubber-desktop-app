"""Managed per-job temporary directory.

Intermediate artifacts (extracted WAV, per-segment TTS WAVs, the assembled dub
track, the ASS file) live in a single temp directory per job. On success the
caller cleans it up; on error it is preserved so the failure can be inspected,
and the path is surfaced in the error message.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


class JobTempDir:
    """A throwaway directory for one processing job.

    Use as a context manager. By default the directory is removed on exit; call
    :meth:`keep` to preserve it (done automatically on error by the pipeline).
    """

    def __init__(self, prefix: str = "autodubber_") -> None:
        self.path = Path(tempfile.mkdtemp(prefix=prefix))
        self._keep = False

    def keep(self) -> None:
        """Preserve the directory instead of deleting it on exit."""
        self._keep = True

    def file(self, name: str) -> Path:
        """Return a path for ``name`` inside this temp directory."""
        return self.path / name

    def cleanup(self) -> None:
        """Remove the directory tree unless :meth:`keep` was called."""
        if not self._keep:
            shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self) -> "JobTempDir":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            # Preserve on error for debugging.
            self.keep()
        self.cleanup()
