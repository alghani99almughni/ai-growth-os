"""External watchdog for the API server.

Runs as a separate process. Every 30 seconds it pings /health. If the server
fails twice in a row, it kills the current uvicorn process and restarts it.

Restart limit: 3 per hour. Beyond that, the watchdog stops trying and writes
a MonitoringAlert row so the next healthy run of the app reports it.

Run it in a SEPARATE terminal from uvicorn:

    cd apps/api
    python watchdog.py

Use Windows Task Scheduler for auto-start on boot (see SERVER_SETUP.md).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timedelta
from pathlib import Path

HEALTH_URL = "http://127.0.0.1:8000/health"
CHECK_INTERVAL_SECONDS = 30
FAILURE_THRESHOLD = 2                # consecutive failures before restart
MAX_RESTARTS_PER_HOUR = 3

API_DIR = Path(__file__).resolve().parent
PYTHON = sys.executable or "python"

_uvicorn_proc: subprocess.Popen | None = None
_restart_times: list[datetime] = []


def log(msg: str) -> None:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[watchdog {ts}] {msg}", flush=True)


def check_health() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=5) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def kill_uvicorn() -> None:
    """Kill any python.exe running uvicorn by port. Best-effort."""
    try:
        subprocess.run(
            ["taskkill", "/F", "/FI", "IMAGENAME eq python.exe"],
            capture_output=True,
        )
        time.sleep(2)
    except Exception as exc:
        log(f"kill failed: {exc}")


def start_uvicorn() -> None:
    global _uvicorn_proc
    log("starting uvicorn")
    logfile = API_DIR / "uvicorn.log"
    with open(logfile, "ab") as fh:
        _uvicorn_proc = subprocess.Popen(
            [PYTHON, "-m", "uvicorn", "app.main:app",
             "--host", "0.0.0.0", "--port", "8000"],
            cwd=str(API_DIR),
            stdout=fh,
            stderr=fh,
        )
    log(f"uvicorn pid = {_uvicorn_proc.pid}")


def should_restart() -> bool:
    """Rate-limit restarts to MAX_RESTARTS_PER_HOUR."""
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=1)
    while _restart_times and _restart_times[0] < cutoff:
        _restart_times.pop(0)
    return len(_restart_times) < MAX_RESTARTS_PER_HOUR


def queue_alert_row(title: str, body: str) -> None:
    """Write a MonitoringAlert row directly, so the app picks it up on next boot."""
    try:
        os.chdir(str(API_DIR))
        from app.db import SessionLocal
        from app.models_monitoring import MonitoringAlert
        db = SessionLocal()
        try:
            db.add(MonitoringAlert(
                id=str(uuid.uuid4()),
                severity="critical",
                component="watchdog",
                title=title,
                body=body,
            ))
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        log(f"could not queue alert: {exc}")


def main() -> None:
    log("watchdog starting")
    log(f"health url  = {HEALTH_URL}")
    log(f"check every = {CHECK_INTERVAL_SECONDS}s")
    log(f"restart limit = {MAX_RESTARTS_PER_HOUR}/hour")

    # If uvicorn isn't already running, start it
    if not check_health():
        log("uvicorn not reachable — starting it")
        start_uvicorn()
        time.sleep(8)

    consecutive_failures = 0

    while True:
        time.sleep(CHECK_INTERVAL_SECONDS)
        healthy = check_health()

        if healthy:
            if consecutive_failures > 0:
                log(f"recovered after {consecutive_failures} failures")
            consecutive_failures = 0
            continue

        consecutive_failures += 1
        log(f"health check failed ({consecutive_failures}/{FAILURE_THRESHOLD})")

        if consecutive_failures < FAILURE_THRESHOLD:
            continue

        if not should_restart():
            log("restart limit reached — not restarting")
            queue_alert_row(
                "Watchdog restart limit reached",
                f"Server failed health check {consecutive_failures} times in a row "
                f"and has already been restarted {MAX_RESTARTS_PER_HOUR} times in the last hour.",
            )
            consecutive_failures = 0
            time.sleep(600)
            continue

        log("restarting uvicorn")
        kill_uvicorn()
        start_uvicorn()
        _restart_times.append(datetime.utcnow())
        consecutive_failures = 0
        time.sleep(15)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("watchdog stopped by user")