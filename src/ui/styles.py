"""Central style constants: colors, fonts, spacing, sizing.

Every UI module imports from here — no hardcoded hex values or pixel numbers
anywhere else. Keeping it all in one place makes the look easy to tweak.
"""
from __future__ import annotations

# --- Colors ---------------------------------------------------------------
BG = "#1a1a1a"            # window background
SURFACE = "#2b2b2b"       # panels, cards, inputs
SURFACE_HOVER = "#353535"  # hover state for surfaces
ACCENT = "#5b8ef0"        # primary actions, active states
ACCENT_HOVER = "#4a7ad8"
SUCCESS = "#4caf7d"
ERROR = "#e05a5a"
TEXT_PRIMARY = "#f0f0f0"
TEXT_SECONDARY = "#888888"
BORDER = "#3a3a3a"

# Status badge colors keyed by status string (see queue_panel.STATUS_*).
STATUS_COLORS: dict[str, str] = {
    "queued": TEXT_SECONDARY,
    "processing": ACCENT,
    "done": SUCCESS,
    "error": ERROR,
}

# --- Typography -----------------------------------------------------------
# Family left empty so CustomTkinter uses the platform default (Segoe UI on
# Windows, San Francisco on macOS). Sizes/weights are the knobs we set.
FONT_FAMILY = ""
FONT_SIZE_TITLE = 22
FONT_SIZE_HEADING = 15
FONT_SIZE_BODY = 13
FONT_SIZE_SMALL = 11

WEIGHT_BOLD = "bold"
WEIGHT_NORMAL = "normal"

# --- Spacing --------------------------------------------------------------
PAD_XS = 4
PAD_S = 8
PAD_M = 12
PAD_L = 20
PAD_XL = 28

# --- Sizing ---------------------------------------------------------------
CORNER_RADIUS = 8
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 640
WINDOW_MIN_WIDTH = 800
WINDOW_MIN_HEIGHT = 500

SETTINGS_WIDTH = 700
SETTINGS_HEIGHT = 500

APP_TITLE = "Auto Dubber"
