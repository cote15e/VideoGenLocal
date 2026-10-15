import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("VIDEGEN_DATA_DIR", ROOT / "data")).resolve()
DB_PATH = DATA_DIR / "videogen.db"
STATIC_DIR = Path(__file__).resolve().parent / "static"
HOST = os.environ.get("VIDEGEN_HOST", "127.0.0.1")
PORT = int(os.environ.get("VIDEGEN_PORT", "8741"))


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or (ROOT / ".env")
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
