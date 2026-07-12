"""Abstract TTS provider interface.

A provider turns English text into a spoken WAV file. The pipeline depends only
on this interface, so providers (Kokoro local, OpenAI API) are interchangeable.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from utils.cancellation import CancelCheck, check_cancelled

# Per-segment retry policy shared by providers: transient failures (network
# blips, rate limits) must not abort a long batch that is mostly done.
MAX_SEGMENT_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0


class TTSProvider(ABC):

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique string identifier: 'kokoro' or 'openai'."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for the UI."""

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Return ``(is_ready, reason_if_not)``.

        Check that model files are present / the API key is set. ``reason`` is a
        short user-facing message and is empty when ready.
        """

    @abstractmethod
    def synthesize(self, text: str, output_wav: Path) -> float:
        """Synthesize English speech for ``text`` and write it to ``output_wav``.

        Returns the duration of the synthesized audio in seconds.
        """

    def synthesize_batch(
        self,
        segments: list[tuple[str, Path]],
        progress_callback: Callable[[int, int], None] | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> list[float]:
        """Synthesize many segments, returning durations in input order.

        Default implementation runs serially with per-segment retries. A
        segment that still fails after all attempts yields duration 0.0 (the
        pipeline fills its window with silence) rather than aborting the whole
        batch; if *every* segment fails, the batch raises. Subclasses that
        support concurrency (e.g. the API provider) may override this.
        """
        durations: list[float] = []
        total = len(segments)
        last_error: Exception | None = None
        for i, (text, out) in enumerate(segments):
            check_cancelled(should_cancel)
            duration = 0.0
            for attempt in range(MAX_SEGMENT_ATTEMPTS):
                try:
                    duration = self.synthesize(text, out)
                    break
                except Exception as exc:  # noqa: BLE001 — retried, then degraded to silence
                    last_error = exc
                    if attempt < MAX_SEGMENT_ATTEMPTS - 1:
                        check_cancelled(should_cancel)
                        time.sleep(RETRY_BASE_DELAY_SECONDS * (2 ** attempt))
            durations.append(duration)
            if progress_callback is not None:
                progress_callback(i + 1, total)
        if segments and last_error is not None and all(d <= 0.0 for d in durations):
            raise RuntimeError(f"TTS failed for every segment: {last_error}")
        return durations
