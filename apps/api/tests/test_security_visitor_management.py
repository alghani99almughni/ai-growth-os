"""Focused tests for security module entitlement and tenant isolation."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.routes_security import PassInput, VisitorRequestInput, tenant_access


def test_pass_input_accepts_supported_industry():
    body = PassInput(visitor_name="Guest", industry="school")
    assert body.industry == "school"
    assert body.needs_approval is True


def test_ai_request_has_no_approval_override():
    body = VisitorRequestInput(visitor_name="Guest", purpose="Parent meeting")
    assert body.visitor_name == "Guest"
    assert not hasattr(body, "needs_approval")


def test_regular_user_cannot_select_another_tenant():
    db = Mock()
    user = SimpleNamespace(tenant_id="tenant-a", role="owner")
    with pytest.raises(HTTPException) as exc:
        tenant_access("tenant-b", user, db)
    assert exc.value.status_code == 403
    db.get.assert_not_called()


def test_security_module_is_opt_in_when_no_feature_configured():
    db = Mock()
    db.get.return_value = SimpleNamespace(status="active")
    db.scalar.return_value = None
    user = SimpleNamespace(tenant_id="tenant-a", role="owner")
    with pytest.raises(HTTPException) as exc:
        tenant_access("tenant-a", user, db)
    assert exc.value.status_code == 403
    assert "disabled" in exc.value.detail.lower()


def test_platform_admin_still_requires_module_enabled_for_target_tenant():
    db = Mock()
    db.get.return_value = SimpleNamespace(status="active")
    db.scalar.side_effect = [
        SimpleNamespace(value_json=json.dumps({"security_visitor_management": True})),
        None,
    ]
    user = SimpleNamespace(tenant_id="platform-tenant", role="platform_admin")
    tenant_access("tenant-a", user, db)
