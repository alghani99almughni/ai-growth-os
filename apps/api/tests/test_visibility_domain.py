"""Unit tests for safe public-domain input validation and tenant authorization."""
# Import application first because visibility routes reuse dependencies from app.main.
import app.main  # noqa: F401
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
import app.routes_visibility as visibility
from app.routes_visibility import _domain

@pytest.mark.parametrize("value,expected", [
    ("example.com", "example.com"),
    ("https://www.example.com/path", "www.example.com"),
    ("http://example.org", "example.org"),
])
def test_domain_normalizes_public_domains(value, expected):
    assert _domain(value) == expected

@pytest.mark.parametrize("value", [
    "", "localhost", "localhost:8000", "127.0.0.1", "http://user:pass@example.com",
    "ftp://example.com", "https://example.com:8443", "https://example..com",
])
def test_domain_rejects_unsafe_or_invalid_inputs(value):
    with pytest.raises(HTTPException):
        _domain(value)


def _dns_answer(address):
    return [(None, None, None, None, (address, 443))]

@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.4", "172.16.0.1", "192.168.1.2",
    "169.254.169.254", "::1", "fc00::1", "fe80::1",
])
def test_public_url_rejects_private_or_reserved_dns_answers(monkeypatch, address):
    monkeypatch.setattr(visibility.socket, "getaddrinfo", lambda *args, **kwargs: _dns_answer(address))
    with pytest.raises(HTTPException):
        visibility._validated_public_url("https://example.com")


def test_public_url_accepts_public_dns_answer_and_removes_fragment(monkeypatch):
    monkeypatch.setattr(visibility.socket, "getaddrinfo", lambda *args, **kwargs: _dns_answer("93.184.216.34"))
    assert visibility._validated_public_url("https://example.com/path?q=1#fragment") == "https://example.com/path?q=1"


def test_public_url_reports_dns_resolution_failure(monkeypatch):
    monkeypatch.setattr(visibility.socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(visibility.socket.gaierror()))
    with pytest.raises(HTTPException, match="could not be resolved"):
        visibility._validated_public_url("https://example.com")


@pytest.mark.parametrize("role", ["customer", "tenant_admin", "staff"])
def test_authorize_rejects_cross_tenant_access(monkeypatch, role):
    monkeypatch.setattr(visibility, "require_tenant", lambda user, tenant_id: None)
    user = SimpleNamespace(role=role, tenant_id="tenant-a")
    with pytest.raises(HTTPException) as exc:
        visibility._authorize(user, "tenant-b")
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["platform_admin", "super_admin"])
def test_authorize_allows_platform_admin_roles(monkeypatch, role):
    monkeypatch.setattr(visibility, "require_tenant", lambda user, tenant_id: None)
    user = SimpleNamespace(role=role, tenant_id="tenant-a")
    visibility._authorize(user, "tenant-b")


def test_authorize_calls_existing_tenant_guard(monkeypatch):
    calls = []
    monkeypatch.setattr(visibility, "require_tenant", lambda user, tenant_id: calls.append((user, tenant_id)))
    user = SimpleNamespace(role="customer", tenant_id="tenant-a")
    with pytest.raises(HTTPException):
        visibility._authorize(user, "tenant-b")
    assert calls == [(user, "tenant-b")]
