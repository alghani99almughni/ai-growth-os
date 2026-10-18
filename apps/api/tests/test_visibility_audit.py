"""Unit tests for the bounded website audit parser and URL guard."""
import pytest
from fastapi import HTTPException
from app.routes_visibility import _domain, _SEOParser

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
