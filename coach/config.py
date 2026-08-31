import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "coach.db"
CATALOG_PATH = DATA_DIR / "catalog.json"
SOLUTIONS_DIR = PROJECT_ROOT / "solutions"
REPORTS_DIR = PROJECT_ROOT / "reports"

MODEL = "claude-opus-5"
EMBED_MODEL = "all-MiniLM-L6-v2"
WEEKLY_TARGET = 25
CURRICULUM = "blind75"


def load_env(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env into os.environ (real env vars win)."""
    if path is None:
        path = PROJECT_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_env()
