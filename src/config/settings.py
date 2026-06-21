"""Application settings: dataclass + JSON persistence.

The pipeline consumes a handful of these fields (Whisper model, subtitle font,
stretch ratio, TTS voices); the full schema is defined here so the UI and
pipeline share a single settings object.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path

# Video containers the app accepts as input (app-wide constant).
SUPPORTED_VIDEO_EXTENSIONS: tuple[str, ...] = (".mp4", ".mkv", ".mov", ".avi")


@dataclass
class AppSettings:
    tts_provider: str = "kokoro"            # "kokoro" or "openai"
    openai_api_key: str = ""
    openai_voice: str = "nova"
    kokoro_voice: str = "af_heart"
    whisper_model: str = "large-v3"
    output_directory: str = ""              # empty = same as input
    subtitle_font: str = "Arial"
    subtitle_font_size: int = 18
    max_stretch_ratio: float = 1.35
    open_output_on_complete: bool = False


def get_settings_path() -> Path:
    """Return the platform-appropriate settings.json path.

    - Windows: ``%APPDATA%/AutoDubber/settings.json``
    - macOS:   ``~/Library/Application Support/AutoDubber/settings.json``
    - Other:   ``~/.config/AutoDubber/settings.json`` (XDG-style fallback)
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "AutoDubber" / "settings.json"


def load_settings() -> AppSettings:
    """Load settings from disk, ignoring unknown keys. Missing file → defaults."""
    path = get_settings_path()
    if not path.exists():
        return AppSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppSettings()
    known = {f.name for f in fields(AppSettings)}
    filtered = {k: v for k, v in raw.items() if k in known}
    return AppSettings(**filtered)


def save_settings(settings: AppSettings) -> None:
    """Persist settings to disk, creating the parent directory if needed."""
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
