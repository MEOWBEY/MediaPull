"""Proxy SSRF guard, cookie-token, and HLS-rewrite characterization tests."""

import pytest

import app.proxy as proxy_mod
from app.config import Settings
from app.proxy import ProxyService, _is_blocked_ip, _rewrite_hls


@pytest.fixture
def proxy():
    return ProxyService(Settings())


# ----- host / IP guard --------------------------------------------------


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",
        "10.0.0.1",
        "192.168.1.5",
        "172.16.5.5",
        "172.31.255.254",
        "169.254.0.1",
        "[::1]",
        "[::ffff:127.0.0.1]",
        "[::ffff:10.0.0.1]",
        "[fc00::1]",
    ],
)
def test_blocked_loopback_and_private(proxy, host):
    # IPv6 literals are bracketed in valid URLs (the form real source URLs take).
    assert proxy._check_host(f"http://{host}/x") is False


def test_is_blocked_ip_edges():
    assert _is_blocked_ip("172.16.0.1") and _is_blocked_ip("172.31.255.255")
    assert not _is_blocked_ip("172.15.0.1") and not _is_blocked_ip("172.32.0.1")
    assert not _is_blocked_ip("8.8.8.8")
    assert not _is_blocked_ip("example.com")  # not an IP literal


def test_allowed_when_no_allowlist(proxy):
    assert proxy._check_host("https://cdn.example.com/file.mp4") is True


def test_allowed_hosts_match_subdomains_and_exact():
    p = ProxyService(Settings())
    p._allowed_hosts = ["googlevideo.com"]
    assert p._check_host("https://r1---sn-abc.googlevideo.com/v.mp4") is True
    assert p._check_host("https://googlevideo.com/v.mp4") is True


def test_disallows_lookalike_suffix():
    p = ProxyService(Settings())
    p._allowed_hosts = ["googlevideo.com"]
    assert p._check_host("https://googlevideo.com.evil.example/x") is False
    assert p._check_host("https://evilgooglevideo.com/x") is False


@pytest.mark.asyncio
async def test_resolve_and_check_rejects_rebind(proxy, monkeypatch):
    """A public hostname that resolves to loopback is rejected (DNS rebind)."""

    def fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(proxy_mod.socket, "getaddrinfo", fake_getaddrinfo)
    assert await proxy._resolve_and_check("https://rebind.example.com/x") is False


@pytest.mark.asyncio
async def test_resolve_and_check_allows_public(proxy, monkeypatch):
    def fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(proxy_mod.socket, "getaddrinfo", fake_getaddrinfo)
    assert await proxy._resolve_and_check("https://example.com/x") is True


# ----- ephemeral cookie token ------------------------------------------


def test_cookie_token_round_trip(proxy):
    token = proxy.create_cookie_token("sid=abc; auth=1")
    assert proxy._resolve_cookie_token(token) == "sid=abc; auth=1"


def test_cookie_token_unknown_is_empty(proxy):
    assert proxy._resolve_cookie_token("does-not-exist") == ""


def test_cookie_token_expired_is_empty(proxy):
    proxy._token_ttl = 0.0  # expire immediately
    token = proxy.create_cookie_token("sid=abc")
    assert proxy._resolve_cookie_token(token) == ""


# ----- HLS rewrite ------------------------------------------------------

BASE = "https://proxy.local/proxy-video"
SOURCE = "https://cdn.example.com/playlist.m3u8"
PASS = {"referer": "https://site.example/page"}


def test_rewrites_relative_segment_url():
    out = _rewrite_hls("#EXTM3U\nsegment.ts\n", SOURCE, BASE, PASS)
    assert "proxy-video" in out
    assert "cdn.example.com" in out  # urljoin against source


def test_rewrites_quoted_key_and_map_uri():
    playlist = (
        "#EXTM3U\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\n'
        '#EXT-X-MAP:URI="init.mp4"\n'
        "segment.ts\n"
    )
    out = _rewrite_hls(playlist, SOURCE, BASE, PASS)
    # Both quoted URIs (key + map) are routed back through the proxy.
    assert out.count("proxy-video") >= 3
