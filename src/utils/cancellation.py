"""Cooperative job cancellation.

``JobCancelled`` is raised at pipeline checkpoints when a job's cancel flag is
set. It lives in utils (not pipeline) so the TTS layer can raise it without
importing pipeline code.
"""
from __future__ import annotations

from typing import Callable

CancelCheck = Callable[[], bool]


class JobCancelled(Exception):
    """Raised when a job is cancelled mid-flight."""


def check_cancelled(should_cancel: CancelCheck | None) -> None:
    """Raise :class:`JobCancelled` if ``should_cancel`` reports True."""
    if should_cancel is not None and should_cancel():
        raise JobCancelled()
