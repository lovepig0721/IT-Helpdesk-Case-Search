"""
Double-click launcher for Help Desk Case Search Portal.
Starts uvicorn on 127.0.0.1:8001 if needed, then opens the browser.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8001
URL = f"http://{HOST}:{PORT}/"
HEALTH = f"{URL}health"
VENV_DIR = ROOT / ".venv"
VENV_PY = VENV_DIR / "Scripts" / "python.exe"
if sys.platform != "win32":
    VENV_PY = VENV_DIR / "bin" / "python"
LOG_FILE = ROOT / ".server.log"
REQ = ROOT / "requirements.txt"


def info(msg: str) -> None:
    print(msg, flush=True)


def health_ok(timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def ensure_venv() -> Path:
    if VENV_PY.is_file():
        info("[OK] venv found")
        return VENV_PY

    info("[1/3] Creating virtual environment...")
    venv.create(VENV_DIR, with_pip=True)
    if not VENV_PY.is_file():
        raise RuntimeError("Failed to create .venv")

    info("[2/3] Installing dependencies (first run may take a minute)...")
    subprocess.check_call(
        [str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip"],
        cwd=str(ROOT),
    )
    subprocess.check_call(
        [str(VENV_PY), "-m", "pip", "install", "-r", str(REQ)],
        cwd=str(ROOT),
    )
    return VENV_PY


def start_server(py: Path) -> None:
    if health_ok():
        info("[OK] Server already running")
        return

    info(f"[3/3] Starting server on {URL} ...")
    log = open(LOG_FILE, "a", encoding="utf-8")  # noqa: SIM115
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    subprocess.Popen(
        [
            str(py),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            HOST,
            "--port",
            str(PORT),
        ],
        cwd=str(ROOT),
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        close_fds=True,
    )

    for _ in range(40):
        time.sleep(0.25)
        if health_ok():
            info("[OK] Server is up")
            return
    raise RuntimeError(f"Server did not become healthy. See {LOG_FILE}")


def main() -> int:
    os.chdir(ROOT)
    try:
        py = ensure_venv()
        start_server(py)
        info(f"Opening {URL}")
        webbrowser.open(URL)
        return 0
    except Exception as exc:  # noqa: BLE001
        info(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
