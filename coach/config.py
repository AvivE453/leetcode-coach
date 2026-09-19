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

# The model that tags and reviews solves; COACH_MODEL in .env switches it without
# touching code. The name picks the API (llm.on_openrouter): `vendor/model` goes
# through OpenRouter on OPENROUTER_API_KEY, any other name to Anthropic on
# ANTHROPIC_API_KEY. The default is free, enforces structured outputs on its free
# endpoint, and answered a review in 5 s where the free DeepSeek took over a minute, but
# the evals have not scored it: RESULTS.md's numbers are Sonnet 5's.
MODEL = os.environ.get("COACH_MODEL", "nex-agi/nex-n2.5-pro:free")

# Kept separate from MODEL so the evals can score a different model than the one
# the coach runs on, without either default dragging the other along.
EVAL_MODEL = "claude-sonnet-5"

# Vectors from two models are not comparable, and search would compare them without
# a word if their lengths matched: after changing this, empty the `embeddings` table
# and run `coach enrich`, which rebuilds every missing vector (locally, no API calls).
EMBED_MODEL = "all-MiniLM-L6-v2"

# The most problems each Daily Plan heading lists: Due, Approach practice, Weak patterns.
SECTION_LIMIT = 10
# How many problems /solutions lists before you search; a search shows every match.
RECENT_SOLUTIONS = 10
CURRICULUM = "blind75"

WEB_HOST = os.environ.get("COACH_WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("COACH_WEB_PORT", "8000"))
