from datetime import date, timedelta

from typer.testing import CliRunner

from coach import config, db
from coach.cli import app

runner = CliRunner()

CODE = "class Solution:\n    def twoSum(self, nums, target):\n        return []\n"


def setup_env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "coach.db")
    monkeypatch.setattr(config, "SOLUTIONS_DIR", tmp_path / "solutions")
    conn = db.connect()
    db.init_schema(conn)
    db.upsert_problems(
        conn,
        [
            {
                "number": 1,
                "slug": "two-sum",
                "title": "Two Sum",
                "difficulty": "Easy",
                "official_tags": '["array"]',
                "paid_only": 0,
            }
        ],
    )
    conn.close()


def test_log_stores_attempt_solution_and_schedule(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)

    result = runner.invoke(app, ["log", "1", "--outcome", "struggled", "--time", "25"], input=CODE)
    assert result.exit_code == 0, result.output

    conn = db.connect()
    attempt = conn.execute("SELECT * FROM attempts").fetchone()
    assert attempt["outcome"] == "struggled"
    assert attempt["minutes"] == 25

    solution = conn.execute("SELECT * FROM solutions").fetchone()
    assert "twoSum" in solution["code"]
    assert solution["attempt_id"] == attempt["id"]

    state = conn.execute("SELECT * FROM review_state").fetchone()
    assert state["next_due"] == (date.today() + timedelta(days=1)).isoformat()

    sol_file = tmp_path / "solutions" / "0001-two-sum.py"
    assert sol_file.exists()
    content = sol_file.read_text()
    assert "# 1. Two Sum" in content
    assert "twoSum" in content


def test_second_solve_appends_and_advances_schedule(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)

    runner.invoke(app, ["log", "1", "--outcome", "clean"], input=CODE)
    result = runner.invoke(app, ["log", "1", "--outcome", "clean"], input=CODE)
    assert result.exit_code == 0, result.output

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 2
    state = conn.execute("SELECT * FROM review_state").fetchone()
    assert state["reps"] == 2
    assert state["interval_days"] == 6.0

    content = (tmp_path / "solutions" / "0001-two-sum.py").read_text()
    assert content.count("# ---") == 2


def test_log_unknown_problem_fails(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    result = runner.invoke(app, ["log", "99999"], input=CODE)
    assert result.exit_code == 1
    assert "not found" in result.output


def test_log_empty_input_fails(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    result = runner.invoke(app, ["log", "1"], input="  \n")
    assert result.exit_code == 1

    conn = db.connect()
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0


def test_due_lists_overdue_problems(tmp_path, monkeypatch):
    setup_env(tmp_path, monkeypatch)
    runner.invoke(app, ["log", "1", "--outcome", "clean"], input=CODE)

    conn = db.connect()
    conn.execute(
        "UPDATE review_state SET next_due = ?",
        ((date.today() - timedelta(days=2)).isoformat(),),
    )
    conn.commit()
    conn.close()

    result = runner.invoke(app, ["due"])
    assert result.exit_code == 0
    assert "#1 Two Sum" in result.output
    assert "overdue 2d" in result.output
