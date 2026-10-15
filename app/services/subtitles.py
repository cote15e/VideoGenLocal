import os
import re
import sys
from pathlib import Path


def cue_ranges(segments: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """segments: (длина кадра, длина речи) → интервалы субтитров по речи."""
    cues: list[tuple[float, float]] = []
    cursor = 0.0
    for render_duration, speech_duration in segments:
        speech = max(0.0, min(speech_duration, render_duration))
        cues.append((cursor, cursor + speech))
        cursor += render_duration
    return cues


def format_ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours = centiseconds // 360000
    centiseconds %= 360000
    minutes = centiseconds // 6000
    centiseconds %= 6000
    secs = centiseconds // 100
    centiseconds %= 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def subtitle_font() -> str:
    if sys.platform == "win32":
        return "Arial"
    return "DejaVu Sans"


def fonts_dir() -> Path | None:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidates = [
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/noto"),
        Path(windir) / "Fonts",
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return None


def ass_escape(text: str, width: int) -> str:
    cleaned = text.replace("\r", "").replace("{", "(").replace("}", ")")
    cleaned = re.sub(r"\s*\n\s*", " ", cleaned).strip()
    limit = 28 if width <= 1080 else 36
    words = cleaned.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > limit:
            lines.append(current)
            current = word
        else:
            current = word if not current else f"{current} {word}"
    if current:
        lines.append(current)
    if len(lines) > 4:
        lines = lines[:4]
        lines[-1] = lines[-1].rstrip(".") + "…"
    return "\\N".join(lines)


def write_ass(
    path,
    *,
    width: int,
    height: int,
    cues: list[tuple[float, float, str]],
    font: str | None = None,
    font_size: int = 32,
    margin_v: int = 56,
) -> None:
    family = font or subtitle_font()
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{family},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3,0,2,48,48,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for start, end, text in cues:
        body = ass_escape(text, width)
        if not body:
            continue
        lines.append(
            f"Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},Default,,0,0,0,,{body}\n"
        )
    path.write_text("".join(lines), encoding="utf-8")
