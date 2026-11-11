#!/usr/bin/env python3
"""Block until the deployed API reports the expected git commit on /health (or time out).

Env: API_URL (required), EXPECTED_COMMIT (required), WAIT_SECONDS (default 600), POLL_SECONDS (default 8).
Exit 0 when the commit matches, 1 on timeout. Render's zero-downtime deploys keep the old instance answering
until the new one is live, so we must wait for the commit to change instead of trusting the first 200.
"""
import os
import sys
import time

import requests

base = os.environ["API_URL"].rstrip("/")
expected = os.environ["EXPECTED_COMMIT"].strip()
deadline = time.time() + int(os.environ.get("WAIT_SECONDS", "600"))
poll = int(os.environ.get("POLL_SECONDS", "8"))
seen = None

while time.time() < deadline:
    try:
        r = requests.get(base + "/health", timeout=15)
        r.raise_for_status()
        got = str(r.json().get("commit", "")).strip()
        if got != seen:
            print("DEPLOYED_COMMIT", got or "<missing>", "expected", expected, flush=True)
            seen = got
        if got and got != "unknown" and (got == expected or got.startswith(expected) or expected.startswith(got)):
            print("Deployment is live.")
            sys.exit(0)
    except (requests.RequestException, ValueError) as exc:   # cold start, mid-deploy, bad JSON: keep waiting
        print("HEALTH_RETRY", type(exc).__name__, str(exc)[:120], flush=True)
    time.sleep(poll)

sys.exit(f"Timed out waiting for commit {expected}; last seen {seen!r}. "
         "If this is empty, /health does not report RENDER_GIT_COMMIT.")
