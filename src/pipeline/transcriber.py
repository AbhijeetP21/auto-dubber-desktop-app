"""Transcribe + translate audio to English with faster-whisper.

Whisper's built-in ``task="translate"`` emits English text regardless of source
language, so there is no separate translation step. We also resolve the detected
language to both a human name and an ISO 639-2/B code for MKV metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from utils.lang_codes import iso639_1_to_name, name_to_iso639_2b

# Segment annotations Whisper sometimes emits for non-speech audio; skip them.
_NOISE_ANNOTATIONS = {
    "[music]", "[applause]", "[laughter]", "[silence]", "[no speech]",
    "(music)", "(applause)", "(laughter)",
}


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


def _clean_text(text: str) -> str | None:
    """Strip a segment; return None if it is empty or a noise annotation."""
    cleaned = text.strip()
    if not cleaned:
        return None
    if cleaned.lower() in _NOISE_ANNOTATIONS:
        return None
    return cleaned


def transcribe(
    audio_path: Path,
    language_hint: str | None = None,
    model_size: str = "large-v3",
    progress_callback: Callable[[float], None] | None = None,
) -> TranscriptionResult:
    """Transcribe and translate ``audio_path`` to English.

    Args:
        audio_path: 16kHz mono WAV.
        language_hint: ISO 639-1 source-language code (e.g. ``"ja"``) or None to
            auto-detect.
        model_size: Whisper model size (``tiny``..``large-v3``).
        progress_callback: called with a 0.0–1.0 float as segments stream in.
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, compute_type="auto")

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
    for seg in segments_iter:
        cleaned = _clean_text(seg.text)
        # Safety net: drop a segment that exactly repeats the previous kept line
        # (a residual Whisper loop), so it can't flood the dub and subtitles.
        if cleaned is not None and not (
            result.segments and result.segments[-1].text.lower() == cleaned.lower()
        ):
            result.segments.append(Segment(start=seg.start, end=seg.end, text=cleaned))
        if progress_callback is not None and total_duration > 0:
            progress_callback(min(seg.end / total_duration, 1.0))

    if progress_callback is not None:
        progress_callback(1.0)

    return result
