import base64
import io
from pathlib import Path

import httpx
from PIL import Image

from app.schemas import Scene, coerce_scene_payload
from app.services.settings_store import redact
from app.services.text_split import split_script

_PROMPT = """Ты режиссёр короткого видео. По тексту сценария и референс-изображениям собери покадровый сценарий.
Верни только JSON-массив объектов с полями:
scene (номер с 1), duration (секунды числом, около 5, дольше если реплика длинная), visual_prompt (что видно в кадре, по-русски), voiceover (текст диктора по-русски, по смыслу исходника).
Не добавляй пояснений вне JSON.

Текст сценария:
"""


def local_script(text: str) -> tuple[list[Scene], str, str]:
    return split_script(text), "local", "Сценарий собран локальным разбором текста."


def _jpeg_data_url(path: Path) -> tuple[str, str]:
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((1280, 1280))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return "image/jpeg", encoded


async def build_director_script(script_text: str, image_paths: list[Path], settings: dict[str, str]) -> tuple[list[Scene], str, str | None]:
    from app.services.choices import choose_llm

    provider = settings.get("llm_provider", "anthropic")
    key = ""
    if provider == "openai":
        key = settings.get("openai_api_key", "")
    else:
        key = settings.get("anthropic_api_key", "")
    engine = choose_llm(mode=settings.get("llm_mode", "local"), provider=provider, key=key)
    if engine == "local":
        scenes, name, note = local_script(script_text)
        if settings.get("llm_mode") == "api":
            note = "Ключ не задан, сценарий собран локальным разбором текста."
        return scenes, name, note
    if engine == "openai":
        scenes = await _openai(script_text, image_paths, settings)
        return scenes, "openai", None
    scenes = await _anthropic(script_text, image_paths, settings)
    return scenes, "anthropic", None


async def _anthropic(script_text: str, image_paths: list[Path], settings: dict[str, str]) -> list[Scene]:
    key = settings["anthropic_api_key"].strip()
    model = settings.get("anthropic_model") or "claude-sonnet-4-5"
    content: list[dict] = []
    for path in image_paths:
        media_type, data = _jpeg_data_url(path)
        content.append(
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": data},
            }
        )
    content.append({"type": "text", "text": _PROMPT + script_text})
    payload = {"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": content}]}
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
    except httpx.HTTPError:
        raise RuntimeError("Не удалось связаться с Anthropic") from None
    if response.status_code >= 400:
        raise RuntimeError(f"Anthropic ответил {response.status_code}: {redact(response.text[:400], [key])}")
    body = response.json()
    parts = []
    for block in body.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    text = "\n".join(parts).strip()
    try:
        return coerce_scene_payload(text)
    except Exception as exc:
        raise RuntimeError(f"Модель вернула сценарий в неожиданном виде: {exc}") from None


async def _openai(script_text: str, image_paths: list[Path], settings: dict[str, str]) -> list[Scene]:
    key = settings["openai_api_key"].strip()
    model = settings.get("openai_model") or "gpt-4o"
    content: list[dict] = [{"type": "text", "text": _PROMPT + script_text}]
    for path in image_paths:
        _media_type, data = _jpeg_data_url(path)
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}})
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    except httpx.HTTPError:
        raise RuntimeError("Не удалось связаться с OpenAI") from None
    if response.status_code >= 400:
        raise RuntimeError(f"OpenAI ответил {response.status_code}: {redact(response.text[:400], [key])}")
    body = response.json()
    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("OpenAI не вернул текст сценария") from None
    try:
        return coerce_scene_payload(text)
    except Exception as exc:
        raise RuntimeError(f"Модель вернула сценарий в неожиданном виде: {exc}") from None
