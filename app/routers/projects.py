import asyncio
import io
import re
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, ImageOps

from app import db
from app.config import DATA_DIR
from app.schemas import Scene, parse_scenes
from app.services.llm import build_director_script
from app.services.render import project_root, render_project
from app.services.settings_store import resolved_settings

router = APIRouter(prefix="/api/projects", tags=["projects"])

_TASKS: set[asyncio.Task] = set()
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
_MUSIC_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
_ID = re.compile(r"^[0-9a-f]{32}$")

STATUS_LABELS = {
    "draft": "Черновик",
    "script_ready": "Сценарий готов",
    "approved": "Утверждён",
    "rendering": "Сборка",
    "done": "Готово",
    "failed": "Ошибка",
}


def _require(project_id: str) -> dict:
    if not _ID.fullmatch(project_id):
        raise HTTPException(404, "Выпуск не найден")
    project = db.get_project(project_id)
    if project is None:
        raise HTTPException(404, "Выпуск не найден")
    return project


def _inside(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(DATA_DIR.resolve()):
        raise HTTPException(404, "Файл не найден")
    return resolved


def _public(project: dict, *, detail: bool) -> dict:
    images = []
    if detail:
        for asset in project["assets"]:
            if asset["kind"] != "image":
                continue
            images.append(
                {
                    "id": asset["id"],
                    "filename": asset["filename"],
                    "url": f"/api/projects/{project['id']}/assets/{asset['id']}",
                }
            )
    outputs = []
    if detail:
        for output in project["outputs"]:
            outputs.append(
                {
                    "preset": output["preset"],
                    "width": output["width"],
                    "height": output["height"],
                    "url": f"/api/projects/{project['id']}/outputs/{output['preset']}",
                }
            )
    music = None
    if detail and project.get("music_path"):
        music = {
            "filename": project.get("music_name") or "music",
            "url": f"/api/projects/{project['id']}/music",
        }
    return {
        "id": project["id"],
        "title": project["title"],
        "script_text": project["script_text"] if detail else None,
        "status": project["status"],
        "status_label": STATUS_LABELS.get(project["status"], project["status"]),
        "error": project.get("error"),
        "scenes": project["scenes"] if detail else None,
        "script_engine": project.get("script_engine"),
        "image_count": project.get("image_count", len(images) if detail else 0),
        "images": images,
        "music": music,
        "progress": project.get("progress") or 0,
        "progress_label": project.get("progress_label"),
        "outputs": outputs,
        "created_at": project["created_at"],
        "updated_at": project["updated_at"],
    }


def _save_image(raw: bytes, dest: Path) -> None:
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            image = ImageOps.exif_transpose(image) or image
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, (18, 17, 14))
                background.paste(rgba, mask=rgba.split()[-1])
                image = background
            else:
                image = image.convert("RGB")
            resample = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            image.thumbnail((4096, 4096), resample)
            dest.parent.mkdir(parents=True, exist_ok=True)
            image.save(dest, "JPEG", quality=92)
    except Exception as exc:
        raise HTTPException(400, "Файл не похож на изображение jpg, png или webp") from exc


@router.get("")
def list_projects():
    return [_public(project, detail=False) for project in db.list_projects()]


@router.post("")
async def create_project(
    title: str = Form(...),
    script_text: str = Form(...),
    images: list[UploadFile] = File(...),
    music: UploadFile | None = File(None),
):
    title = title.strip()
    script_text = script_text.strip()
    if not title or len(title) > 120:
        raise HTTPException(400, "Укажите название до 120 символов")
    if not script_text or len(script_text) > 20000:
        raise HTTPException(400, "Добавьте текст сценария")
    files = [image for image in images if image.filename]
    if not 3 <= len(files) <= 5:
        raise HTTPException(400, "Нужно от 3 до 5 изображений")

    project_id = uuid.uuid4().hex
    root = project_root(project_id)
    image_dir = root / "images"
    try:
        image_dir.mkdir(parents=True, exist_ok=True)
        music_path = None
        music_name = None
        if music is not None and music.filename:
            suffix = Path(music.filename).suffix.lower()
            if suffix not in _MUSIC_EXT:
                raise HTTPException(400, "Музыка: mp3, wav, m4a, aac, ogg или flac")
            payload = await music.read()
            if not payload or len(payload) > 30 * 1024 * 1024:
                raise HTTPException(400, "Файл музыки пустой или больше 30 МБ")
            music_name = Path(music.filename).name
            music_path = str(root / f"music{suffix}")
            Path(music_path).write_bytes(payload)

        db.create_project(
            project_id=project_id,
            title=title,
            script_text=script_text,
            music_path=music_path,
            music_name=music_name,
        )
        for index, upload in enumerate(files):
            suffix = Path(upload.filename or "").suffix.lower()
            if suffix not in _IMAGE_EXT:
                raise HTTPException(400, "Изображения только jpg, png или webp")
            raw = await upload.read()
            if not raw or len(raw) > 20 * 1024 * 1024:
                raise HTTPException(400, "Изображение пустое или больше 20 МБ")
            dest = image_dir / f"{index + 1:02d}.jpg"
            _save_image(raw, dest)
            db.add_asset(
                asset_id=uuid.uuid4().hex,
                project_id=project_id,
                kind="image",
                filename=Path(upload.filename or dest.name).name,
                path=str(dest),
                sort_order=index,
            )
    except HTTPException:
        db.delete_project(project_id)
        shutil.rmtree(root, ignore_errors=True)
        raise
    except Exception as exc:
        db.delete_project(project_id)
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(500, "Не удалось сохранить выпуск") from exc

    created = db.get_project(project_id)
    return _public(created, detail=True)


@router.get("/{project_id}")
def get_project(project_id: str):
    return _public(_require(project_id), detail=True)


@router.post("/{project_id}/script")
async def build_script(project_id: str):
    project = _require(project_id)
    if project["status"] == "rendering":
        raise HTTPException(409, "Дождитесь конца сборки")
    images = [Path(asset["path"]) for asset in project["assets"] if asset["kind"] == "image"]
    try:
        scenes, engine, note = await build_director_script(
            project["script_text"],
            images,
            resolved_settings(),
        )
    except Exception as exc:
        message = str(exc).strip() or "Не удалось собрать сценарий"
        db.update_project(project_id, error=message[:2000])
        raise HTTPException(502, message[:2000]) from None
    import json

    db.update_project(
        project_id,
        scenes_json=json.dumps([scene.model_dump() for scene in scenes], ensure_ascii=False),
        script_engine=engine,
        status="script_ready",
        error=None,
    )
    body = _public(_require(project_id), detail=True)
    body["note"] = note
    return body


@router.put("/{project_id}/scenes")
def update_scenes(project_id: str, scenes: list[Scene]):
    project = _require(project_id)
    if project["status"] == "rendering":
        raise HTTPException(409, "Дождитесь конца сборки")
    if project["status"] == "draft":
        raise HTTPException(400, "Сначала соберите сценарий")
    import json

    parsed = parse_scenes([scene.model_dump() for scene in scenes])
    db.update_project(
        project_id,
        scenes_json=json.dumps([scene.model_dump() for scene in parsed], ensure_ascii=False),
        error=None,
    )
    if project["status"] in {"failed", "done", "approved"}:
        db.update_project(project_id, status="script_ready")
    return _public(_require(project_id), detail=True)


@router.post("/{project_id}/approve")
async def approve(project_id: str):
    project = _require(project_id)
    if not project["scenes"]:
        raise HTTPException(400, "Сначала соберите сценарий")
    if not db.claim_render(project_id):
        current = db.get_project(project_id)
        if current and current["status"] == "rendering":
            raise HTTPException(409, "Сборка уже идёт")
        raise HTTPException(400, "Сначала соберите сценарий")
    task = asyncio.create_task(render_project(project_id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return _public(_require(project_id), detail=True)


@router.get("/{project_id}/assets/{asset_id}")
def get_asset(project_id: str, asset_id: str):
    project = _require(project_id)
    for asset in project["assets"]:
        if asset["id"] == asset_id:
            path = _inside(Path(asset["path"]))
            if not path.is_file():
                raise HTTPException(404, "Файл не найден")
            return FileResponse(path, media_type="image/jpeg")
    raise HTTPException(404, "Файл не найден")


@router.get("/{project_id}/music")
def get_music(project_id: str):
    project = _require(project_id)
    if not project.get("music_path"):
        raise HTTPException(404, "Музыки нет")
    path = _inside(Path(project["music_path"]))
    if not path.is_file():
        raise HTTPException(404, "Файл не найден")
    return FileResponse(path, filename=project.get("music_name") or path.name)


@router.get("/{project_id}/outputs/{preset}")
def get_output(project_id: str, preset: str, download: int = 0):
    project = _require(project_id)
    for output in project["outputs"]:
        if output["preset"] == preset:
            path = _inside(Path(output["path"]))
            if not path.is_file():
                raise HTTPException(404, "Файл ещё не готов")
            filename = f"{preset}.mp4"
            return FileResponse(
                path,
                media_type="video/mp4",
                filename=filename if download else None,
                content_disposition_type="attachment" if download else "inline",
                headers={"Cache-Control": "no-store"},
            )
    raise HTTPException(404, "Файл ещё не готов")
