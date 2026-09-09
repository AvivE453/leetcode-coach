"""Runs coach-web itself, so `uv run pytest tests/browser` needs no setup.

The server is a real subprocess on a real port against a real (empty) database,
built by `coach init` exactly the way a person builds one - not a TestClient.
That is the point of a browser test: if the entry point, the static mount or the
port binding is broken, this is the suite that finds out.

Pass --base-url to skip all of that and use a server you are already running,
which is what you want while iterating on a page by hand.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

STARTUP_TIMEOUT = 30
SHUTDOWN_GRACE = 5
BIN = Path(sys.executable).parent


def free_port() -> int:
    """Let the kernel name a free port instead of hoping 8000 is idle.

    The port is released the moment this returns, so in principle something else
    could take it before the server binds. In practice nothing does, and the
    alternative - a hardcoded port - fails constantly against a dev server that
    is already running.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def answers(url: str) -> bool:
    """A real request, because a bound port is not a working server.

    A process that has bound the port and then stopped still completes the TCP
    handshake in the kernel - so a connect() check passes while every request
    hangs forever. Only a completed response proves the application is running,
    and the timeout is what keeps the middle state from hanging the suite.
    """
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


@pytest.fixture(scope="session", autouse=True)
def require_chromium(playwright):
    """`uv sync` installs the playwright library; the browser is a separate 150MB
    download, so a fresh clone has one and not the other. Skipping keeps
    `uv run pytest` green there instead of erroring on a missing binary.

    The `playwright` argument is pytest-playwright's own session fixture. Opening
    a second driver here instead would work, and would print a TargetClosedError
    to stderr on every run when it shuts down alongside theirs.
    """
    if not Path(playwright.chromium.executable_path).exists():
        pytest.skip("no chromium - run: uv run playwright install chromium")


@pytest.fixture(scope="session")
def base_url(request, tmp_path_factory, require_chromium):
    """Overrides pytest-base-url's fixture of the same name, unless it was given one.

    Depends on require_chromium so the skip happens before this spends two
    seconds building a database for a run that cannot start a browser anyway.
    """
    given = request.config.getoption("--base-url")
    if given:
        yield given
        return

    workdir = tmp_path_factory.mktemp("coach-web")
    env = {**os.environ, "COACH_DB": str(workdir / "coach.db")}
    subprocess.run([BIN / "coach", "init"], env=env, check=True, capture_output=True)

    env["COACH_WEB_PORT"] = str(free_port())
    url = f"http://127.0.0.1:{env['COACH_WEB_PORT']}"
    log = (workdir / "server.log").open("w")
    server = subprocess.Popen([BIN / "coach-web"], env=env, stdout=log, stderr=log)

    deadline = time.monotonic() + STARTUP_TIMEOUT
    while not answers(f"{url}/api/stats"):
        if server.poll() is not None or time.monotonic() > deadline:
            server.kill()
            raise RuntimeError(f"coach-web never answered on {url}; see {workdir / 'server.log'}")
        time.sleep(0.1)

    yield url

    # After the yield runs even when a test explodes - which is the only reason
    # the port is not left held by an orphan. terminate() is SIGTERM and lets
    # uvicorn close its sockets; kill() is the fallback if it ignores that.
    server.terminate()
    try:
        server.wait(timeout=SHUTDOWN_GRACE)
    except subprocess.TimeoutExpired:
        server.kill()
    log.close()
