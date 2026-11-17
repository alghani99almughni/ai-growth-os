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


def test_website_audit_uses_connection_pinned_fetcher_and_persists_findings(monkeypatch):
    from types import SimpleNamespace
    from app.models_visibility import VisibilityAudit, VisibilityAuditFinding

    monkeypatch.setattr(visibility_routes, "_authorize", lambda user, tenant_id: None)
    captured = {}
    html = (
        '<html><head><title>Example Company</title>'
        '<meta name="description" content="Local service">'
        '<link rel="canonical" href="https://example.com/">'
        '<script type="application/ld+json">{}</script></head>'
        '<body><h1>Welcome</h1></body></html>'
    ).encode()

    class FakeDB:
        def __init__(self):
            self.rows = []
        def scalar(self, statement):
            return SimpleNamespace(primary_domain="example.com")
        def add(self, row):
            self.rows.append(row)
        def flush(self):
            for row in self.rows:
                if isinstance(row, VisibilityAudit) and not row.id:
                    row.id = "audit-test"
        def commit(self):
            pass
        def refresh(self, row):
            pass

    fake_response = SimpleNamespace(
        status=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
        body=html,
    )
    def fake_fetch(url):
        captured["url"] = url
        return fake_response

    monkeypatch.setattr(visibility_routes, "fetch_public_homepage", fake_fetch)
    db = FakeDB()
    result = run_website_audit("tenant-test", user=object(), db=db)

    assert captured["url"] == "https://example.com/"
    assert result["status"] == "completed"
    assert result["pages_checked"] == 1
    assert result["http_status"] == 200
    assert result["scope"].startswith("Single homepage only")
    assert any(isinstance(row, VisibilityAudit) for row in db.rows)
    assert any(isinstance(row, VisibilityAuditFinding) for row in db.rows)


def test_website_audit_rejects_fetcher_security_failure(monkeypatch):
    from app.website_audit_fetcher import UnsafeWebsiteTarget

    monkeypatch.setattr(visibility_routes, "_authorize", lambda user, tenant_id: None)
    class FakeDB:
        def scalar(self, statement):
            return type("Brand", (), {"primary_domain": "example.com"})()

    def unsafe_fetch(url):
        raise UnsafeWebsiteTarget("private target")

    monkeypatch.setattr(visibility_routes, "fetch_public_homepage", unsafe_fetch)
    with pytest.raises(HTTPException) as exc:
        run_website_audit("tenant-test", user=object(), db=FakeDB())
    assert exc.value.status_code == 422
    assert "security checks" in exc.value.detail
