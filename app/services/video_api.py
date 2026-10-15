import asyncio
import base64
from pathlib import Path

import httpx

from app.presets import FPS, MASTER_SIZE, frames_for
from app.services.ffmpeg_util import run_ffmpeg
from app.services.settings_store import redact


class VideoAPIError(RuntimeError):
    pass


async def generate_broll(
    provider: str,
    settings: dict[str, str],
    image_path: Path,
    prompt: str,
    duration: float,
    dest: Path,
) -> None:
    raw = dest.with_name(dest.stem + "_api.mp4")
    if provider == "runway":
        await _runway(settings["runway_api_key"], image_path, prompt, duration, raw)
    elif provider == "kling":
        await _kling(settings["kling_api_key"], image_path, prompt, duration, raw)
    elif provider == "luma":
        await _luma(settings["luma_api_key"], image_path, prompt, duration, raw)
    else:
        raise VideoAPIError(f"Неизвестный видеопровайдер: {provider}")
    await normalize_clip(raw, dest, duration)


def _jpeg_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


async def normalize_clip(src: Path, dest: Path, duration: float) -> None:
    frames = frames_for(duration)
    video_filter = (
        f"scale={MASTER_SIZE}:{MASTER_SIZE}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={MASTER_SIZE}:{MASTER_SIZE},fps={FPS},"
        f"tpad=stop_mode=clone:stop_duration=30,format=yuv420p,setsar=1"
    )
    await run_ffmpeg(
        [
            "-y",
            "-i",
            str(src),
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


async def _runway(api_key: str, image_path: Path, prompt: str, duration: float, dest: Path) -> None:
    key = api_key.strip()
    headers = {
        "Authorization": f"Bearer {key}",
        "X-Runway-Version": "2024-11-06",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gen3a_turbo",
        "promptImage": f"data:image/jpeg;base64,{_jpeg_b64(image_path)}",
        "promptText": prompt[:1000],
        "duration": 5 if duration < 8 else 10,
        "ratio": "1280:768",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post("https://api.dev.runwayml.com/v1/image_to_video", headers=headers, json=payload)
        if response.status_code >= 400:
            raise VideoAPIError(f"Runway ответил {response.status_code}: {redact(response.text[:400], [key])}")
        task_id = response.json().get("id")
        if not task_id:
            raise VideoAPIError("Runway не вернул идентификатор задачи")
        for _ in range(60):
            await asyncio.sleep(5)
            poll = await client.get(f"https://api.dev.runwayml.com/v1/tasks/{task_id}", headers=headers)
            if poll.status_code >= 400:
                raise VideoAPIError(f"Runway ответил {poll.status_code}: {redact(poll.text[:400], [key])}")
            body = poll.json()
            status = body.get("status")
            if status == "SUCCEEDED":
                output = body.get("output") or []
                url = output[0] if output else None
                if not url:
                    raise VideoAPIError("Runway не вернул ссылку на ролик")
                video = await client.get(url)
                if video.status_code >= 400:
                    raise VideoAPIError("Runway не отдал готовый ролик")
                dest.write_bytes(video.content)
                return
            if status in {"FAILED", "CANCELLED"}:
                raise VideoAPIError(str(body.get("failure") or "Runway не собрал ролик"))
    raise VideoAPIError("Runway не успел завершить генерацию")


async def _kling(api_key: str, image_path: Path, prompt: str, duration: float, dest: Path) -> None:
    key = api_key.strip()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model_name": "kling-v1",
        "image": _jpeg_b64(image_path),
        "prompt": prompt[:1000],
        "duration": "5" if duration < 8 else "10",
        "mode": "std",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.klingai.com/v1/videos/image2video",
            headers=headers,
            json=payload,
        )
        if response.status_code >= 400:
            raise VideoAPIError(f"Kling ответил {response.status_code}: {redact(response.text[:400], [key])}")
        body = response.json()
        task_id = (body.get("data") or {}).get("task_id") or body.get("task_id")
        if not task_id:
            raise VideoAPIError("Kling не вернул идентификатор задачи")
        for _ in range(60):
            await asyncio.sleep(5)
            poll = await client.get(
                f"https://api.klingai.com/v1/videos/image2video/{task_id}",
                headers=headers,
            )
            if poll.status_code >= 400:
                raise VideoAPIError(f"Kling ответил {poll.status_code}: {redact(poll.text[:400], [key])}")
            data = poll.json().get("data") or poll.json()
            status = str(data.get("task_status") or data.get("status") or "").lower()
            if status in {"succeed", "succeeded", "success"}:
                videos = (data.get("task_result") or {}).get("videos") or data.get("videos") or []
                url = videos[0].get("url") if videos else None
                if not url:
                    raise VideoAPIError("Kling не вернул ссылку на ролик")
                video = await client.get(url)
                if video.status_code >= 400:
                    raise VideoAPIError("Kling не отдал готовый ролик")
                dest.write_bytes(video.content)
                return
            if status in {"failed", "error"}:
                raise VideoAPIError(str(data.get("task_status_msg") or "Kling не собрал ролик"))
    raise VideoAPIError("Kling не успел завершить генерацию")


async def _luma(api_key: str, image_path: Path, prompt: str, duration: float, dest: Path) -> None:
    del duration
    key = api_key.strip()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "prompt": prompt[:1000],
        "aspect_ratio": "1:1",
        "keyframes": {
            "frame0": {
                "type": "image",
                "url": f"data:image/jpeg;base64,{_jpeg_b64(image_path)}",
            }
        },
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.lumalabs.ai/dream-machine/v1/generations",
            headers=headers,
            json=payload,
        )
        if response.status_code >= 400:
            raise VideoAPIError(f"Luma ответил {response.status_code}: {redact(response.text[:400], [key])}")
        generation_id = response.json().get("id")
        if not generation_id:
            raise VideoAPIError("Luma не вернула идентификатор задачи")
        for _ in range(60):
            await asyncio.sleep(5)
            poll = await client.get(
                f"https://api.lumalabs.ai/dream-machine/v1/generations/{generation_id}",
                headers=headers,
            )
            if poll.status_code >= 400:
                raise VideoAPIError(f"Luma ответила {poll.status_code}: {redact(poll.text[:400], [key])}")
            body = poll.json()
            state = str(body.get("state") or "").lower()
            if state == "completed":
                url = (body.get("assets") or {}).get("video")
                if not url:
                    raise VideoAPIError("Luma не вернула ссылку на ролик")
                video = await client.get(url)
                if video.status_code >= 400:
                    raise VideoAPIError("Luma не отдала готовый ролик")
                dest.write_bytes(video.content)
                return
            if state == "failed":
                raise VideoAPIError(str(body.get("failure_reason") or "Luma не собрала ролик"))
    raise VideoAPIError("Luma не успела завершить генерацию")
