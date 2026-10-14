"""Выбор провайдера без сети. Ключи сюда не логируются."""

LOCAL_TTS = ("piper", "edge")


def choose_llm(*, mode: str, provider: str, key: str) -> str:
    if mode != "api" or not key.strip():
        return "local"
    if provider not in {"anthropic", "openai"}:
        raise ValueError("Неизвестный провайдер языковой модели")
    return provider


def choose_tts(
    *,
    mode: str,
    eleven_key: str,
    gpu_memory_gb: float,
    piper_ready: bool,
) -> str:
    local = "piper" if piper_ready else "edge"
    if mode == "local":
        return local
    if mode == "api":
        if not eleven_key.strip():
            raise ValueError("Режим API для озвучки выбран, но ключ ElevenLabs не задан")
        return "elevenlabs"
    if gpu_memory_gb >= 12:
        return local
    if eleven_key.strip():
        return "elevenlabs"
    return local


def choose_video(*, mode: str, provider: str, key: str) -> str:
    if mode != "api":
        return "kenburns"
    if provider not in {"runway", "kling", "luma"} or not key.strip():
        return "kenburns"
    return provider
