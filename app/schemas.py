import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

__all__ = ["Scene", "ValidationError", "parse_scenes", "coerce_scene_payload"]


class Scene(BaseModel):
    scene: int = Field(ge=1)
    duration: float = Field(ge=1, le=120)
    visual_prompt: str = Field(min_length=1, max_length=4000)
    voiceover: str = Field(min_length=1, max_length=4000)

    @field_validator("visual_prompt", "voiceover")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("пустое поле")
        return text


def parse_scenes(data: Any) -> list[Scene]:
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict):
        for key in ("scenes", "scenario", "items"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list) or not data:
        raise ValueError("Сценарий должен быть непустым JSON-массивом сцен")
    scenes = [Scene.model_validate(item) for item in data]
    return [scene.model_copy(update={"scene": index}) for index, scene in enumerate(scenes, start=1)]


def coerce_scene_payload(text: str) -> list[Scene]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, count=1, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw, count=1)
    return parse_scenes(json.loads(raw))
