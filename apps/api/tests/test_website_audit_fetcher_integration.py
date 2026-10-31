"""Mocked integration tests for the pinned fetcher's HTTP/TLS boundary."""
from app import website_audit_fetcher as fetcher


class FakeResponse:
    def __init__(self, status=200, headers=None, chunks=None):
        self.status = status
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self._chunks = list(chunks or [])
        self.closed = False
        self.read_sizes = []

    def read(self, amount, decode_content=False):
        self.read_sizes.append(amount)
        if self._chunks:
            return self._chunks.pop(0)
        return b""

    def close(self):
        self.closed = True


class FakePool:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.closed = False
        self.response = FakeResponse(chunks=[b"<html>ok</html>"])

    def urlopen(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return self.response

    def close(self):
        self.closed = True


def test_fetcher_uses_pinned_pool_host_header_and_disables_redirects(monkeypatch):
    pools = []

    class PoolFactory(FakePool):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            pools.append(self)

    monkeypatch.setattr(fetcher, "_resolve_public_addresses", lambda host, port: ["93.184.216.34"])
    monkeypatch.setattr(fetcher, "HTTPConnectionPool", PoolFactory)
    monkeypatch.setattr(fetcher, "HTTPConnection", object)

    result = fetcher.fetch_public_homepage("http://example.com/path?q=1")

    assert result.status == 200
    assert result.body == b"<html>ok</html>"
    pool = pools[0]
    method, path, kwargs = pool.calls[0]
    assert method == "GET"
    assert path == "/path?q=1"
    assert kwargs["redirect"] is False
    assert kwargs["retries"] is False
    assert kwargs["headers"]["Host"] == "example.com"
    assert pool.kwargs["host"] == "example.com"
    assert pool.closed is True
    assert pool.response.closed is True


def test_https_pool_preserves_hostname_for_tls_verification(monkeypatch):
    pools = []

    class PoolFactory(FakePool):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            pools.append(self)

    monkeypatch.setattr(fetcher, "_resolve_public_addresses", lambda host, port: ["93.184.216.34"])
    monkeypatch.setattr(fetcher, "HTTPSConnectionPool", PoolFactory)
    monkeypatch.setattr(fetcher, "HTTPSConnection", object)

    fetcher.fetch_public_homepage("https://example.com/")

    assert pools[0].kwargs["host"] == "example.com"
    assert pools[0].kwargs["server_hostname"] == "example.com"
    assert pools[0].kwargs["assert_hostname"] == "example.com"
    assert pools[0].kwargs["cert_reqs"] == "CERT_REQUIRED"


def test_fetcher_stops_if_body_exceeds_configured_limit(monkeypatch):
    class OversizePool(FakePool):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.response = FakeResponse(chunks=[b"12345", b"67890"])

    monkeypatch.setattr(fetcher, "_resolve_public_addresses", lambda host, port: ["93.184.216.34"])
    monkeypatch.setattr(fetcher, "HTTPConnectionPool", OversizePool)
    monkeypatch.setattr(fetcher, "HTTPConnection", object)

    import pytest
    with pytest.raises(fetcher.WebsiteFetchError):
        fetcher.fetch_public_homepage("http://example.com/", max_bytes=8)
