from pathlib import Path

from app.presets import FPS, MASTER_SIZE, frames_for
from app.services.ffmpeg_util import run_ffmpeg


def motion(variant: int, frames: int) -> tuple[str, str, str]:
    kind = variant % 3
    if kind == 0:
        zoom = f"min(1.0+0.12*on/{frames}\\,1.12)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif kind == 1:
        zoom = "1.12"
        x = f"(iw-iw/zoom)*on/{max(frames - 1, 1)}"
        y = "(ih-ih/zoom)/2"
    else:
        zoom = f"max(1.12-0.12*on/{frames}\\,1.0)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    return zoom, x, y


async def render_kenburns(image: Path, dest: Path, duration: float, variant: int) -> None:
    frames = frames_for(duration)
    zoom, x, y = motion(variant, frames)
    video_filter = (
        f"scale={MASTER_SIZE}:{MASTER_SIZE}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={MASTER_SIZE}:{MASTER_SIZE},"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={frames}:s={MASTER_SIZE}x{MASTER_SIZE}:fps={FPS},"
        f"format=yuv420p,setsar=1"
    )
    await run_ffmpeg(
        [
            "-y",
            "-i",
            str(image),
            "-vf",
            video_filter,
            "-frames:v",
            str(frames),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-an",
            str(dest),
        ]
    )
