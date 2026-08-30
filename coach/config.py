from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "coach.db"
CATALOG_PATH = DATA_DIR / "catalog.json"
SOLUTIONS_DIR = PROJECT_ROOT / "solutions"
REPORTS_DIR = PROJECT_ROOT / "reports"

MODEL = "claude-opus-5"
WEEKLY_TARGET = 25
CURRICULUM = "blind75"
