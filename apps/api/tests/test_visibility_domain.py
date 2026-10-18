"""Unit tests for safe public-domain input validation."""
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
