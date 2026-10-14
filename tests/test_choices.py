import pytest

from app.services.choices import choose_llm, choose_tts, choose_video


def test_llm_uses_api_only_with_key():
    assert choose_llm(mode="local", provider="anthropic", key="secret") == "local"
    assert choose_llm(mode="api", provider="openai", key="") == "local"
    assert choose_llm(mode="api", provider="anthropic", key="sk-ant") == "anthropic"
    assert choose_llm(mode="api", provider="openai", key="sk-openai") == "openai"


def test_tts_auto_follows_gpu_threshold():
    assert choose_tts(mode="auto", eleven_key="key", gpu_memory_gb=12, piper_ready=True) == "piper"
    assert choose_tts(mode="auto", eleven_key="key", gpu_memory_gb=11.9, piper_ready=True) == "elevenlabs"
    assert choose_tts(mode="auto", eleven_key="", gpu_memory_gb=0, piper_ready=False) == "edge"
    assert choose_tts(mode="auto", eleven_key="", gpu_memory_gb=24, piper_ready=False) == "edge"
    assert choose_tts(mode="local", eleven_key="key", gpu_memory_gb=0, piper_ready=True) == "piper"


def test_tts_api_without_key_is_an_error():
    with pytest.raises(ValueError):
        choose_tts(mode="api", eleven_key="", gpu_memory_gb=0, piper_ready=True)


def test_video_falls_back_to_kenburns_without_blocking():
    assert choose_video(mode="local", provider="runway", key="key") == "kenburns"
    assert choose_video(mode="api", provider="kling", key="") == "kenburns"
    assert choose_video(mode="api", provider="luma", key="key") == "luma"
