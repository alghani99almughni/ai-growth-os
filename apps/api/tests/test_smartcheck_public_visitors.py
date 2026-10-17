"""Tests for the SQL-backed public visitor registration contract."""
import json
from unittest.mock import Mock

import app.routes_smartcheck_public as public_routes
from app.routes_smartcheck_public import PublicVisitorRequest


def test_public_request_schema_accepts_qr_form_fields():
    body = PublicVisitorRequest(
        visitor_name=" Guest ", visitor_mobile="+919876543210",
        purpose="Meeting", destination="Reception", vehicle_number="ts09ab1234",
    )
    assert body.visitor_name == " Guest "
    assert body.visitor_mobile == "+919876543210"
    assert body.destination == "Reception"


def test_public_registration_feature_is_opt_in_by_default():
    db = Mock()
    db.scalar.side_effect = [None, None]
    assert public_routes._tenant_feature_enabled(db, "tenant-uuid") is False


def test_public_registration_feature_can_be_enabled_for_tenant():
    db = Mock()
    db.scalar.side_effect = [
        type("Setting", (), {"value_json": json.dumps({"security_visitor_management": True})})(),
        None,
    ]
    assert public_routes._tenant_feature_enabled(db, "tenant-uuid") is True


def test_public_registration_does_not_expose_legacy_bridge_helpers():
    # Public visitor registration writes to the platform's SQL database; it must
    # not depend on Apps Script credentials, redirects, or a Google Sheet ticket.
    assert not hasattr(public_routes, "_submit_to_smartcheck")
    assert not hasattr(public_routes, "_script_config")
    assert not hasattr(public_routes, "_require_lifecycle_ready")
