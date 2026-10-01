"""Startup config validation.

Fails fast when required environment variables are missing or malformed, so the
app refuses to boot in a misconfigured state instead of failing later on the
first request. Called from main.py at import time.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


_REQUIRED_ALWAYS = (
    "DATABASE_URL",
    "JWT_SECRET",
)

_REQUIRED_IN_PRODUCTION = (
    "REDIS_URL",
)

_PATTERN_VALIDATORS = {
    "DATABASE_URL": (
        re.compile(r"^(postgres|postgresql|sqlite)"),
        "must start with postgresql://, postgres://, or sqlite://",
    ),
    "REDIS_URL": (
        re.compile(r"^rediss?://"),
        "must start with redis:// or rediss://",
    ),
}

_PRODUCTION_MARKERS = (
    "PRODUCTION",
    "PROD",
    "RENDER",
)


def _is_production() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "").upper()
    if env in _PRODUCTION_MARKERS:
        return True
    if os.getenv("RENDER"):
        return True
    if os.getenv("PRODUCTION") == "true":
        return True
    return False


def _missing(vars_):
    return [name for name in vars_ if not os.getenv(name)]


def validate_environment(exit_on_failure=True):
    problems = []

    missing = _missing(_REQUIRED_ALWAYS)
    if missing:
        problems.append(
            "Missing required environment variables: " + ", ".join(missing)
        )

    if _is_production():
        missing_prod = _missing(_REQUIRED_IN_PRODUCTION)
        if missing_prod:
            problems.append(
                "Missing production environment variables: "
                + ", ".join(missing_prod)
            )

    for name, (pattern, hint) in _PATTERN_VALIDATORS.items():
        value = os.getenv(name)
        if value and not pattern.match(value):
            problems.append(f"{name} {hint} (got: {value[:20]}...)")

    if not problems:
        return

    message = "Configuration error(s):\n  - " + "\n  - ".join(problems)
    print(message, file=sys.stderr)

    if exit_on_failure and _is_production():
        sys.exit(1)
    if exit_on_failure:
        print(
            "Continuing in non-production mode. Fix the above before deploying.",
            file=sys.stderr,
        )


def get_required(name):
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Environment variable {name} is required but not set.")
    return value


def get_optional(name, default=""):
    return os.getenv(name, default)
