"""Background processing queue.

Runs jobs serially on a single worker thread (one heavy Whisper model in memory
at a time). Progress and completion callbacks are marshaled back onto the UI
thread via the ``post_to_ui`` function supplied at construction (typically
``lambda fn: root.after(0, fn)``), so widgets are only ever touched from the
main thread.

Every task carries a cancel :class:`threading.Event`. Setting it before the
task starts skips it entirely; setting it mid-job aborts the job at the next
pipeline checkpoint. Either way the task's completion callback always fires
(with ``cancelled=True``), so callers can rely on one completion per task.
"""
from __future__ import annotations

import queue as queue_module
import threading
from dataclasses import dataclass, field
from typing import Callable

from .processor import JobResult, ProcessingJob, process_video

ProgressCallback = Callable[[str, float, str], None]
CompleteCallback = Callable[[JobResult], None]


def _cancelled_result() -> JobResult:
    return JobResult(
        success=False,
        output_path=None,
        detected_language=None,
        error="Cancelled",
        duration_seconds=0.0,
        cancelled=True,
    )


@dataclass
class _Task:
    job: ProcessingJob
    on_progress: ProgressCallback
    on_complete: CompleteCallback
    cancel_event: threading.Event = field(default_factory=threading.Event)


class ProcessingQueue:
    """Serial, threaded job runner with UI-thread-safe callbacks."""

    def __init__(self, post_to_ui: Callable[[Callable[[], None]], None]) -> None:
        self._post = post_to_ui
        self._queue: queue_module.Queue[_Task] = queue_module.Queue()
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        # Guards every worker lifecycle decision (spawn, idle-exit, stop-exit),
        # so a task is never stranded between an exiting worker and a start()
        # that saw the old worker as still alive.
        self._lock = threading.Lock()

    def add_task(
        self,
        job: ProcessingJob,
        on_progress: ProgressCallback,
        on_complete: CompleteCallback,
    ) -> threading.Event:
        """Enqueue a job. Returns its cancel event.

        Set the event to cancel the task: before it starts it is skipped, and
        mid-job the pipeline aborts at its next checkpoint. The completion
        callback fires either way.
        """
        task = _Task(job, on_progress, on_complete)
        self._queue.put(task)
        return task.cancel_event

    def start(self) -> None:
        """Start the worker thread, or un-stop a live one."""
        with self._lock:
            self._stop_event.clear()
            if self.is_running():
                return
            self._worker = threading.Thread(target=self._run, daemon=True)
            self._worker.start()

    def stop(self) -> None:
        """Request a stop; the worker exits after the current job finishes.

        Queued tasks stay queued and are picked up by the next ``start()``.
        """
        self._stop_event.set()

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _run(self) -> None:
        while True:
            # All exit decisions happen under the lock and clear self._worker,
            # so start() can never observe a worker that is about to die and
            # skip spawning a replacement (which would strand queued tasks).
            with self._lock:
                if self._stop_event.is_set():
                    self._worker = None
                    return
            try:
                task = self._queue.get(timeout=0.2)
            except queue_module.Empty:
                with self._lock:
                    if self._queue.empty():
                        self._worker = None
                        return
                continue

            if task.cancel_event.is_set():
                self._post(lambda oc=task.on_complete: oc(_cancelled_result()))
                continue

            def progress_cb(stage: str, frac: float, msg: str, op=task.on_progress) -> None:
                self._post(lambda: op(stage, frac, msg))

            result = process_video(
                task.job,
                progress_callback=progress_cb,
                should_cancel=task.cancel_event.is_set,
            )
            self._post(lambda r=result, oc=task.on_complete: oc(r))
