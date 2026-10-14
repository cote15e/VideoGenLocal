from dataclasses import dataclass


@dataclass(frozen=True)
class FramePreset:
    key: str
    title: str
    width: int
    height: int


PRESETS: tuple[FramePreset, ...] = (
    FramePreset("youtube", "YouTube 16:9", 1920, 1080),
    FramePreset("shorts", "Shorts/Reels 9:16", 1080, 1920),
    FramePreset("feed", "Лента 1:1", 1080, 1080),
)

PRESET_BY_KEY = {preset.key: preset for preset in PRESETS}

MASTER_SIZE = 1920
FPS = 25


def cover_filter(width: int, height: int) -> str:
    """Center cover: uniform scale, then crop. The picture is not stretched."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height}"
    )


def cover_scale(src_w: float, src_h: float, dst_w: float, dst_h: float) -> tuple[float, float]:
    if src_w <= 0 or src_h <= 0:
        raise ValueError("некорректный размер исходного кадра")
    factor = max(dst_w / src_w, dst_h / src_h)
    return src_w * factor, src_h * factor


def frames_for(duration: float) -> int:
    return max(FPS, int(round(duration * FPS)))
