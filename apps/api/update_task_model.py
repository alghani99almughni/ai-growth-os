"""Add duration_minutes and all_day to PlatformTask model."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MODELS = HERE / "app" / "models_growth.py"

if not MODELS.exists():
    print("ERROR: models_growth.py not found")
    sys.exit(1)

text = MODELS.read_text(encoding="utf-8")

if "duration_minutes" in text and "all_day" in text and "class PlatformTask" in text:
    print("SKIP: fields already present")
    sys.exit(0)

old = "    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)\n\n\nclass PlatformSetting"
new = "    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)\n    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)\n    all_day: Mapped[bool] = mapped_column(Boolean, default=False)\n\n\nclass PlatformSetting"

if old not in text:
    print("ERROR: PlatformTask tail anchor not found")
    print("Search models_growth.py for the PlatformTask class and manually add:")
    print("  duration_minutes: Mapped[int] = mapped_column(Integer, default=30)")
    print("  all_day: Mapped[bool] = mapped_column(Boolean, default=False)")
    sys.exit(1)

text = text.replace(old, new, 1)
MODELS.write_text(text, encoding="utf-8")
print("PlatformTask model updated with duration_minutes + all_day")