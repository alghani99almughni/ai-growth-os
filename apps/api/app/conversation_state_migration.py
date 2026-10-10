"""Safe PostgreSQL schema migration for conversation workflow state values."""

from sqlalchemy import text


def ensure_conversation_state_capacity(engine) -> None:
    """Widen conversations.state so workflow states containing UUIDs never truncate.

    PostgreSQL enforces VARCHAR length. SQLite does not enforce VARCHAR limits, so no
    SQLite DDL is needed for local/unit-test databases.
    """
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        current_length = connection.execute(text(
            "SELECT character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'conversations' AND column_name = 'state'"
        )).scalar_one_or_none()
        if current_length is None:
            # The table may not exist in a fresh/test database yet; metadata creation
            # will create it with the updated VARCHAR(255) model definition.
            return
        if current_length < 255:
            connection.execute(text(
                "ALTER TABLE conversations ALTER COLUMN state TYPE VARCHAR(255)"
            ))
