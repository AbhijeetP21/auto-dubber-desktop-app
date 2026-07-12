"""Kokoro local TTS provider (ONNX, CPU-friendly).

``kokoro-onnx`` needs two model files at runtime: the ONNX model and a voices
pack. We cache them under ``~/.cache/auto-dubber/kokoro/`` and download them on
first use if missing, so the rest of the app can treat synthesis as a simple
call.
"""
from __future__ import annotations

import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

import soundfile as sf

from .base import TTSProvider

# Network robustness: a stalled connection must error out (and be retried/
# resumed) rather than hang forever — the original bug was an untimed urlopen
# that blocked indefinitely after a dropped connection (e.g. laptop sleep).
_TIMEOUT_SECONDS = 30
_MAX_ATTEMPTS = 4

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
    """Download ``url`` to ``dest`` robustly.

    - Uses a socket timeout so a stalled connection raises instead of hanging.
    - Resumes from a partial ``.part`` file via an HTTP Range request, retrying
      transient network errors up to ``_MAX_ATTEMPTS`` times.
    - Reports fractional progress via ``progress_callback``.
    - Raises :class:`DownloadCancelled` (and discards the partial) if
      ``should_cancel`` signals a stop; raises ``RuntimeError`` if all attempts
      fail (the partial is kept so a later run can resume).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_error: Exception | None = None

    for _attempt in range(_MAX_ATTEMPTS):
        if should_cancel is not None and should_cancel():
            tmp.unlink(missing_ok=True)
            raise DownloadCancelled()

        resume_from = tmp.stat().st_size if tmp.exists() else 0
        req = urllib.request.Request(url)
        if resume_from:
            req.add_header("Range", f"bytes={resume_from}-")

        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:  # noqa: S310 (trusted GitHub release URL)
                length = int(resp.headers.get("Content-Length", 0))
                if getattr(resp, "status", 200) == 206:
                    total = resume_from + length            # partial content
                    mode = "ab"
                else:
                    total, resume_from, mode = length, 0, "wb"  # server sent full file

                read = resume_from
                cancelled = False
                with open(tmp, mode) as f:
                    while True:
                        if should_cancel is not None and should_cancel():
                            cancelled = True
                            break
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        read += len(chunk)
                        if progress_callback is not None and total:
                            progress_callback(min(read / total, 1.0))
                if cancelled:
                    # Unlink only after the file handle is closed — deleting an
                    # open file raises a sharing violation on Windows, which
                    # would masquerade as a network error and eat the cancel.
                    tmp.unlink(missing_ok=True)
                    raise DownloadCancelled()

            # Stream ended; verify completeness before committing.
            if total and tmp.stat().st_size < total:
                last_error = IOError(
                    f"incomplete download ({tmp.stat().st_size}/{total} bytes)"
                )
                continue  # resume on next attempt
            tmp.replace(dest)
            return
        except DownloadCancelled:
            raise
        except urllib.error.HTTPError as exc:
            # 416 = our Range start is at/past the file's end (e.g. a fully
            # downloaded .part that was never promoted). Resuming can never
            # succeed, so discard the partial and retry from scratch.
            if exc.code == 416:
                tmp.unlink(missing_ok=True)
            last_error = exc
            continue
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc  # keep .part for resume, then retry
            continue

    raise RuntimeError(
        f"Download failed after {_MAX_ATTEMPTS} attempts: {last_error}"
    )


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
        # find_spec checks the package is importable without actually importing
        # the heavy kokoro_onnx → phonemizer chain (keeps startup fast).
        import importlib.util

        if importlib.util.find_spec("kokoro_onnx") is None:
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
