import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from app.config import DATA_DIR, DB_PATH

PROJECT_FIELDS = {
    "title",
    "script_text",
    "status",
    "error",
    "scenes_json",
    "script_engine",
    "music_path",
    "music_name",
    "progress",
    "progress_label",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                script_text TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                scenes_json TEXT,
                script_engine TEXT,
                music_path TEXT,
                music_name TEXT,
                progress INTEGER NOT NULL DEFAULT 0,
                progress_label TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                filename TEXT NOT NULL,
                path TEXT NOT NULL,
                sort_order INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS outputs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                preset TEXT NOT NULL,
                path TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                UNIQUE(project_id, preset)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def create_project(
    *,
    project_id: str,
    title: str,
    script_text: str,
    music_path: str | None,
    music_name: str | None,
) -> None:
    stamp = now()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO projects (
                id, title, script_text, status, error, scenes_json, script_engine,
                music_path, music_name, progress, progress_label, created_at, updated_at
            ) VALUES (?, ?, ?, 'draft', NULL, NULL, NULL, ?, ?, 0, NULL, ?, ?)
            """,
            (project_id, title, script_text, music_path, music_name, stamp, stamp),
        )


def add_asset(
    *,
    asset_id: str,
    project_id: str,
    kind: str,
    filename: str,
    path: str,
    sort_order: int,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO assets (id, project_id, kind, filename, path, sort_order)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (asset_id, project_id, kind, filename, path, sort_order),
        )


def update_project(project_id: str, **fields: Any) -> None:
    unknown = set(fields) - PROJECT_FIELDS
    if unknown:
        raise ValueError(f"неизвестные поля: {', '.join(sorted(unknown))}")
    fields["updated_at"] = now()
    columns = ", ".join(f"{key}=?" for key in fields)
    values = list(fields.values()) + [project_id]
    with connect() as conn:
        conn.execute(f"UPDATE projects SET {columns} WHERE id=?", values)


def claim_render(project_id: str) -> bool:
    """Атомарно: script_ready|failed|done → approved → rendering."""
    stamp = now()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT status FROM projects WHERE id=?", (project_id,)).fetchone()
        allowed = {"script_ready", "approved", "failed", "done"}
        if row is None or row["status"] not in allowed:
            conn.execute("ROLLBACK")
            return False
        conn.execute(
            "UPDATE projects SET status='approved', error=NULL, updated_at=? WHERE id=?",
            (stamp, project_id),
        )
        conn.execute(
            """
            UPDATE projects
            SET status='rendering', error=NULL, progress=0, progress_label=?, updated_at=?
            WHERE id=?
            """,
            ("Запускаем сборку", stamp, project_id),
        )
        conn.execute("COMMIT")
        return True
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def clear_outputs(project_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM outputs WHERE project_id=?", (project_id,))


def save_output(
    *,
    output_id: str,
    project_id: str,
    preset: str,
    path: str,
    width: int,
    height: int,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO outputs (id, project_id, preset, path, width, height)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, preset) DO UPDATE SET
                path=excluded.path, width=excluded.width, height=excluded.height
            """,
            (output_id, project_id, preset, path, width, height),
        )


def get_all_settings() -> dict[str, str]:
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def set_settings(values: dict[str, str]) -> None:
    with connect() as conn:
        for key, value in values.items():
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, value),
            )


def delete_settings(keys: list[str]) -> None:
    if not keys:
        return
    with connect() as conn:
        conn.executemany("DELETE FROM settings WHERE key=?", [(key,) for key in keys])


def _scenes(raw: str | None) -> list[dict]:
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else []


def _project_row(conn: sqlite3.Connection, project_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        return None
    assets = conn.execute(
        "SELECT * FROM assets WHERE project_id=? ORDER BY sort_order, id",
        (project_id,),
    ).fetchall()
    outputs = conn.execute(
        "SELECT * FROM outputs WHERE project_id=? ORDER BY preset",
        (project_id,),
    ).fetchall()
    data = dict(row)
    data["scenes"] = _scenes(data.pop("scenes_json"))
    data["assets"] = [dict(asset) for asset in assets]
    data["outputs"] = [dict(output) for output in outputs]
    return data


def get_project(project_id: str) -> dict | None:
    with connect() as conn:
        return _project_row(conn, project_id)


def list_projects() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        projects = []
        for row in rows:
            data = dict(row)
            data["scenes"] = _scenes(data.pop("scenes_json"))
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM assets WHERE project_id=? AND kind='image'",
                (data["id"],),
            ).fetchone()
            data["image_count"] = int(count["n"])
            data["assets"] = []
            data["outputs"] = []
            projects.append(data)
    return projects


def delete_project(project_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
