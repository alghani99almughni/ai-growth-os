"""Adversarial unit tests for the SSRF-safe website fetch boundary."""
import socket

import pytest

from app import website_audit_fetcher as fetcher


def _answer(address: str):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443))


def test_dns_resolution_rejects_private_answer_even_if_public_answer_exists(monkeypatch):
    monkeypatch.setattr(
        fetcher.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [_answer("93.184.216.34"), _answer("127.0.0.1")],
    )
    with pytest.raises(fetcher.UnsafeWebsiteTarget):
        fetcher._resolve_public_addresses("example.com", 443)


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.1", "169.254.169.254", "::1",
    "fc00::1", "fe80::1", "0.0.0.0",
])
def test_dns_resolution_rejects_non_global_addresses(monkeypatch, address):
    monkeypatch.setattr(fetcher.socket, "getaddrinfo", lambda *args, **kwargs: [_answer(address)])
    with pytest.raises(fetcher.UnsafeWebsiteTarget):
        fetcher._resolve_public_addresses("example.com", 443)


def test_dns_resolution_deduplicates_public_addresses(monkeypatch):
    monkeypatch.setattr(
        fetcher.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [_answer("93.184.216.34"), _answer("93.184.216.34")],
    )
    assert fetcher._resolve_public_addresses("example.com", 443) == ["93.184.216.34"]


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "https://user:password@example.com/",
    "https://example.com:8443/",
    "https://example.com:not-a-port/",
    "https://example.com:99999/",
    "https://[not-an-ipv6-address]/",
    "https://127.0.0.1/",
])
def test_fetch_rejects_unsafe_url_before_network(monkeypatch, url):
    monkeypatch.setattr(
        fetcher.socket,
        "getaddrinfo",
        lambda *args, **kwargs: pytest.fail("unsafe URL must be rejected before DNS"),
    )
    with pytest.raises(fetcher.UnsafeWebsiteTarget):
        fetcher.fetch_public_homepage(url)


def test_pinned_connection_dials_exact_validated_ip(monkeypatch):
    calls = []
    sentinel = object()

    def fake_create_connection(address, timeout, source_address=None, socket_options=None):
        calls.append(address)
        return sentinel

    monkeypatch.setattr(fetcher.socket, "create_connection", fake_create_connection)
    connection_class = fetcher._pinned_connection_class(fetcher.HTTPConnection, "93.184.216.34")
    connection = connection_class("example.com", port=443)
    connection.timeout = 3
    connection.source_address = None
    connection.socket_options = None

    assert connection._new_conn() is sentinel
    assert calls == [("93.184.216.34", 443)]


def test_response_limit_cannot_be_increased_above_hard_limit(monkeypatch):
    monkeypatch.setattr(
        fetcher.socket,
        "getaddrinfo",
        lambda *args, **kwargs: pytest.fail("invalid byte limit must fail before DNS"),
    )
    with pytest.raises(ValueError):
        fetcher.fetch_public_homepage("https://example.com/", max_bytes=fetcher.MAX_RESPONSE_BYTES + 1)


@pytest.mark.parametrize("url", [
    "https://example.com:abc/",
    "https://example.com:99999/",
    "https://[invalid-ipv6]/",
])
def test_malformed_url_is_rejected_before_dns(monkeypatch, url):
    monkeypatch.setattr(
        fetcher.socket,
        "getaddrinfo",
        lambda *args, **kwargs: pytest.fail("malformed URL must be rejected before DNS"),
    )
    with pytest.raises(fetcher.UnsafeWebsiteTarget):
        fetcher.fetch_public_homepage(url)
