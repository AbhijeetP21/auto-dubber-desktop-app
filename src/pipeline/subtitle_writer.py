"""Write styled English subtitles as an ASS file.

ASS (not SRT) is used because the styling survives muxing into MKV and renders
in VLC. Times are formatted ``H:MM:SS.cc`` (centiseconds).
"""
from __future__ import annotations

from pathlib import Path

from .transcriber import Segment

_WRAP_THRESHOLD = 80  # characters; longer lines get wrapped with \N

_HEADER_TEMPLATE = """[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2.5,1,2,10,10,25,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _format_time(seconds: float) -> str:
    """Format seconds as ASS ``H:MM:SS.cc`` (centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _wrap_text(text: str) -> str:
    """Sanitize for ASS, collapse newlines, and word-wrap with ``\\N`` breaks."""
    # ASS has no escape for these: `{`/`}` open override blocks (hiding the
    # enclosed text in the player) and `\` can start a control sequence, so
    # substitute lookalikes.
    text = text.replace("{", "(").replace("}", ")").replace("\\", "/")
    # Collapse any embedded newlines/whitespace runs into single spaces.
    text = " ".join(text.split())
    if len(text) <= _WRAP_THRESHOLD:
        return text

    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        if current and len(current) + 1 + len(word) > _WRAP_THRESHOLD:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return "\\N".join(lines)


def write_ass(
    segments: list[Segment],
    output_path: Path,
    font_name: str = "Arial",
    font_size: int = 18,
    play_res_x: int = 1920,
    play_res_y: int = 1080,
) -> None:
    """Write ``segments`` to an ASS subtitle file at ``output_path``."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = _HEADER_TEMPLATE.format(
        play_res_x=play_res_x,
        play_res_y=play_res_y,
        font_name=font_name,
        font_size=font_size,
    )

    lines = [header]
    for seg in segments:
        text = _wrap_text(seg.text)
        start = _format_time(seg.start)
        end = _format_time(seg.end)
        lines.append(
            f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}"
        )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
