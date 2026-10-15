import asyncio
import logging
import shutil
import uuid
from pathlib import Path

from app.config import DATA_DIR
from app import db
from app.presets import FPS, PRESETS, cover_filter, frames_for
from app.services.choices import choose_tts, choose_video
from app.services.ffmpeg_util import (
    MediaError,
    audio_stream,
    escape_filter_path,
    probe,
    probe_duration,
    run_ffmpeg,
    video_stream,
)
from app.services.gpu import detect_gpu
from app.services.kenburns import render_kenburns
from app.services.settings_store import resolved_settings
from app.services.subtitles import cue_ranges, fonts_dir, write_ass
from app.services import tts
from app.services.video_api import VideoAPIError, generate_broll
from app.services.whisper import WhisperTranscriber

logger = logging.getLogger("videogen")

# Whisper подключён как интерфейс и на рендере не вызывается.
_WHISPER = WhisperTranscriber

PRESET_STYLE = {
    "youtube": {"font_size": 32, "margin_v": 56},
    "shorts": {"font_size": 42, "margin_v": 200},
    "feed": {"font_size": 34, "margin_v": 64},
}

_TTS_SEM = asyncio.Semaphore(1)
_VIDEO_SEM = asyncio.Semaphore(2)


def project_root(project_id: str) -> Path:
    return DATA_DIR / "projects" / project_id


def _set_progress(project_id: str, progress: int, label: str) -> None:
    db.update_project(project_id, progress=max(0, min(100, progress)), progress_label=label)


async def _fit_audio(src: Path, dest: Path, duration: float) -> None:
    await run_ffmpeg(
        [
            "-y",
            "-i",
            str(src),
            "-af",
            f"apad,atrim=0:{duration:.3f},asetpts=PTS-STARTPTS",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(dest),
        ]
    )


async def _mux(video: Path, audio: Path, dest: Path, duration: float) -> None:
    await run_ffmpeg(
        [
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(dest),
        ]
    )


def _concat_list(paths: list[Path], dest: Path) -> None:
    lines = []
    for path in paths:
        escaped = path.resolve().as_posix().replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _scene(
    index: int,
    scene: dict,
    image_path: Path,
    work: Path,
    tts_provider: str,
    video_provider: str,
    settings: dict,
) -> tuple[Path, float, float]:
    voice = str(scene["voiceover"]).strip()
    planned = float(scene["duration"])
    raw_audio = work / f"scene_{index:02d}.wav"
    async with _TTS_SEM:
        await tts.synthesize(tts_provider, voice, raw_audio, settings)
    speech = await probe_duration(raw_audio)
    if speech <= 0.05:
        raise MediaError(f"Сцена {index}: пустая озвучка")
    render_duration = max(planned, speech, 1.0)
    exact = frames_for(render_duration) / FPS
    fitted = work / f"scene_{index:02d}_fit.wav"
    await _fit_audio(raw_audio, fitted, exact)
    silent = work / f"scene_{index:02d}_silent.mp4"
    async with _VIDEO_SEM:
        if video_provider == "kenburns":
            await render_kenburns(image_path, silent, exact, index - 1)
        else:
            try:
                await generate_broll(
                    video_provider,
                    settings,
                    image_path,
                    str(scene["visual_prompt"]),
                    exact,
                    silent,
                )
            except VideoAPIError as exc:
                raise MediaError(str(exc)) from None
    muxed = work / f"scene_{index:02d}.mp4"
    await _mux(silent, fitted, muxed, exact)
    return muxed, exact, min(speech, exact)


async def render_project(project_id: str) -> None:
    try:
        await _render(project_id)
    except Exception as exc:
        message = str(exc).strip() or "Сборка не удалась"
        logger.error("render %s failed: %s", project_id, message)
        db.update_project(project_id, status="failed", error=message[:2000])


async def _render(project_id: str) -> None:
    project = db.get_project(project_id)
    if project is None:
        return
    scenes = project["scenes"]
    images = [asset for asset in project["assets"] if asset["kind"] == "image"]
    if not scenes:
        raise MediaError("Нет сцен для сборки")
    if not images:
        raise MediaError("Нет изображений для сборки")

    settings = resolved_settings()
    gpu = detect_gpu()
    piper_ready = tts.piper_paths() is not None
    tts_provider = choose_tts(
        mode=settings["tts_mode"],
        eleven_key=settings["elevenlabs_api_key"],
        gpu_memory_gb=float(gpu["memory_gb"]),
        piper_ready=piper_ready,
    )
    video_key = {
        "runway": settings["runway_api_key"],
        "kling": settings["kling_api_key"],
        "luma": settings["luma_api_key"],
    }.get(settings["video_provider"], "")
    video_provider = choose_video(
        mode=settings["video_mode"],
        provider=settings["video_provider"],
        key=video_key,
    )
    logger.info("render %s tts=%s video=%s", project_id, tts_provider, video_provider)

    root = project_root(project_id)
    work = root / "work"
    out = root / "out"
    if work.exists():
        shutil.rmtree(work)
    if out.exists():
        shutil.rmtree(out)
    work.mkdir(parents=True)
    out.mkdir(parents=True)
    db.clear_outputs(project_id)
    _set_progress(project_id, 4, "Озвучиваем и собираем кадры")

    total = len(scenes)
    done = 0

    async def one(index: int, scene: dict):
        nonlocal done
        image = images[(index - 1) % len(images)]
        result = await _scene(
            index,
            scene,
            Path(image["path"]),
            work,
            tts_provider,
            video_provider,
            settings,
        )
        done += 1
        span = 4 + int(62 * done / total)
        _set_progress(project_id, span, f"Сцена {done} из {total}")
        return result

    pieces = await asyncio.gather(*[one(index, scene) for index, scene in enumerate(scenes, start=1)])
    clips = [item[0] for item in pieces]
    segments = [(item[1], item[2]) for item in pieces]
    ranges = cue_ranges(segments)
    cues = [
        (start, end, str(scene["voiceover"]))
        for (start, end), scene in zip(ranges, scenes, strict=True)
    ]

    _set_progress(project_id, 70, "Склеиваем сцены")
    list_path = work / "concat.txt"
    _concat_list(clips, list_path)
    master = work / "master.mp4"
    await run_ffmpeg(
        [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(master),
        ]
    )

    source = master
    music = project.get("music_path")
    if music and Path(music).is_file():
        _set_progress(project_id, 78, "Добавляем музыку")
        mixed = work / "mixed.mp4"
        total_duration = sum(item[1] for item in pieces)
        await run_ffmpeg(
            [
                "-y",
                "-i",
                str(master),
                "-stream_loop",
                "-1",
                "-i",
                str(music),
                "-filter_complex",
                (
                    f"[1:a]volume=0.12,atrim=0:{total_duration:.3f},asetpts=PTS-STARTPTS[m];"
                    "[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
                ),
                "-map",
                "0:v",
                "-map",
                "[a]",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                str(mixed),
            ]
        )
        source = mixed

    labels = {
        "youtube": "Экспорт: YouTube 16:9",
        "shorts": "Экспорт: Shorts и Reels",
        "feed": "Экспорт: лента 1:1",
    }
    for offset, preset in enumerate(PRESETS):
        _set_progress(project_id, 82 + offset * 5, labels[preset.key])
        style = PRESET_STYLE[preset.key]
        ass_path = work / f"{preset.key}.ass"
        write_ass(
            ass_path,
            width=preset.width,
            height=preset.height,
            cues=cues,
            font_size=style["font_size"],
            margin_v=style["margin_v"],
        )
        dest = out / f"{preset.key}.mp4"
        fonts = fonts_dir()
        font_opt = f":fontsdir={escape_filter_path(fonts)}" if fonts else ""
        video_filter = (
            f"{cover_filter(preset.width, preset.height)},"
            f"subtitles={escape_filter_path(ass_path)}{font_opt}:charenc=UTF-8,"
            "format=yuv420p,setsar=1"
        )
        await run_ffmpeg(
            [
                "-y",
                "-i",
                str(source),
                "-vf",
                video_filter,
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "20",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                str(dest),
            ],
            timeout=300,
        )
        info = await probe(dest)
        video = video_stream(info)
        audio = audio_stream(info)
        if video is None or audio is None:
            raise MediaError(f"В файле {preset.title} нет картинки или звука")
        if int(video.get("width", 0)) != preset.width or int(video.get("height", 0)) != preset.height:
            raise MediaError(f"Неверный размер {preset.title}")
        duration = float(info.get("format", {}).get("duration") or 0)
        if duration <= 0:
            raise MediaError(f"Пустой файл {preset.title}")
        db.save_output(
            output_id=uuid.uuid4().hex,
            project_id=project_id,
            preset=preset.key,
            path=str(dest),
            width=preset.width,
            height=preset.height,
        )

    db.update_project(project_id, status="done", error=None, progress=100, progress_label="Готово")
