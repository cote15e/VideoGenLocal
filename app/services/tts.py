import asyncio
import importlib.util
import os
import shutil
from pathlib import Path

from app.config import DATA_DIR
from app.services.ffmpeg_util import run_ffmpeg
from app.services.settings_store import redact


def piper_paths() -> tuple[str, str] | None:
    binary = os.environ.get("PIPER_BINARY") or shutil.which("piper")
    model = os.environ.get("PIPER_MODEL") or ""
    if not model:
        found = sorted(DATA_DIR.glob("models/piper/**/*.onnx"))
        model = str(found[0]) if found else ""
    if binary and model and Path(model).is_file():
        return binary, model
    return None


def edge_tts_available() -> bool:
    return importlib.util.find_spec("edge_tts") is not None


async def synthesize(provider: str, text: str, dest_wav: Path, settings: dict[str, str]) -> None:
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    if provider == "piper":
        await _piper(text, dest_wav)
    elif provider == "elevenlabs":
        await _elevenlabs(text, dest_wav, settings)
    elif provider == "edge":
        await _edge(text, dest_wav)
    else:
        raise RuntimeError(f"Неизвестный способ озвучки: {provider}")
    if not dest_wav.is_file() or dest_wav.stat().st_size < 1000:
        raise RuntimeError("Озвучка получилась пустой")


async def _to_wav(source: Path, dest_wav: Path) -> None:
    await run_ffmpeg(
        [
            "-y",
            "-i",
            str(source),
            "-ar",
            "44100",
            "-ac",
            "1",
            str(dest_wav),
        ]
    )


async def _edge(text: str, dest_wav: Path) -> None:
    import edge_tts

    voice = os.environ.get("EDGE_TTS_VOICE") or "ru-RU-SvetlanaNeural"
    mp3 = dest_wav.with_suffix(".mp3")
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(mp3))
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.6)
    if last_error is not None:
        raise RuntimeError(
            "Не удалось озвучить через edge-tts. Проверьте сеть или установите Piper."
        ) from None
    await _to_wav(mp3, dest_wav)


async def _piper(text: str, dest_wav: Path) -> None:
    found = piper_paths()
    if not found:
        raise RuntimeError("Piper не найден: нужен бинарь и модель .onnx")
    binary, model = found
    raw = dest_wav.with_name(dest_wav.stem + "_piper.wav")
    proc = await asyncio.create_subprocess_exec(
        binary,
        "--model",
        model,
        "--output_file",
        str(raw),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate(text.encode("utf-8"))
    if proc.returncode != 0:
        tail = stderr.decode("utf-8", errors="replace").strip()[-400:]
        raise RuntimeError(f"Piper: {tail or 'ошибка озвучки'}")
    await _to_wav(raw, dest_wav)


async def _elevenlabs(text: str, dest_wav: Path, settings: dict[str, str]) -> None:
    import httpx

    key = settings.get("elevenlabs_api_key", "").strip()
    voice = settings.get("elevenlabs_voice_id", "").strip()
    if not key:
        raise RuntimeError("Ключ ElevenLabs не задан")
    if not voice:
        raise RuntimeError("Укажите voice id ElevenLabs")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
    headers = {"xi-api-key": key, "accept": "audio/mpeg"}
    payload = {"text": text, "model_id": "eleven_multilingual_v2"}
    mp3 = dest_wav.with_suffix(".mp3")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError:
        raise RuntimeError("Не удалось связаться с ElevenLabs") from None
    if response.status_code >= 400:
        body = redact(response.text[:400], [key, voice])
        raise RuntimeError(f"ElevenLabs ответил {response.status_code}: {body}")
    mp3.write_bytes(response.content)
    await _to_wav(mp3, dest_wav)
