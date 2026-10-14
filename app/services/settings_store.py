import os

from app.config import load_dotenv
from app import db

DEFAULTS = {
    "llm_mode": "local",
    "llm_provider": "anthropic",
    "anthropic_api_key": "",
    "openai_api_key": "",
    "anthropic_model": "claude-sonnet-4-5",
    "openai_model": "gpt-4o",
    "tts_mode": "auto",
    "elevenlabs_api_key": "",
    "elevenlabs_voice_id": "",
    "video_mode": "local",
    "video_provider": "runway",
    "runway_api_key": "",
    "kling_api_key": "",
    "luma_api_key": "",
}

MODE_KEYS = {"llm_mode", "llm_provider", "tts_mode", "video_mode", "video_provider"}

ENV_FOR_SETTING = {
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_model": "ANTHROPIC_MODEL",
    "openai_model": "OPENAI_MODEL",
    "elevenlabs_api_key": "ELEVENLABS_API_KEY",
    "elevenlabs_voice_id": "ELEVENLABS_VOICE_ID",
    "runway_api_key": "RUNWAY_API_KEY",
    "kling_api_key": "KLING_API_KEY",
    "luma_api_key": "LUMA_API_KEY",
}

SECRET_KEYS = {
    "anthropic_api_key",
    "openai_api_key",
    "elevenlabs_api_key",
    "runway_api_key",
    "kling_api_key",
    "luma_api_key",
}

ALLOWED = {
    "llm_mode": {"local", "api"},
    "llm_provider": {"anthropic", "openai"},
    "tts_mode": {"auto", "local", "api"},
    "video_mode": {"local", "api"},
    "video_provider": {"runway", "kling", "luma"},
}


def resolved_settings() -> dict[str, str]:
    load_dotenv()
    stored = db.get_all_settings()
    result = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in MODE_KEYS:
            if stored.get(key):
                result[key] = stored[key]
            continue
        db_value = stored.get(key, "")
        env_name = ENV_FOR_SETTING.get(key, "")
        env_value = os.environ.get(env_name, "") if env_name else ""
        result[key] = db_value or env_value or DEFAULTS[key]
    return result


def redact(text: str, secrets: list[str]) -> str:
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "***")
    return cleaned
