import pytest

from app.schemas import parse_scenes
from app.services.text_split import split_script


def test_paragraphs_become_scenes_with_shared_text_and_five_seconds():
    text = "Первый абзац про утро.\n\nВторой абзац про свет.\n\nТретий абзац про монтаж."
    scenes = split_script(text)
    assert [scene.scene for scene in scenes] == [1, 2, 3]
    assert scenes[0].voiceover == "Первый абзац про утро."
    assert scenes[0].visual_prompt == scenes[0].voiceover
    assert scenes[1].voiceover == "Второй абзац про свет."
    assert all(scene.duration == 5 for scene in scenes)
    assert parse_scenes([scene.model_dump() for scene in scenes])[2].voiceover.startswith("Третий")


def test_sentences_when_text_is_one_paragraph():
    scenes = split_script("Город просыпается. Камера ловит свет. Вечером ролик готов.")
    assert [scene.voiceover for scene in scenes] == [
        "Город просыпается.",
        "Камера ловит свет.",
        "Вечером ролик готов.",
    ]


def test_single_newlines_when_there_is_no_blank_line():
    scenes = split_script("Первая строка кадра\nВторая строка кадра")
    assert len(scenes) == 2
    assert scenes[1].visual_prompt == "Вторая строка кадра"


def test_long_paragraph_splits_into_sentences():
    sentence = "Это довольно длинное предложение про утро на реке и камеру. "
    text = sentence * 12
    scenes = split_script(text.strip())
    assert len(scenes) > 1
    assert all(scene.duration == 5 for scene in scenes)


def test_empty_text_raises():
    with pytest.raises(ValueError):
        split_script("  \n  ")


def test_one_sentence_stays_one_scene():
    scenes = split_script("Только одна фраза без точки")
    assert len(scenes) == 1
    assert scenes[0].scene == 1
    assert scenes[0].duration == 5
