"""Wire Phase A safety modules into main.py.

This is a one-shot patcher. It makes three changes:
1. Adds imports for config_validator, logging_config, middleware,
   error_handler, and health at the bottom of the import block.
2. Inserts configure_logging() and validate_environment() before the
   FastAPI app is created.
3. Adds RequestContextMiddleware, error handlers, and the health router
   right after the app is created.

Safe to run multiple times: if a change is already present, it is skipped.
"""
import pathlib
import sys


def main():
    path = pathlib.Path("main.py")
    if not path.exists():
        print("ERROR: main.py not found in current directory")
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    original = text

    # --- Insertion 1: new imports after the tenant_policy import ---
    anchor_imports = (
        "from .tenant_policy import tenant_policy, capability_enabled, policy_context"
    )
    new_imports = (
        "from .config_validator import validate_environment\n"
        "from .logging_config import configure_logging\n"
        "from .middleware import RequestContextMiddleware\n"
        "from .error_handler import install_error_handlers\n"
        "from .health import router as health_router"
    )

    if anchor_imports not in text:
        print("ERROR: import anchor not found in main.py")
        print("       Expected: " + anchor_imports)
        sys.exit(1)

    if "config_validator" not in text:
        text = text.replace(
            anchor_imports,
            anchor_imports + "\n" + new_imports,
            1,
        )
        print("OK: imports inserted")
    else:
        print("SKIP: imports already present")

    # --- Insertions 2 & 3: configure_logging + app wiring ---
    anchor_app = 'app=FastAPI(title="AI Growth OS API",version="1.0.0")'

    if anchor_app not in text:
        print("ERROR: FastAPI anchor not found in main.py")
        print("       Expected: " + anchor_app)
        sys.exit(1)

    before_app = (
        "configure_logging()\n"
        "validate_environment(exit_on_failure=False)\n"
    )
    after_app = (
        "\napp.add_middleware(RequestContextMiddleware)\n"
        "install_error_handlers(app)\n"
        "app.include_router(health_router)"
    )

    if "install_error_handlers(app)" not in text:
        text = text.replace(
            anchor_app,
            before_app + anchor_app + after_app,
            1,
        )
        print("OK: app wiring inserted")
    else:
        print("SKIP: app wiring already present")

    if text == original:
        print("No changes needed. main.py is up to date.")
    else:
        path.write_text(text, encoding="utf-8")
        print("main.py updated successfully.")


if __name__ == "__main__":
    main()