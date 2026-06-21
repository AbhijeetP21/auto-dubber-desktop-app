"""Background processing queue.

Runs jobs serially on a single worker thread (one heavy Whisper model in memory
at a time). Progress and completion callbacks are marshaled back onto the UI
thread via the ``post_to_ui`` function supplied at construction (typically
``lambda fn: root.after(0, fn)``), so widgets are only ever touched from the
main thread.
"""
from __future__ import annotations

import queue as queue_module
import threading
from dataclasses import dataclass
from typing import Callable

from .processor import JobResult, ProcessingJob, process_video

ProgressCallback = Callable[[str, float, str], None]
CompleteCallback = Callable[[JobResult], None]


@dataclass
class _Task:
    job: ProcessingJob
    on_progress: ProgressCallback
    on_complete: CompleteCallback


class ProcessingQueue:
    """Serial, threaded job runner with UI-thread-safe callbacks."""

    def __init__(self, post_to_ui: Callable[[Callable[[], None]], None]) -> None:
        self._post = post_to_ui
        self._queue: queue_module.Queue[_Task] = queue_module.Queue()
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()

    def add_task(
        self,
        job: ProcessingJob,
        on_progress: ProgressCallback,
        on_complete: CompleteCallback,
    ) -> None:
        self._queue.put(_Task(job, on_progress, on_complete))

    def start(self) -> None:
        """Start the worker thread if it isn't already running."""
        if self.is_running():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def stop(self) -> None:
        """Request a stop; the worker exits after the current job finishes."""
        self._stop_event.set()

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                task = self._queue.get(timeout=0.2)
            except queue_module.Empty:
                break  # nothing left to do; let the worker exit (idle)

            def progress_cb(stage: str, frac: float, msg: str, op=task.on_progress) -> None:
                self._post(lambda: op(stage, frac, msg))

            result = process_video(task.job, progress_callback=progress_cb)
            self._post(lambda r=result, oc=task.on_complete: oc(r))
