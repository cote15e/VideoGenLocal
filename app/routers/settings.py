import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.choices import choose_llm, choose_tts, choose_video
from app.services.ffmpeg_util import ffmpeg_bin
from app.services.gpu import detect_gpu
from app.services.settings_store import ALLOWED, DEFAULTS, MODE_KEYS, SECRET_KEYS, resolved_settings
from app.services import tts
from app import db

router = APIRouter(prefix="/api", tags=["settings"])


class SettingsUpdate(BaseModel):
    llm_mode: str | None = None
    llm_provider: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    tts_mode: str | None = None
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str | None = None
    video_mode: str | None = None
    video_provider: str | None = None
    runway_api_key: str | None = None
    kling_api_key: str | None = None
    luma_api_key: str | None = None


def _system(settings: dict) -> dict:
    gpu = detect_gpu()
    piper = tts.piper_paths()
    try:
        ffmpeg_bin()
        ffmpeg_ok = True
    except Exception:
        ffmpeg_ok = False
    try:
        llm = choose_llm(
            mode=settings["llm_mode"],
            provider=settings["llm_provider"],
            key=settings["anthropic_api_key"] if settings["llm_provider"] == "anthropic" else settings["openai_api_key"],
        )
    except ValueError as exc:
        llm = f"error: {exc}"
    try:
        voice = choose_tts(
            mode=settings["tts_mode"],
            eleven_key=settings["elevenlabs_api_key"],
            gpu_memory_gb=float(gpu["memory_gb"]),
            piper_ready=piper is not None,
        )
    except ValueError as exc:
        voice = f"error: {exc}"
    video_key = {
        "runway": settings["runway_api_key"],
        "kling": settings["kling_api_key"],
        "luma": settings["luma_api_key"],
    }.get(settings["video_provider"], "")
    picture = choose_video(mode=settings["video_mode"], provider=settings["video_provider"], key=video_key)
    return {
        "ffmpeg": ffmpeg_ok,
        "ffprobe": shutil.which("ffprobe") is not None,
        "gpu": gpu,
        "piper": piper is not None,
        "edge_tts": tts.edge_tts_available(),
        "effective": {"llm": llm, "tts": voice, "video": picture},
    }


def _public_settings(settings: dict) -> dict:
    body = {
        "llm_mode": settings["llm_mode"],
        "llm_provider": settings["llm_provider"],
        "tts_mode": settings["tts_mode"],
        "elevenlabs_voice_id": settings["elevenlabs_voice_id"],
        "video_mode": settings["video_mode"],
        "video_provider": settings["video_provider"],
    }
    for key in SECRET_KEYS:
        body[f"{key}_set"] = bool(settings.get(key))
    body["system"] = _system(settings)
    return body


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/system")
def system():
    return _system(resolved_settings())


@router.get("/settings")
def get_settings():
    return _public_settings(resolved_settings())


@router.put("/settings")
def put_settings(body: SettingsUpdate):
    incoming = body.model_dump(exclude_unset=True)
    to_store: dict[str, str] = {}
    to_delete: list[str] = []
    for key, value in incoming.items():
        if key in MODE_KEYS:
            if value not in ALLOWED[key]:
                raise HTTPException(400, "Некорректный режим")
            to_store[key] = value
            continue
        if value is None:
            continue
        text = value.strip()
        if key in SECRET_KEYS or key == "elevenlabs_voice_id":
            if text:
                to_store[key] = text
            else:
                to_delete.append(key)
            continue
        if key in DEFAULTS:
            to_store[key] = text
    if to_store:
        db.set_settings(to_store)
    if to_delete:
        db.delete_settings(to_delete)
    return _public_settings(resolved_settings())
