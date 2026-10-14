import asyncio
import json
import shutil
from pathlib import Path


class MediaError(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    binary = shutil.which("ffmpeg")
    if not binary:
        raise MediaError("Не найден ffmpeg. Установите FFmpeg и добавьте его в PATH.")
    return binary


def ffprobe_bin() -> str:
    binary = shutil.which("ffprobe")
    if not binary:
        raise MediaError("Не найден ffprobe. Установите FFmpeg и добавьте его в PATH.")
    return binary


def escape_filter_path(path: Path) -> str:
    text = path.resolve().as_posix()
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


async def run_ffmpeg(args: list[str], timeout: float = 240) -> None:
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise MediaError("FFmpeg превысил время ожидания") from None
    if proc.returncode != 0:
        tail = stderr.decode("utf-8", errors="replace").strip()[-800:]
        raise MediaError(f"FFmpeg: {tail or 'ошибка сборки'}")


async def probe(path: Path) -> dict:
    proc = await asyncio.create_subprocess_exec(
        ffprobe_bin(),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        tail = stderr.decode("utf-8", errors="replace").strip()[-400:]
        raise MediaError(f"ffprobe: {tail or 'не удалось прочитать файл'}")
    return json.loads(stdout)


async def probe_duration(path: Path) -> float:
    data = await probe(path)
    try:
        return float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaError("Не удалось измерить длительность") from exc


def video_stream(data: dict) -> dict | None:
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return None


def audio_stream(data: dict) -> dict | None:
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            return stream
    return None
