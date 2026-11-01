"""Unit tests for the bounded website audit parser and URL guard."""
# Import the application first because routes_visibility currently reuses dependencies from app.main.
# This mirrors the production import order and avoids initializing the router before main.py.
import app.main  # noqa: F401
import pytest
from fastapi import HTTPException
import app.routes_visibility as visibility_routes
from app.routes_visibility import _domain, _SEOParser, _read_bounded_body, run_website_audit

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
    "169.254.169.254", "http://[::1]",
])
def test_domain_rejects_unsafe_or_invalid_inputs(value):
    with pytest.raises(HTTPException):
        _domain(value)

def test_seo_parser_extracts_basic_metadata():
    parser = _SEOParser()
    parser.feed('<html><head><title>Example Company</title><meta name="description" content="Local service"><link rel="canonical" href="https://example.com/"></head><body><h1>Welcome</h1><script type="application/ld+json">{}</script></body></html>')
    assert "Example Company" == " ".join(parser.title_parts).strip()
    assert parser.description == "Local service"
    assert parser.canonical == "https://example.com/"
    assert parser.h1_count == 1
    assert parser.structured_data is True

def test_seo_parser_detects_noindex():
    parser = _SEOParser()
    parser.feed('<meta name="robots" content="noindex,follow">')
    assert "noindex" in parser.robots

class _FakeResponse:
    def __init__(self, chunks):
        self._chunks = chunks

    def iter_bytes(self):
        yield from self._chunks


def test_bounded_body_accepts_content_at_limit():
    assert _read_bounded_body(_FakeResponse([b"abc", b"def"]), max_bytes=6) == b"abcdef"


def test_bounded_body_rejects_content_over_limit():
    with pytest.raises(HTTPException) as exc:
        _read_bounded_body(_FakeResponse([b"abc", b"def"]), max_bytes=5)
    assert exc.value.status_code == 422
    assert "5-byte audit limit" in exc.value.detail


def test_website_audit_api_is_blocked_before_outbound_fetch(monkeypatch):
    # Even direct backend invocation must fail closed while SSRF-safe fetching
    # is unfinished. If the route proceeds, it would try to query the database
    # for a brand; the test intentionally supplies no usable database.
    monkeypatch.setattr(visibility_routes, "_authorize", lambda user, tenant_id: None)
    with pytest.raises(HTTPException) as exc:
        run_website_audit("tenant-test", user=object(), db=None)
    assert exc.value.status_code == 503
    assert "disabled pending security hardening" in exc.value.detail
