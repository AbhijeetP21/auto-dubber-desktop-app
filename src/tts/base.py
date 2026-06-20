"""Abstract TTS provider interface.

A provider turns English text into a spoken WAV file. The pipeline depends only
on this interface, so providers (Kokoro local, OpenAI API) are interchangeable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable


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
    ) -> list[float]:
        """Synthesize many segments, returning durations in input order.

        Default implementation runs serially. Subclasses that support
        concurrency (e.g. the API provider) may override this.
        """
        durations: list[float] = []
        total = len(segments)
        for i, (text, out) in enumerate(segments):
            durations.append(self.synthesize(text, out))
            if progress_callback is not None:
                progress_callback(i + 1, total)
        return durations
