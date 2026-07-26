"""Proxy SSRF guard, cookie-token, and HLS-rewrite characterization tests."""

import pytest

import app.proxy as proxy_mod
from app.config import Settings
from app.proxy import ProxyService, _download_filename, _rewrite_hls
from app.ssrf import is_blocked_ip


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
    assert is_blocked_ip("172.16.0.1") and is_blocked_ip("172.31.255.255")
    assert not is_blocked_ip("172.15.0.1") and not is_blocked_ip("172.32.0.1")
    assert not is_blocked_ip("8.8.8.8")
    assert not is_blocked_ip("example.com")  # not an IP literal


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


# ----- DNS verdict cache (per-HLS-segment resolution reuse) -------------


@pytest.mark.asyncio
async def test_resolve_verdict_is_cached_across_calls(proxy, monkeypatch):
    """The second call for the same host (e.g. the next HLS segment) reuses the
    cached resolution instead of resolving again."""
    calls = {"n": 0}

    def counting_getaddrinfo(host, port):
        calls["n"] += 1
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(proxy_mod.socket, "getaddrinfo", counting_getaddrinfo)
    assert await proxy._resolve_and_check("https://cdn.example.com/seg1.ts") is True
    assert await proxy._resolve_and_check("https://cdn.example.com/seg2.ts") is True
    assert calls["n"] == 1  # resolved once, second segment served from cache


@pytest.mark.asyncio
async def test_resolve_cache_expires(proxy, monkeypatch):
    def fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(proxy_mod.socket, "getaddrinfo", fake_getaddrinfo)
    proxy._dns_ttl = 0.0  # every entry is already expired
    assert await proxy._resolve_and_check("https://cdn.example.com/a.ts") is True
    # A now-expired entry must not be trusted -- forces a fresh resolve.
    hostname = "cdn.example.com"
    assert proxy._dns_verdict_cache[hostname][1] <= proxy_mod.time.monotonic()


@pytest.mark.asyncio
async def test_allowlist_still_enforced_despite_dns_cache(monkeypatch):
    """Caching the *resolution* must not cache away the allow-list guard: a
    disallowed host is rejected by _check_host before DNS is ever consulted."""
    p = ProxyService(Settings())
    p._allowed_hosts = ["googlevideo.com"]

    def boom(host, port):  # pragma: no cover - must never run
        raise AssertionError("getaddrinfo should not be reached for a blocked host")

    monkeypatch.setattr(proxy_mod.socket, "getaddrinfo", boom)
    assert await p._resolve_and_check("https://evil.example/x") is False


@pytest.mark.asyncio
async def test_resolve_failure_not_cached(proxy, monkeypatch):
    """A transient resolver failure returns False but is NOT cached, so a
    following request re-resolves rather than being pinned to blocked."""
    import socket as _socket

    state = {"fail": True}

    def flaky_getaddrinfo(host, port):
        if state["fail"]:
            raise _socket.gaierror("temporary failure")
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(proxy_mod.socket, "getaddrinfo", flaky_getaddrinfo)
    assert await proxy._resolve_and_check("https://cdn.example.com/x.ts") is False
    state["fail"] = False
    assert await proxy._resolve_and_check("https://cdn.example.com/x.ts") is True


# ----- byte-stream response headers (Content-Encoding correctness) ------


class _FakeUpstream:
    """Minimal stand-in for a curl_cffi streaming response. curl_cffi
    transparently decompresses, so ``aiter_content`` yields DECODED bytes even
    when the upstream advertised ``Content-Encoding: gzip``."""

    def __init__(self, headers: dict[str, str], body: bytes, status: int = 200):
        self.headers = headers
        self.status_code = status
        self._body = body

    async def aiter_content(self, chunk_size=None, decode_unicode=False):
        yield self._body

    async def aclose(self):
        pass


class _FakeRequestURL:
    scheme = "https"
    netloc = "proxy.local"
    path = "/proxy-video"


class _FakeRequest:
    def __init__(self):
        self.headers = {}
        self.url = _FakeRequestURL()

    async def is_disconnected(self):
        return False


@pytest.mark.asyncio
async def test_stream_drops_stale_gzip_encoding(proxy, monkeypatch):
    """YouTube/Vimeo gzip their timedtext captions and report the COMPRESSED
    length. curl_cffi hands us the decoded body, so forwarding the upstream
    ``Content-Encoding: gzip`` (and compressed ``Content-Length``) would make
    the browser try to gunzip plain text -> decode error -> empty subtitle
    track. The proxy must strip both and stream identity."""
    decoded = b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello\n"
    upstream = _FakeUpstream(
        headers={
            "content-type": "text/vtt; charset=UTF-8",
            "content-encoding": "gzip",
            "content-length": "1074",  # compressed size -- a lie about the body
        },
        body=decoded,
    )

    async def fake_get_checked(url, *, stream, headers):
        return upstream

    monkeypatch.setattr(proxy, "_get_checked", fake_get_checked)

    resp = await proxy._handle_stream(_FakeRequest(), "https://youtube.com/api/timedtext", {})

    assert resp.headers["content-encoding"] == "identity"
    # The compressed Content-Length must not be forwarded (it describes gzip bytes).
    assert "content-length" not in {k.lower() for k in resp.headers}
    # And the streamed body is the real, decoded VTT.
    chunks = [c async for c in resp.body_iterator]
    assert b"".join(chunks) == decoded


@pytest.mark.asyncio
async def test_stream_keeps_length_for_identity_body(proxy, monkeypatch):
    """An uncompressed response keeps its real Content-Length so Range/seek on
    video still works -- only compressed responses lose it."""
    body = b"\x00\x01\x02\x03"
    upstream = _FakeUpstream(
        headers={
            "content-type": "video/mp4",
            "content-length": "4",
            "accept-ranges": "bytes",
        },
        body=body,
    )

    async def fake_get_checked(url, *, stream, headers):
        return upstream

    monkeypatch.setattr(proxy, "_get_checked", fake_get_checked)

    resp = await proxy._handle_stream(_FakeRequest(), "https://cdn.example.com/v.mp4", {})

    assert resp.headers["content-encoding"] == "identity"
    assert resp.headers["content-length"] == "4"  # preserved for seeking


# ----- playlist proxy: bounded buffering --------------------------------


class _FakeChunkedUpstream:
    """Streaming upstream stand-in that yields a fixed chunk repeatedly."""

    def __init__(self, chunk: bytes, count: int, status: int = 200):
        self.headers = {}
        self.status_code = status
        self._chunk = chunk
        self._count = count

    async def aiter_content(self, chunk_size=None):
        for _ in range(self._count):
            yield self._chunk

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_playlist_over_size_cap_is_rejected(proxy, monkeypatch):
    """A protocol=m3u8_native request pointing at a huge file must not be
    buffered whole into memory -- the read stops at the cap and answers 502."""
    upstream = _FakeChunkedUpstream(b"#" * 65536, count=1000)  # ~64MB on offer

    async def fake_get_checked(url, *, stream, headers):
        return upstream

    monkeypatch.setattr(proxy, "_get_checked", fake_get_checked)
    monkeypatch.setattr(proxy_mod, "_MAX_PLAYLIST_BYTES", 100_000)

    resp = await proxy._handle_playlist(
        _FakeRequest(), "https://cdn.example.com/big.bin", {}, {}
    )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_playlist_under_cap_is_rewritten(proxy, monkeypatch):
    playlist = b"#EXTM3U\nsegment.ts\n"
    upstream = _FakeChunkedUpstream(playlist, count=1)

    async def fake_get_checked(url, *, stream, headers):
        return upstream

    monkeypatch.setattr(proxy, "_get_checked", fake_get_checked)

    resp = await proxy._handle_playlist(
        _FakeRequest(), "https://cdn.example.com/playlist.m3u8", {}, {}
    )
    assert resp.status_code == 200
    assert b"proxy-video" in resp.body


# ----- forced-download filename sanitization ----------------------------


def test_download_filename_strips_header_injection_chars():
    assert _download_filename({"filename": 'a\r\nb"c'}) == "abc"


def test_download_filename_strips_path_separators_and_semicolons():
    # Path separators / ';' / '%' can spoof the save location or smuggle
    # Content-Disposition parameters -- all must be dropped.
    assert _download_filename({"filename": "..\\..\\evil;name%2e.mp4"}) == "....evilname2e.mp4"
    assert _download_filename({"filename": "a/b/c.mp4"}) == "abc.mp4"


def test_download_filename_falls_back_to_generic():
    assert _download_filename({}) == "video"
    assert _download_filename({"filename": "///"}) == "video"


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
