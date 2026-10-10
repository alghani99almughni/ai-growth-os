from contextlib import contextmanager

from app.conversation_state_migration import ensure_conversation_state_capacity


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeConnection:
    def __init__(self, lengths):
        self.lengths = iter(lengths)
        self.statements = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        if "SELECT character_maximum_length" in sql:
            return FakeResult(next(self.lengths))
        return FakeResult(None)


class FakeEngine:
    def __init__(self, dialect_name, connection):
        self.dialect = type("Dialect", (), {"name": dialect_name})()
        self.connection = connection

    @contextmanager
    def begin(self):
        yield self.connection


def test_widens_all_existing_workflow_state_columns_to_255():
    connection = FakeConnection([60, 60, 120])
    ensure_conversation_state_capacity(FakeEngine("postgresql", connection))

    alters = [sql for sql, _ in connection.statements if sql.startswith("ALTER TABLE")]
    assert alters == [
        "ALTER TABLE conversations ALTER COLUMN state TYPE VARCHAR(255)",
        "ALTER TABLE call_turns ALTER COLUMN state_before TYPE VARCHAR(255)",
        "ALTER TABLE call_turns ALTER COLUMN state_after TYPE VARCHAR(255)",
    ]


def test_skips_missing_or_already_wide_columns():
    connection = FakeConnection([None, 255, 500])
    ensure_conversation_state_capacity(FakeEngine("postgresql", connection))

    assert not [sql for sql, _ in connection.statements if sql.startswith("ALTER TABLE")]


def test_non_postgres_database_needs_no_capacity_ddl():
    connection = FakeConnection([])
    ensure_conversation_state_capacity(FakeEngine("sqlite", connection))

    assert connection.statements == []
