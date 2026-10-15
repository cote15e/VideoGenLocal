# ВидеоГен

Локальный сервис для одного выпуска: текст и 3–5 изображений превращаются в режиссёрский сценарий, озвучку и три mp4.

- YouTube 16:9 — 1920×1080
- Shorts/Reels 9:16 — 1080×1920
- Лента 1:1 — 1080×1080

Кадр кадрируется по центру (cover): масштаб равномерный, лишнее обрезается, картинка не растягивается.

## Что нужно

- Python 3.11 или новее
- FFmpeg: в PATH должны быть `ffmpeg` и `ffprobe`
- Шрифт с кириллицей для субтитров. На Linux подойдут DejaVu Sans или Noto Sans. На Windows используется Arial.

Remotion не используется. DVC в первой версии не подключается: медиа и база лежат в локальной папке `data/`.

## Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8741
```

Откройте http://127.0.0.1:8741

Пакет FFmpeg, если его ещё нет: `sudo apt install ffmpeg`.

## Windows

В PowerShell или cmd:

```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
py -m uvicorn app.main:app --host 127.0.0.1 --port 8741
```

FFmpeg: `winget install Gyan.FFmpeg`. Откройте новое окно терминала, чтобы подхватился PATH, и снова запустите команду выше.

Та же команда через модуль, хост и порт берутся из окружения (`VIDEGEN_HOST`, `VIDEGEN_PORT`, по умолчанию `127.0.0.1` и `8741`):

```bat
py -m app
```

## Без ключей

Полный путь работает локально.

- Сценарий: разбор текста по абзацам, а если абзац один — по строкам или предложениям. `visual_prompt` и `voiceover` равны тексту сцены, длительность 5 секунд.
- Озвучка: Piper, если найдены бинарь и модель. Иначе edge-tts (нужен интернет, ключ не нужен), голос `ru-RU-SvetlanaNeural`.
- Видео: загруженные картинки по кругу и Ken Burns через FFmpeg `zoompan`.
- Субтитры пишутся из текста озвучки, по длительности речи. Whisper в рендере не вызывается.
- Фоновая музыка необязательна. Если файл приложен, он смешивается тише голоса.

Если ключ языковой модели задан и в настройках выбран API, сценарий запрашивается у Claude или GPT-4o. Локальный разбор в этом случае не подменяет ответ модели.

## Ключи и режимы

Раздел «Настройки» в интерфейсе. Значения хранятся в `data/videogen.db` или в файле `.env` (скопируйте `.env.example`). В журнал ключи не пишутся.

Переменные:

- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_MODEL`, `OPENAI_MODEL`
- `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` (в том числе id клонированного голоса)
- `RUNWAY_API_KEY`, `KLING_API_KEY`, `LUMA_API_KEY`
- `PIPER_BINARY`, `PIPER_MODEL`
- `EDGE_TTS_VOICE`
- `VIDEGEN_DATA_DIR`, `VIDEGEN_HOST`, `VIDEGEN_PORT`

Режимы:

- Языковая модель: локально или API (Claude / GPT-4o).
- Озвучка: авто, локально или ElevenLabs. Авто смотрит на GPU (`nvidia-smi`, если его нет — `torch`). При 12 ГБ и больше выбирается Piper или edge-tts. Если GPU нет или памяти меньше, и задан ключ ElevenLabs, выбирается API. Иначе снова Piper или edge-tts.
- Видео: Ken Burns или B-roll (Runway, Kling, Luma). Нет ключа — выпуск не блокируется, остаётся Ken Burns.

## Piper

Положите исполняемый файл `piper` в PATH (или укажите `PIPER_BINARY`) и модель `.onnx` в `PIPER_MODEL` либо в `data/models/piper/`. Для русской речи нужна русская модель. Пока бинарь или модель не найдены, используется edge-tts.

## Сборка выпуска

1. Новый выпуск: название, текст, 3–5 изображений (jpg, png, webp). Кнопка «Собрать сценарий».
2. Список сцен. Можно править длительность, visual prompt и озвучку. Кнопка «Утвердить и собрать».
3. Прогресс сборки. По готовности — превью и скачивание трёх mp4.

Статусы: черновик, сценарий готов, утверждён, сборка, готово. При сбое статус «ошибка» и текст причины.

## Тесты

```bash
pytest
```

Проверяют схему сцены, пресеты кадра и локальный разбор текста. Сеть не нужна.

## Проверка ролика

После сборки три файла лежат в `data/projects/<id>/out/`: `youtube.mp4`, `shorts.mp4`, `feed.mp4`.

```bash
ffprobe -hide_banner data/projects/<id>/out/youtube.mp4
```
