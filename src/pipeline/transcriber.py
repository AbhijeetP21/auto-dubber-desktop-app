"""Transcribe + translate audio to English with faster-whisper.

Whisper's built-in ``task="translate"`` emits English text regardless of source
language, so there is no separate translation step. We also resolve the detected
language to both a human name and an ISO 639-2/B code for MKV metadata.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from utils.cancellation import CancelCheck, check_cancelled
from utils.lang_codes import iso639_1_to_name, name_to_iso639_2b

# Whisper models download from Hugging Face on first use. Without a read
# timeout a stalled connection (e.g. laptop sleep mid-download) hangs forever —
# same bug class the Kokoro downloader was hardened against.
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")

# Segment annotations Whisper sometimes emits for non-speech audio; skip them.
_NOISE_ANNOTATIONS = {
    "[music]", "[applause]", "[laughter]", "[silence]", "[no speech]",
    "(music)", "(applause)", "(laughter)",
}

# Consecutive identical lines beyond this count are treated as a Whisper
# hallucination loop and dropped. Two is allowed so genuinely repeated speech
# ("Run! ... Run!") survives in the dub and subtitles.
_MAX_CONSECUTIVE_REPEATS = 2

# The loaded model is cached so a batch of videos doesn't reload a multi-GB
# model per job. Only the most recent size is kept (they are too big to stack).
_model_cache: dict[str, object] = {}


def _clean_text(text: str) -> str | None:
    """Strip a segment; return None if it is empty or a noise annotation."""
    cleaned = text.strip()
    if not cleaned:
        return None
    if cleaned.lower() in _NOISE_ANNOTATIONS:
        return None
    return cleaned


@dataclass
class Segment:
    start: float      # seconds
    end: float        # seconds
    text: str         # English translated text


@dataclass
class TranscriptionResult:
    segments: list[Segment] = field(default_factory=list)
    detected_language: str = "unknown"        # e.g. "japanese"
    detected_language_code: str = "und"       # ISO 639-2/B e.g. "jpn"


def _load_model(model_size: str, download_notify: Callable[[], None] | None):
    """Load (or fetch from cache) the Whisper model, downloading if needed.

    ``download_notify`` fires once if the model is not cached locally, so the
    UI can tell the user a multi-GB first-run download is in progress instead
    of appearing frozen at "Transcribing...".
    """
    from faster_whisper import WhisperModel

    cached = _model_cache.get(model_size)
    if cached is not None:
        return cached

    try:
        model = WhisperModel(model_size, compute_type="auto", local_files_only=True)
    except Exception:
        # Not on disk yet — this run will download it.
        if download_notify is not None:
            download_notify()
        model = WhisperModel(model_size, compute_type="auto")

    _model_cache.clear()  # at most one model in memory
    _model_cache[model_size] = model
    return model


def transcribe(
    audio_path: Path,
    language_hint: str | None = None,
    model_size: str = "large-v3",
    progress_callback: Callable[[float], None] | None = None,
    download_notify: Callable[[], None] | None = None,
    should_cancel: CancelCheck | None = None,
) -> TranscriptionResult:
    """Transcribe and translate ``audio_path`` to English.

    Args:
        audio_path: 16kHz mono WAV.
        language_hint: ISO 639-1 source-language code (e.g. ``"ja"``) or None to
            auto-detect.
        model_size: Whisper model size (``tiny``..``large-v3``).
        progress_callback: called with a 0.0–1.0 float as segments stream in.
        download_notify: called once if the model must be downloaded first.
        should_cancel: raises :class:`JobCancelled` between segments when True.
    """
    model = _load_model(model_size, download_notify)
    check_cancelled(should_cancel)

    segments_iter, info = model.transcribe(
        str(audio_path),
        task="translate",
        language=language_hint,
        # Anti-repetition: Whisper can loop on the same translated sentence,
        # especially over music/silence. These three options together are the
        # standard mitigation:
        vad_filter=True,                   # skip non-speech that triggers hallucinated loops
        condition_on_previous_text=False,  # don't let a repeat feed itself and perpetuate
        no_repeat_ngram_size=3,            # hard-block repeating 3-grams during decoding
    )

    detected_name = iso639_1_to_name(info.language)
    result = TranscriptionResult(
        detected_language=detected_name,
        detected_language_code=name_to_iso639_2b(detected_name),
    )

    # faster-whisper streams segments lazily; use audio duration to estimate
    # progress as each segment's end time advances.
    total_duration = float(getattr(info, "duration", 0.0)) or 0.0
    repeat_count = 0
    for seg in segments_iter:
        check_cancelled(should_cancel)
        cleaned = _clean_text(seg.text)
        if cleaned is not None:
            if result.segments and result.segments[-1].text.lower() == cleaned.lower():
                repeat_count += 1
            else:
                repeat_count = 0
            # Keep genuine repeats (up to _MAX_CONSECUTIVE_REPEATS in a row);
            # drop longer runs, which are residual Whisper hallucination loops
            # that would otherwise flood the dub and subtitles.
            if repeat_count < _MAX_CONSECUTIVE_REPEATS:
                result.segments.append(
                    Segment(start=seg.start, end=seg.end, text=cleaned)
                )
        if progress_callback is not None and total_duration > 0:
            progress_callback(min(seg.end / total_duration, 1.0))

    if progress_callback is not None:
        progress_callback(1.0)

    return result
