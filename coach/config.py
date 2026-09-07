import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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

DATA_DIR = PROJECT_ROOT / "data"
# COACH_DB points the whole tool at a different database - the safe way to try
# things (or run the web UI) without touching data/coach.db.
DB_PATH = Path(os.environ["COACH_DB"]).expanduser() if os.environ.get("COACH_DB") else DATA_DIR / "coach.db"
CATALOG_PATH = DATA_DIR / "catalog.json"
REPORTS_DIR = PROJECT_ROOT / "reports"

# Sonnet ($2/$10 per Mtok against Opus's $5/$25) - the enrichment eval scored
# 100% on it, so the extra spend bought nothing this tool can measure.
MODEL = "claude-sonnet-5"

# Kept separate from MODEL so the evals can score a different model than the one
# the coach runs on, without either default dragging the other along.
EVAL_MODEL = "claude-sonnet-5"

EMBED_MODEL = "all-MiniLM-L6-v2"
WEEKLY_TARGET = 25
DAILY_TARGET = 4
CURRICULUM = "blind75"

WEB_HOST = os.environ.get("COACH_WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("COACH_WEB_PORT", "8000"))
