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
    subtitle_font_size: int = 32
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
    settings = AppSettings(**filtered)
    # A hand-edited file can hold anything; bad numerics would crash the
    # settings dialog (IntVar) or feed nonsense into the pipeline.
    defaults = AppSettings()
    try:
        settings.subtitle_font_size = max(12, min(48, int(settings.subtitle_font_size)))
    except (TypeError, ValueError):
        settings.subtitle_font_size = defaults.subtitle_font_size
    try:
        ratio = float(settings.max_stretch_ratio)
        # json accepts NaN/Infinity; both (and anything outside atempo's usable
        # range once split across two filters, i.e. (1.0, 4.0]) would make every
        # over-long segment fail in FFmpeg. Clamp to the range the syncer supports.
        if ratio != ratio or ratio in (float("inf"), float("-inf")):
            ratio = defaults.max_stretch_ratio
        settings.max_stretch_ratio = max(1.0, min(4.0, ratio))
    except (TypeError, ValueError):
        settings.max_stretch_ratio = defaults.max_stretch_ratio
    return settings


def save_settings(settings: AppSettings) -> None:
    """Persist settings to disk atomically.

    Written to a temp file then swapped in with ``os.replace``, so a crash
    mid-write can never leave a truncated settings.json (which would silently
    reset everything — including the API key — to defaults on next load).
    """
    path = get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    os.replace(tmp, path)
