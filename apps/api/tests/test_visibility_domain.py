"""Unit tests for safe public-domain input validation."""
# Import application first because visibility routes reuse dependencies from app.main.
import app.main  # noqa: F401
import pytest
from fastapi import HTTPException
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
    import app.routes_visibility as visibility
    monkeypatch.setattr(visibility.socket, "getaddrinfo", lambda *args, **kwargs: _dns_answer(address))
    with pytest.raises(HTTPException):
        visibility._validated_public_url("https://example.com")


def test_public_url_accepts_public_dns_answer_and_removes_fragment(monkeypatch):
    import app.routes_visibility as visibility
    monkeypatch.setattr(visibility.socket, "getaddrinfo", lambda *args, **kwargs: _dns_answer("93.184.216.34"))
    assert visibility._validated_public_url("https://example.com/path?q=1#fragment") == "https://example.com/path?q=1"


def test_public_url_reports_dns_resolution_failure(monkeypatch):
    import app.routes_visibility as visibility
    monkeypatch.setattr(visibility.socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(visibility.socket.gaierror()))
    with pytest.raises(HTTPException, match="could not be resolved"):
        visibility._validated_public_url("https://example.com")
