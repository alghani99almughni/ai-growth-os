"""Safe PostgreSQL capacity migration for dynamically generated workflow state values.

Only workflow-state columns that store generated identifiers are widened here.
Human-facing text already uses TEXT in the models; fixed identifiers and validated
business fields keep their intentional limits.
"""

from sqlalchemy import text


# Explicit allowlist: these fields contain workflow state strings, sometimes with UUIDs.
_STATE_COLUMNS = (
    ("conversations", "state"),
    ("call_turns", "state_before"),
    ("call_turns", "state_after"),
)
_TARGET_LENGTH = 255


def ensure_conversation_state_capacity(engine) -> None:
    """Widen known workflow-state columns without rewriting data.

    PostgreSQL enforces VARCHAR limits. SQLite does not enforce VARCHAR length limits,
    so no SQLite DDL is needed for local/unit-test databases. Missing tables/columns
    are skipped because fresh installations may not have created optional tables yet.
    """
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        for table_name, column_name in _STATE_COLUMNS:
            current_length = connection.execute(
                text(
                    "SELECT character_maximum_length "
                    "FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = :table_name AND column_name = :column_name"
                ),
                {"table_name": table_name, "column_name": column_name},
            ).scalar_one_or_none()

            if current_length is None or current_length >= _TARGET_LENGTH:
                continue

            # Identifiers are selected only from the constant allowlist above.
            connection.execute(
                text(
                    f"ALTER TABLE {table_name} ALTER COLUMN {column_name} "
                    f"TYPE VARCHAR({_TARGET_LENGTH})"
                )
            )
