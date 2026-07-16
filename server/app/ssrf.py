"""Shared SSRF guards for proxy, extract, gallery, and transcription fetches.

Block loopback / private / link-local destinations and require http(s).
Proxy still applies its own host allow-list on top of these helpers.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def is_blocked_ip(host: str) -> bool:
    """True when *host* is an IP literal in a range we must never reach.

    Covers loopback, RFC-1918 private, link-local, unique-local (fc00::/7),
    unspecified, reserved, multicast, and IPv4-mapped IPv6. Returns False
    when *host* is not an IP literal (a DNS name).
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


def assert_public_http_url(url: str) -> None:
    """Raise ValueError if *url* is not a safe public http(s) target.

    Checks scheme, presence of hostname, and blocks localhost / private IP
    literals. DNS rebinding is handled on the proxy hop path; extractors
    rely on this string-level gate for user-supplied page URLs.
    """
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http and https URLs are allowed")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL is missing a hostname")

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("Requests to localhost are not allowed")

    if is_blocked_ip(hostname):
        raise ValueError("Requests to private or internal network addresses are not allowed")
