"""One-command launcher for the VCNITY prototype. Stdlib only.

    python app/start.py            # sync deps, start Postgres + API + UI
    python app/start.py --api-only # just the Flask API (useful with precompute)

Works on Windows 11 and macOS. Keeps the venv and the Reflex build out of the
Google Drive folder by pointing uv and Reflex at ~/.vcnity.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
HOME = Path(os.environ.get("VCNITY_HOME", Path.home() / ".vcnity"))
VENV = HOME / "venv"
WEB = HOME / "web"


def main() -> int:
    # A Windows console defaults to a codepage (e.g. cp1252) that can't encode
    # the arrows/dashes this script prints, crashing on the first such print.
    # Reconfigure this process's own stdout/stderr, and pass PYTHONIOENCODING
    # to the API/UI subprocesses so their own non-ASCII prints don't crash either.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    api_only = "--api-only" in sys.argv
    if shutil.which("uv") is None:
        print("uv is not installed. See https://docs.astral.sh/uv/ — then re-run.")
        return 1

    HOME.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = str(VENV)
    env["REFLEX_WEB_WORKDIR"] = str(WEB)
    env.setdefault("VCNITY_HOME", str(HOME))
    env.setdefault("PYTHONIOENCODING", "utf-8")

    print(f"[start] syncing dependencies into {VENV} (first run downloads ~2 GB)")
    subprocess.run(["uv", "sync", "--project", str(APP), "--extra", "dev"], env=env, check=True)

    procs: list[subprocess.Popen] = []
    try:
        print("[start] API  → http://127.0.0.1:%s" % env.get("VCNITY_API_PORT", "8100"))
        procs.append(subprocess.Popen(
            ["uv", "run", "--project", str(APP), "python", "-m", "api.app"], cwd=APP, env=env))
        if not api_only:
            time.sleep(3)
            print("[start] UI   → http://localhost:3000  (first run compiles the front end; give it a minute)")
            procs.append(subprocess.Popen(
                ["uv", "run", "--project", str(APP), "reflex", "run"], cwd=APP / "ui", env=env))
        print("[start] Ctrl-C stops everything.")
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        for p in procs:
            if p.poll() is not None:
                print(f"[start] a process exited with code {p.returncode}")
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                if os.name == "nt":
                    p.terminate()
                else:
                    p.send_signal(signal.SIGINT)
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
