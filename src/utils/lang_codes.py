"""Language code mappings.

faster-whisper reports the detected language as an ISO 639-1 code (e.g. ``"ja"``)
and Whisper's tokenizer maps that to a lowercase English name (e.g.
``"japanese"``). For MKV metadata we need the ISO 639-2/B three-letter code
(e.g. ``"jpn"``). This module provides the lookups in both directions plus the
display-name → ISO 639-1 mapping used by the UI language-hint dropdown.
"""
from __future__ import annotations

# ISO 639-1 (Whisper output) → lowercase English language name.
ISO6391_TO_NAME: dict[str, str] = {
    "ja": "japanese",
    "ko": "korean",
    "zh": "chinese",
    "yue": "cantonese",
    "hi": "hindi",
    "es": "spanish",
    "fr": "french",
    "pt": "portuguese",
    "de": "german",
    "it": "italian",
    "ar": "arabic",
    "ru": "russian",
    "tr": "turkish",
    "th": "thai",
    "vi": "vietnamese",
    "id": "indonesian",
    "nl": "dutch",
    "pl": "polish",
    "sv": "swedish",
    "no": "norwegian",
    "en": "english",
}

# Language name (and common aliases) → ISO 639-2/B three-letter code.
NAME_TO_ISO6392B: dict[str, str] = {
    "japanese": "jpn",
    "korean": "kor",
    "chinese": "zho",
    "mandarin": "zho",
    "mandarin / chinese": "zho",
    "mandarin chinese": "zho",
    "cantonese": "yue",
    "hindi": "hin",
    "spanish": "spa",
    "castilian": "spa",
    "french": "fre",
    "portuguese": "por",
    "german": "ger",
    "italian": "ita",
    "arabic": "ara",
    "russian": "rus",
    "turkish": "tur",
    "thai": "tha",
    "vietnamese": "vie",
    "indonesian": "ind",
    "dutch": "dut",
    "flemish": "dut",
    "polish": "pol",
    "swedish": "swe",
    "norwegian": "nor",
    "english": "eng",
}

# UI display name → ISO 639-1 code (None = auto-detect). Order is preserved for
# the dropdown.
DISPLAY_TO_ISO6391: dict[str, str | None] = {
    "Auto-detect": None,
    "Japanese": "ja",
    "Korean": "ko",
    "Mandarin / Chinese": "zh",
    "Cantonese": "yue",
    "Hindi": "hi",
    "Spanish": "es",
    "French": "fr",
    "Portuguese": "pt",
    "German": "de",
    "Italian": "it",
    "Arabic": "ar",
    "Russian": "ru",
    "Turkish": "tr",
    "Thai": "th",
    "Vietnamese": "vi",
    "Indonesian": "id",
    "Dutch": "nl",
    "Polish": "pl",
    "Swedish": "sv",
    "Norwegian": "no",
}


def iso639_1_to_name(code: str) -> str:
    """Map an ISO 639-1 code (Whisper output) to a lowercase language name.

    Falls back to the code itself if unknown, so callers always get a usable
    display string.
    """
    return ISO6391_TO_NAME.get(code.lower(), code.lower())


def name_to_iso639_2b(name: str) -> str:
    """Map a language name to its ISO 639-2/B code, or ``"und"`` if unknown."""
    return NAME_TO_ISO6392B.get(name.strip().lower(), "und")


def whisper_code_to_iso639_2b(code: str) -> str:
    """Convenience: map a Whisper ISO 639-1 code directly to ISO 639-2/B."""
    return name_to_iso639_2b(iso639_1_to_name(code))
