"""Delete junk files created by accidental shell redirections
and *.BEFORE-* backup files.

Only deletes files inside apps/api/app/ whose names match a known list
or the pattern *.BEFORE-*. Never touches .py source files or __pycache__.
"""
import pathlib
import sys

APP = pathlib.Path(__file__).resolve().parent / "app"

JUNK = {
    "bool", "bytes", "callback_logged", "complaint_received",
    "dict", "emergency_flagged", "handoff_requested", "int",
    "JSONResponse", "list", "None", "Optional[bytes]",
    "Optional[str]", "pathlib.Path", "refund_forwarded",
    "Response", "str", "url",
}

removed = 0

for name in JUNK:
    p = APP / name
    if p.exists() and p.is_file():
        try:
            p.unlink()
            print(f"  removed {name}")
            removed += 1
        except Exception as exc:
            print(f"  failed to remove {name}: {exc}")

for p in APP.glob("*.BEFORE-*"):
    try:
        p.unlink()
        print(f"  removed {p.name}")
        removed += 1
    except Exception as exc:
        print(f"  failed to remove {p.name}: {exc}")

print()
print(f"Cleanup complete. {removed} files removed.")