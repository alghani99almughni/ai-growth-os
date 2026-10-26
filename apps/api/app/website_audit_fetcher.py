"""Connection-pinned, bounded fetch boundary for public website audits.

The URL hostname is resolved once, every returned address must be globally routable,
and the HTTP connection is opened to one of those exact IP addresses. For HTTPS,
urllib3 still uses the original hostname for SNI and certificate hostname validation.
Redirects are never followed. The caller receives bounded response bytes only.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit

import urllib3
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.util import Timeout


MAX_RESPONSE_BYTES = 500_000
USER_AGENT = "AIGrowthOS-VisibilityAudit/1.0"


class UnsafeWebsiteTarget(ValueError):
    """The requested host cannot be safely fetched."""


class WebsiteFetchError(RuntimeError):
    """The public website could not be fetched within the audit boundary."""


@dataclass(frozen=True)
class BoundedWebsiteResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes


def _resolve_public_addresses(host: str, port: int) -> list[str]:
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError) as exc:
        raise WebsiteFetchError("Website domain could not be resolved") from exc
    addresses: list[str] = []
    for answer in answers:
        raw = answer[4][0].split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise UnsafeWebsiteTarget("DNS returned an invalid address") from exc
        # Fail closed if ANY answer is private, loopback, link-local, multicast,
        # reserved, or otherwise non-global; do not just pick a public answer.
        if not ip.is_global or ip.is_multicast or ip.is_unspecified:
            raise UnsafeWebsiteTarget("Website domain resolves to a private or reserved address")
        normalized = str(ip)
        if normalized not in addresses:
            addresses.append(normalized)
    if not addresses:
        raise WebsiteFetchError("Website domain could not be resolved")
    return addresses


def _pinned_connection_class(base_class: type, address: str) -> type:
    """Create a per-request connection class whose TCP dial target cannot drift."""
    def _new_conn(self):
        try:
            sock = socket.create_connection(
                (address, self.port),
                self.timeout,
                source_address=self.source_address,
                socket_options=self.socket_options,
            )
        except OSError as exc:
            raise urllib3.exceptions.NewConnectionError(self, "Pinned website connection failed") from exc
        return sock

    return type(
        "Pinned" + base_class.__name__,
        (base_class,),
        {"_new_conn": _new_conn, "__module__": __name__},
    )


def fetch_public_homepage(url: str, *, max_bytes: int = MAX_RESPONSE_BYTES) -> BoundedWebsiteResponse:
    """Fetch one public HTTP(S) homepage without redirects or unbounded reads."""
    if max_bytes < 1 or max_bytes > MAX_RESPONSE_BYTES:
        raise ValueError("max_bytes must be between 1 and the audit hard limit")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeWebsiteTarget("Only absolute HTTP(S) website URLs are supported")
    if parts.username or parts.password or parts.fragment:
        raise UnsafeWebsiteTarget("URL credentials and fragments are not supported")
    if parts.port not in (None, 80, 443):
        raise UnsafeWebsiteTarget("Custom ports are not supported")
    host = parts.hostname.rstrip(".").lower()
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeWebsiteTarget("IP-literal website targets are not supported")
    port = 443 if parts.scheme == "https" else 80
    addresses = _resolve_public_addresses(host, port)
    last_error: Exception | None = None

    for address in addresses:
        base = HTTPSConnection if parts.scheme == "https" else HTTPConnection
        pinned_class = _pinned_connection_class(base, address)
        pool_class = HTTPSConnectionPool if parts.scheme == "https" else HTTPConnectionPool
        pool_kwargs = {
            "host": host,
            "port": port,
            "timeout": Timeout(connect=3.0, read=5.0),
            "maxsize": 1,
            "block": True,
            "retries": False,
            "headers": {"User-Agent": USER_AGENT, "Accept": "text/html"},
            "_connection_cls": pinned_class,
        }
        if parts.scheme == "https":
            # Keep hostname-based TLS SNI and certificate validation while the
            # underlying TCP socket is pinned to the previously validated IP.
            pool_kwargs.update({"server_hostname": host, "assert_hostname": host, "cert_reqs": "CERT_REQUIRED"})
        pool = pool_class(**pool_kwargs)
        response = None
        try:
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            response = pool.urlopen(
                "GET", path, redirect=False, retries=False, preload_content=False,
                decode_content=False, headers={"Host": host},
            )
            body = bytearray()
            if response.status < 300 and "text/html" in response.headers.get("Content-Type", "").lower():
                while True:
                    chunk = response.read(min(16_384, max_bytes + 1 - len(body)), decode_content=False)
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        raise WebsiteFetchError("Website homepage exceeds the audit byte limit")
            return BoundedWebsiteResponse(
                url=url,
                status=response.status,
                headers={str(k): str(v) for k, v in response.headers.items()},
                body=bytes(body),
            )
        except WebsiteFetchError:
            raise
        except Exception as exc:
            last_error = exc
        finally:
            if response is not None:
                response.close()
            pool.close()
    raise WebsiteFetchError("Website could not be reached safely") from last_error
