"""Fix the runaway signal handler in hardening.py.

The old handler didn't exit, so SIGTERM re-fired indefinitely. This
replaces it with a version that disposes resources once, then exits.
Second Ctrl+C forces an immediate exit.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
HARDENING = HERE / "app" / "hardening.py"

if not HARDENING.exists():
    print("ERROR: app/hardening.py not found. Run from apps/api.")
    sys.exit(1)

text = HARDENING.read_text(encoding="utf-8")

if "_shutting_down" in text:
    print("SKIP: signal handler already fixed")
    sys.exit(0)

# Find the install_signal_handlers function and replace its body
start = text.find("def install_signal_handlers(app)")
if start < 0:
    print("ERROR: install_signal_handlers not found")
    sys.exit(1)

# Find the end of the function (next top-level def or end of file)
end = text.find("\ndef ", start + 10)
if end < 0:
    end = len(text)

NEW = '''def install_signal_handlers(app) -> None:
    """Close DB pool and Redis on SIGTERM. Render sends SIGTERM on deploy.

    Second SIGTERM forces an immediate exit so a stuck process cannot loop.
    """
    _shutting_down = {"v": False}

    def _shutdown(signum=None, frame=None):
        if _shutting_down["v"]:
            import sys as _sys
            _sys.exit(1)
        _shutting_down["v"] = True
        logger.info("SIGTERM received - closing resources")
        try:
            from .db import engine
            engine.dispose()
            logger.info("DB engine disposed")
        except Exception as exc:
            logger.debug("engine.dispose failed: %s", exc)
        try:
            from .config import settings
            if settings.redis_url:
                import redis
                redis.Redis.from_url(settings.redis_url).close()
        except Exception:
            pass
        import sys as _sys
        _sys.exit(0)

    import signal as _sig
    for sig in (_sig.SIGTERM, _sig.SIGINT):
        try:
            _sig.signal(sig, _shutdown)
        except Exception:
            pass

'''

text = text[:start] + NEW + text[end:]
HARDENING.write_text(text, encoding="utf-8")
print("Signal handler fixed.")
print(f"hardening.py now {len(text)} bytes.")