"""Fetch a public web page for ingestion without becoming an SSRF proxy (SPEC §6 safe external access).

Only http(s) on default ports; every hop (including redirects, max 3) must resolve exclusively to public IP
addresses; responses are size-capped and time-limited. For http the request goes to the validated IP (Host header
kept), closing the DNS-rebinding window. For https the TLS client re-resolves the hostname, leaving a small
rebinding window — production should also route this egress through a proxy that blocks private ranges
(docs/SECURITY.md).
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

from abos.core.config import get_settings
from abos.knowledge.parsing import ParseError

MAX_REDIRECTS = 3
ALLOWED_TYPES = ("text/html", "text/plain", "text/markdown", "text/csv", "application/pdf", "application/xhtml+xml")


@dataclass
class Fetched:
    data: bytes
    content_type: str
    final_url: str


def _public_ip(host: str, port: int) -> str:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ParseError("url_unresolvable", "The website's address could not be resolved") from exc
    addrs = {info[4][0] for info in infos}
    for a in addrs:
        ip = ipaddress.ip_address(a.split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise ParseError("url_forbidden", "Only public websites can be imported")
    return sorted(addrs)[0]


def validate_url(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ParseError("url_invalid", "Use a full http:// or https:// address")
    if parts.username or parts.password:
        raise ParseError("url_invalid", "Addresses with embedded credentials are not allowed")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in (80, 443):
        raise ParseError("url_forbidden", "Only standard web ports (80/443) are allowed")
    return parts.scheme, parts.hostname, port


def fetch(url: str) -> Fetched:
    s = get_settings()
    for _ in range(MAX_REDIRECTS + 1):
        scheme, host, port = validate_url(url)
        ip = _public_ip(host, port)
        pinned = f"[{ip}]" if ":" in ip else ip
        target = url.replace(f"//{host}", f"//{pinned}", 1) if scheme == "http" else url
        with httpx.Client(timeout=s.url_fetch_timeout_seconds, follow_redirects=False,
                          headers={"User-Agent": "AI-Business-OS-Importer/1.0"}) as client:
            try:
                with client.stream("GET", target, headers={"Host": host}) as r:
                    if r.is_redirect:
                        url = urljoin(url, r.headers.get("location", ""))
                        continue
                    if r.status_code >= 400:
                        raise ParseError("url_http_error", f"The website returned HTTP {r.status_code}")
                    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype not in ALLOWED_TYPES:
                        raise ParseError("unsupported_type", f"Unsupported content type: {ctype or 'unknown'}")
                    data = bytearray()
                    for chunk in r.iter_bytes():
                        data.extend(chunk)
                        if len(data) > s.url_fetch_max_bytes:
                            raise ParseError("too_large", "The page is larger than the import limit")
                    return Fetched(bytes(data), ctype, url)
            except httpx.TimeoutException as exc:
                raise ParseError("url_timeout", "The website took too long to respond") from exc
            except httpx.HTTPError as exc:
                raise ParseError("url_unreachable", "The website could not be reached") from exc
    raise ParseError("url_redirects", "Too many redirects")
