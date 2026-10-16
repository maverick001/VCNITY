"""One-command launcher for the VCNITY prototype. Stdlib only.

    python app/start.py            # sync deps, start Postgres + API + UI
    python app/start.py --api-only # just the Flask API (useful with precompute)
    python app/start.py --sync     # force the dependency sync even if uv.lock hasn't changed

On Windows 11 it also starts `ollama serve` in the background if Ollama isn't running.
Works on Windows 11 and macOS. Keeps the venv and the Reflex build out of the
Google Drive folder by pointing uv and Reflex at ~/.vcnity.
"""
from __future__ import annotations

import hashlib
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
SYNC_STAMP = HOME / "sync.stamp"


def _deps_fingerprint() -> str:
    """Changes when the lock file or the project file does, i.e. when a sync could have something to do."""
    h = hashlib.sha256()
    for name in ("uv.lock", "pyproject.toml"):
        h.update((APP / name).read_bytes())
    return h.hexdigest()


def _venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _needs_sync(force: bool) -> bool:
    if force or not _venv_python().exists():
        return True
    try:
        return SYNC_STAMP.read_text(encoding="utf-8").strip() != _deps_fingerprint()
    except OSError:
        return True


def _ollama_running() -> bool:
    """True if an ollama.exe (the server, not the tray app 'ollama app.exe') is in the Windows process list."""
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ollama.exe", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "ollama.exe" in out.lower()


def _ensure_ollama() -> None:
    """On Windows, start `ollama serve` hidden and detached if Ollama isn't running. Never stops the launch."""
    if os.name != "nt":
        return
    if _ollama_running():
        print("[start] Ollama is already running")
        return
    if shutil.which("ollama") is None:
        print("[start] WARNING: Ollama is not running and 'ollama' is not on PATH. Install it from https://ollama.com "
              "— the AI steps will fail until it is running.")
        return
    try:
        # DETACHED_PROCESS + CREATE_NO_WINDOW: no console window, and it keeps running after this launcher stops.
        subprocess.Popen(["ollama", "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True,
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
    except OSError as e:
        print(f"[start] WARNING: could not start Ollama ({e}). Start it yourself with 'ollama serve'.")
        return
    for _ in range(10):
        time.sleep(0.5)
        if _ollama_running():
            print("[start] Ollama was not running, started 'ollama serve' in the background")
            return
    print("[start] WARNING: sent 'ollama serve' but ollama.exe isn't showing up yet. Check it with 'ollama list'.")


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
    _ensure_ollama()
    env = dict(os.environ)
    env["UV_PROJECT_ENVIRONMENT"] = str(VENV)
    env["REFLEX_WEB_WORKDIR"] = str(WEB)
    env.setdefault("VCNITY_HOME", str(HOME))
    env.setdefault("PYTHONIOENCODING", "utf-8")

    if _needs_sync("--sync" in sys.argv):
        print(f"[start] syncing dependencies into {VENV} (first run downloads ~2 GB)")
        subprocess.run(["uv", "sync", "--project", str(APP), "--extra", "dev"], env=env, check=True)
        SYNC_STAMP.write_text(_deps_fingerprint(), encoding="utf-8")
    else:
        print("[start] dependencies unchanged since the last sync, skipping (--sync forces it)")

    procs: list[subprocess.Popen] = []
    try:
        print("[start] API  → http://127.0.0.1:%s" % env.get("VCNITY_API_PORT", "8100"))
        procs.append(subprocess.Popen(
            ["uv", "run", "--no-sync", "--project", str(APP), "python", "-m", "api.app"], cwd=APP, env=env))
        if not api_only:
            # No wait for the API: the front end's compile takes far longer, and it only calls the API when a page is opened.
            print("[start] UI   → http://localhost:3000  (first run compiles the front end; give it a minute)")
            procs.append(subprocess.Popen(
                ["uv", "run", "--no-sync", "--project", str(APP), "reflex", "run"], cwd=APP / "ui", env=env))
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
