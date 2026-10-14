"""Regression tests for the platform-owned external contact book.

These endpoints must deduplicate normalized identities, preserve opt-ins on import,
and reject attempts to merge two different saved contacts into one identity.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import app.routes_platform_comms as comms
from app.routes_platform_comms import (
    PlatformMarketingContactImport,
    PlatformMarketingContactInput,
    import_platform_marketing_contacts,
)


def contact(**overrides):
    values = {
        "id": "contact-1",
        "name": "Existing contact",
        "phone": "+1 555 123 4567",
        "phone_norm": "15551234567",
        "email": "existing@example.com",
        "email_norm": "existing@example.com",
        "whatsapp_opt_in": True,
        "email_opt_in": True,
        "consent_source": "web-form",
        "tags": "lead",
        "status": "active",
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def run_import(monkeypatch, db, items):
    monkeypatch.setattr(comms, "audit", lambda *args, **kwargs: None)
    return import_platform_marketing_contacts(
        PlatformMarketingContactImport(contacts=items),
        user=SimpleNamespace(id="platform-admin"),
        db=db,
    )


def test_import_deduplicates_normalized_phone_within_same_batch(monkeypatch):
    saved = contact()
    db = Mock()
    # Existing contact lookup by phone, then no matching email contact,
    # then no existing phone/email preference rows.
    db.scalar.side_effect = [saved, None, None, None]

    result = run_import(monkeypatch, db, [
        PlatformMarketingContactInput(
            name="Updated name", phone="+1 (555) 123-4567",
            email="existing@example.com", whatsapp_opt_in=True,
        ),
        PlatformMarketingContactInput(
            name="Duplicate row", phone="15551234567",
            email="duplicate@example.com", email_opt_in=True,
        ),
    ])

    assert result == {"imported": 0, "updated": 1, "rejected": [{"row": 2, "reason": "duplicate_in_import"}]}
    assert saved.name == "Updated name"
    db.commit.assert_called_once()


def test_import_never_clears_existing_channel_opt_in(monkeypatch):
    saved = contact()
    db = Mock()
    db.scalar.side_effect = [saved, None]

    result = run_import(monkeypatch, db, [
        PlatformMarketingContactInput(email="existing@example.com")
    ])

    assert result["updated"] == 1
    assert saved.whatsapp_opt_in is True
    assert saved.email_opt_in is True
    db.commit.assert_called_once()


def test_import_rejects_phone_and_email_that_belong_to_different_contacts(monkeypatch):
    phone_match = contact(id="phone-owner", email=None, email_norm=None)
    email_match = contact(id="email-owner", phone=None, phone_norm=None)
    db = Mock()
    db.scalar.side_effect = [phone_match, email_match]

    result = run_import(monkeypatch, db, [
        PlatformMarketingContactInput(
            phone="+1 555 123 4567", email="someone@example.com"
        )
    ])

    assert result["imported"] == 0
    assert result["updated"] == 0
    assert result["rejected"] == [{
        "row": 1, "reason": "phone_and_email_belong_to_different_contacts"
    }]
    db.commit.assert_called_once()
