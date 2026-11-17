"""Regression coverage for visibility result transaction recovery."""
from types import SimpleNamespace

import app.main  # noqa: F401
from app.routes_visibility import _commit_visibility_result


class _CommitFailOnceDB:
    def __init__(self, run):
        self.run = run
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1
        if self.commits == 1:
            raise RuntimeError("simulated database commit failure")

    def rollback(self):
        self.rollbacks += 1

    def get(self, model, run_id):
        assert run_id == self.run.id
        return self.run


def test_failed_result_commit_recovers_persisted_run_as_failed():
    run = SimpleNamespace(id="run-1", status="completed", error_code=None, completed_at=None)
    db = _CommitFailOnceDB(run)

    assert _commit_visibility_result(db, run) is True
    assert db.rollbacks == 1
    assert db.commits == 2
    assert run.status == "failed"
    assert run.error_code == "result_persistence_failed"
    assert run.completed_at is not None


def test_failed_recovery_commit_returns_false_without_claiming_success():
    run = SimpleNamespace(id="run-2", status="completed", error_code=None, completed_at=None)

    class AlwaysFailDB(_CommitFailOnceDB):
        def commit(self):
            self.commits += 1
            raise RuntimeError("database unavailable")

    db = AlwaysFailDB(run)
    assert _commit_visibility_result(db, run) is False
    assert db.rollbacks == 2
