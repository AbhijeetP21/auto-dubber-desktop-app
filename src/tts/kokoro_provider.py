"""Kokoro local TTS provider (ONNX, CPU-friendly).

``kokoro-onnx`` needs two model files at runtime: the ONNX model and a voices
pack. We cache them under ``~/.cache/auto-dubber/kokoro/`` and download them on
first use if missing, so the rest of the app can treat synthesis as a simple
call.
"""
from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Callable

import soundfile as sf

from .base import TTSProvider

# Official model-file release assets for kokoro-onnx v1.0.
_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
_VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

_CACHE_DIR = Path.home() / ".cache" / "auto-dubber" / "kokoro"
_MODEL_PATH = _CACHE_DIR / "kokoro-v1.0.onnx"
_VOICES_PATH = _CACHE_DIR / "voices-v1.0.bin"

# Kokoro emits 24kHz audio.
_SAMPLE_RATE = 24000


class DownloadCancelled(Exception):
    """Raised when a model download is cancelled mid-flight."""


def _download(
    url: str,
    dest: Path,
    progress_callback: Callable[[float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    """Download ``url`` to ``dest`` atomically, reporting fractional progress.

    If ``should_cancel`` returns True mid-download, the partial file is removed
    and :class:`DownloadCancelled` is raised.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url) as resp:  # noqa: S310 (trusted GitHub release URL)
            total = int(resp.headers.get("Content-Length", 0))
            read = 0
            with open(tmp, "wb") as f:
                while True:
                    if should_cancel is not None and should_cancel():
                        raise DownloadCancelled()
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    read += len(chunk)
                    if progress_callback is not None and total:
                        progress_callback(read / total)
        tmp.replace(dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def ensure_model_files(
    progress_callback: Callable[[str, float], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> None:
    """Download Kokoro model files if not already cached.

    ``progress_callback(filename, fraction)`` is invoked during downloads.
    Raises :class:`DownloadCancelled` if ``should_cancel`` signals a stop.
    """
    for url, dest in ((_MODEL_URL, _MODEL_PATH), (_VOICES_URL, _VOICES_PATH)):
        if dest.exists():
            continue
        cb = (lambda frac, name=dest.name: progress_callback(name, frac)) if progress_callback else None
        _download(url, dest, cb, should_cancel)


def model_files_present() -> bool:
    return _MODEL_PATH.exists() and _VOICES_PATH.exists()


class KokoroProvider(TTSProvider):
    """Local, free TTS using kokoro-onnx."""

    def __init__(self, voice: str = "af_heart", lang: str = "en-us") -> None:
        self._voice = voice
        self._lang = lang
        self._kokoro = None  # lazy-loaded

    @property
    def provider_id(self) -> str:
        return "kokoro"

    @property
    def display_name(self) -> str:
        return "Kokoro (Local — Free)"

    def is_available(self) -> tuple[bool, str]:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return (False, "kokoro-onnx package not installed")
        if not model_files_present():
            return (False, "Model not downloaded yet")
        return (True, "")

    def _ensure_loaded(self) -> None:
        if self._kokoro is not None:
            return
        ensure_model_files()
        from kokoro_onnx import Kokoro

        self._kokoro = Kokoro(str(_MODEL_PATH), str(_VOICES_PATH))

    def synthesize(self, text: str, output_wav: Path) -> float:
        self._ensure_loaded()
        samples, sample_rate = self._kokoro.create(
            text, voice=self._voice, speed=1.0, lang=self._lang
        )
        sf.write(str(output_wav), samples, sample_rate)
        return float(len(samples)) / float(sample_rate)
