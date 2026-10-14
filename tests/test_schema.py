import pytest
from pydantic import ValidationError

from app.schemas import coerce_scene_payload, parse_scenes


def test_parse_array_renumbers_scenes():
    scenes = parse_scenes(
        [
            {"scene": 8, "duration": 5, "visual_prompt": "кадр реки", "voiceover": "Утро на набережной."},
            {"scene": 2, "duration": 6.5, "visual_prompt": "свет на воде", "voiceover": "Свет ложится на воду."},
        ]
    )
    assert [scene.scene for scene in scenes] == [1, 2]
    assert scenes[0].voiceover == "Утро на набережной."
    assert scenes[1].duration == 6.5


def test_parse_wrapped_object_and_json_string():
    scenes = parse_scenes(
        '{"scenes": [{"scene": 1, "duration": 5, "visual_prompt": "кадр", "voiceover": "текст"}]}'
    )
    assert len(scenes) == 1
    assert scenes[0].visual_prompt == "кадр"


def test_coerce_markdown_fence():
    raw = """```json
[{"scene": 1, "duration": 5, "visual_prompt": "кадр", "voiceover": "реплика"}]
```"""
    scenes = coerce_scene_payload(raw)
    assert scenes[0].voiceover == "реплика"


def test_reject_missing_voiceover():
    with pytest.raises(ValidationError):
        parse_scenes([{"scene": 1, "duration": 5, "visual_prompt": "кадр"}])


def test_reject_empty_list_and_short_duration():
    with pytest.raises(ValueError):
        parse_scenes([])
    with pytest.raises(ValidationError):
        parse_scenes([{"scene": 1, "duration": 0.2, "visual_prompt": "кадр", "voiceover": "текст"}])
