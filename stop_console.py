"""Stop the Help Desk portal server on port 8001."""

from __future__ import annotations

import subprocess
import sys

PORT = 8001


def main() -> int:
    if sys.platform == "win32":
        # Find PIDs listening on PORT and kill them
        try:
            out = subprocess.check_output(
                ["netstat", "-ano"],
                text=True,
                errors="ignore",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] netstat failed: {exc}")
            return 1
        pids: set[str] = set()
        needle = f":{PORT}"
        for line in out.splitlines():
            if needle in line and "LISTENING" in line.upper():
                parts = line.split()
                if parts:
                    pids.add(parts[-1])
        if not pids:
            print(f"[OK] Nothing listening on port {PORT}")
            return 0
        for pid in pids:
            if pid == "0":
                continue
            subprocess.run(["taskkill", "/PID", pid, "/F"], check=False)
            print(f"[OK] Killed PID {pid}")
        return 0

    # Unix: fuser or lsof
    try:
        subprocess.run(["fuser", "-k", f"{PORT}/tcp"], check=False)
        print(f"[OK] Tried fuser on {PORT}")
        return 0
    except FileNotFoundError:
        print("[ERROR] fuser not found; stop uvicorn manually")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
