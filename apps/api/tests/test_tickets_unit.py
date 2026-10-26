from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import app.tickets as tickets
import app.operational_alerts as operational_alerts


class FakeTicket:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.__dict__.setdefault("assigned_to", None)
        self.__dict__.setdefault("resolved_at", None)
        self.__dict__.setdefault("resolved_by", None)


class FakeDB:
    def __init__(self, existing=None):
        self.added = []
        self.existing = existing
        self.commits = 0

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commits += 1

    def refresh(self, row):
        if not getattr(row, "id", None):
            row.id = "ticket-1"

    def rollback(self):
        pass


def test_create_ticket_normalizes_category_priority_and_starts_sla(monkeypatch):
    monkeypatch.setattr(operational_alerts, "create_operational_alerts", lambda *args, **kwargs: 0)
    monkeypatch.setattr(tickets, "_model", lambda: FakeTicket)
    monkeypatch.setattr(tickets, "_compute_sla_hours", lambda db, category: 4)
    db = FakeDB()

    result = tickets.create_ticket(
        db,
        tenant_id="tenant-a",
        subject="  Booking help  ",
        body="details",
        category="UNKNOWN",
        priority="UNKNOWN",
        created_by="user-a",
    )

    row = db.added[0]
    assert row.tenant_id == "tenant-a"
    assert row.subject == "Booking help"
    assert row.category == "support"
    assert row.priority == "normal"
    assert row.status == "new"
    assert row.sla_hours == 4
    assert row.sla_due_at > row.created_at
    assert result["tenant_id"] == "tenant-a"
    assert db.commits == 1


def test_create_ticket_rejects_blank_subject_without_persisting(monkeypatch):
    monkeypatch.setattr(tickets, "_model", lambda: FakeTicket)
    db = FakeDB()

    with pytest.raises(ValueError, match="subject is required"):
        tickets.create_ticket(db, tenant_id="tenant-a", subject="   ")

    assert db.added == []
    assert db.commits == 0


def test_resolved_ticket_is_not_sla_breached():
    old = datetime.utcnow() - timedelta(hours=2)
    ticket = SimpleNamespace(status="resolved", sla_due_at=old)
    assert tickets._is_breached(ticket) is False


def test_open_ticket_past_due_is_sla_breached():
    old = datetime.utcnow() - timedelta(hours=2)
    ticket = SimpleNamespace(status="in_progress", sla_due_at=old)
    assert tickets._is_breached(ticket) is True


def test_ticket_reply_reopens_resolved_ticket_for_tenant_followup(monkeypatch):
    monkeypatch.setattr(operational_alerts, "create_operational_alerts", lambda *args, **kwargs: 0)
    row = FakeTicket(
        id="ticket-1",
        tenant_id="tenant-a",
        subject="Booking help",
        body="original",
        category="support",
        priority="normal",
        status="resolved",
        sla_hours=24,
        sla_due_at=datetime.utcnow() + timedelta(hours=1),
        sla_breached=False,
        assigned_to=None,
        created_by="user-a",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        resolved_at=datetime.utcnow(),
        resolved_by="support-user",
    )
    monkeypatch.setattr(tickets, "_model", lambda: FakeTicket)

    class ReplyDB(FakeDB):
        def get(self, model, ticket_id):
            assert ticket_id == "ticket-1"
            return row

    db = ReplyDB()
    result = tickets.reply(db, "ticket-1", "It is still happening", from_tenant=True, actor_id="user-a")

    assert row.status == "acknowledged"
    assert "Tenant" in row.body
    assert "It is still happening" in row.body
    assert result["status"] == "acknowledged"
    assert db.commits == 1
