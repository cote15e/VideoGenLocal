import re

from app.schemas import Scene, parse_scenes

_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
_LONG_CHUNK = 500


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE.split(text.strip())
    return [part.strip() for part in parts if part.strip()]


def _chunks(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) >= 2:
        chunks = paragraphs
    else:
        block = paragraphs[0] if paragraphs else text
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) >= 2:
            chunks = lines
        else:
            sentences = split_sentences(block)
            chunks = sentences if len(sentences) >= 2 else [block]

    refined: list[str] = []
    for chunk in chunks:
        if len(chunk) > _LONG_CHUNK:
            sentences = split_sentences(chunk)
            refined.extend(sentences if len(sentences) >= 2 else [chunk])
        else:
            refined.append(chunk)
    return refined


def split_script(text: str) -> list[Scene]:
    """Локальный разбор: абзацы или предложения, visual_prompt и voiceover из текста, duration 5 с."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("Пустой текст сценария")
    raw = [
        {
            "scene": index,
            "duration": 5,
            "visual_prompt": chunk,
            "voiceover": chunk,
        }
        for index, chunk in enumerate(_chunks(normalized), start=1)
    ]
    return parse_scenes(raw)
