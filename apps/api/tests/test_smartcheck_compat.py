"""Tests for safe SmartCheck / Google Sheets migration compatibility."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

import app.routes_security as security
from app.routes_security import (
    SmartCheckLegacyTicket,
    SmartCheckMigrationInput,
    _validate_smartcheck_url,
    migrate_smartcheck_pending,
)


def test_smartcheck_url_accepts_only_https_google_apps_script_deployments():
    assert _validate_smartcheck_url(
        "https://script.google.com/macros/s/abc123/exec"
    ) == "https://script.google.com/macros/s/abc123/exec"


@pytest.mark.parametrize("url", [
    "http://script.google.com/macros/s/abc/exec",
    "https://example.com/macros/s/abc/exec",
    "https://script.google.com/anything",
    "https://script.google.com/macros/s/abc/exec?url=https://example.com",
    "https://user:pass@script.google.com/macros/s/abc/exec",
])
def test_smartcheck_url_rejects_non_google_or_unsafe_targets(url):
    with pytest.raises(HTTPException) as exc:
        _validate_smartcheck_url(url)
    assert exc.value.status_code == 422


def test_migration_imports_pending_pass_as_pending_and_requires_human_approval(monkeypatch):
    monkeypatch.setattr(security, "tenant_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(security, "admin_only", lambda *args, **kwargs: None)
    monkeypatch.setattr(security, "_site_for_tenant", lambda *args, **kwargs: None)
    db = Mock()
    db.get.return_value = None
    user = SimpleNamespace(id="admin-1", role="owner")

    result = migrate_smartcheck_pending(
        "tenant-a",
        SmartCheckMigrationInput(tickets=[
            SmartCheckLegacyTicket(
                ticket_id="GP-100",
                tenant_id="tenant-a",
                visitor_name="Guest",
                status="PENDING_APPROVAL",
            )
        ]),
        user=user,
        db=db,
    )

    assert result["imported"] == 1
    assert result["duplicates"] == 0
    assert result["rejected"] == []
    assert result["created"][0]["source_ticket_id"] == "GP-100"
    assert result["created"][0]["qr_token"]
    added_pass = db.add.call_args_list[0].args[0]
    assert added_pass.status == "pending"
    assert added_pass.tenant_id == "tenant-a"
    db.commit.assert_called_once()


def test_migration_rejects_cross_tenant_and_already_approved_legacy_rows(monkeypatch):
    monkeypatch.setattr(security, "tenant_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(security, "admin_only", lambda *args, **kwargs: None)
    db = Mock()
    user = SimpleNamespace(id="admin-1", role="owner")

    result = migrate_smartcheck_pending(
        "tenant-a",
        SmartCheckMigrationInput(tickets=[
            SmartCheckLegacyTicket(
                ticket_id="GP-200", tenant_id="tenant-b",
                visitor_name="Cross-tenant", status="PENDING_APPROVAL",
            ),
            SmartCheckLegacyTicket(
                ticket_id="GP-201", tenant_id="tenant-a",
                visitor_name="Already approved", status="APPROVED",
            ),
        ]),
        user=user,
        db=db,
    )

    assert result["imported"] == 0
    assert [item["reason"] for item in result["rejected"]] == [
        "tenant_mismatch", "non_pending_requires_manual_reconciliation"
    ]
    db.get.assert_not_called()
    db.commit.assert_called_once()


def test_migration_is_idempotent_for_existing_deterministic_pass_id(monkeypatch):
    import uuid
    monkeypatch.setattr(security, "tenant_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(security, "admin_only", lambda *args, **kwargs: None)
    db = Mock()
    db.get.return_value = SimpleNamespace(id="already-imported")
    user = SimpleNamespace(id="admin-1", role="owner")
    ticket_id = "GP-300"

    result = migrate_smartcheck_pending(
        "tenant-a",
        SmartCheckMigrationInput(tickets=[
            SmartCheckLegacyTicket(
                ticket_id=ticket_id, tenant_id="tenant-a",
                visitor_name="Duplicate", status="PENDING",
            )
        ]),
        user=user,
        db=db,
    )

    assert result["imported"] == 0
    assert result["duplicates"] == 1
    assert result["created"] == []
    expected_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"aigrowthos:smartcheck:tenant-a:{ticket_id}"))
    db.get.assert_called_once()
    assert db.get.call_args.args[1] == expected_id
