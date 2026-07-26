"""Unit tests for proxy-URL unwrap + ctok cookie resolution (plan 009)."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from app.audio import _unwrap_proxied


def _proxy_url(**params: str) -> str:
    return "http://localhost:8000/proxy-video?" + urlencode(params, quote_via=quote)


def test_non_proxy_url_unchanged() -> None:
    url, headers = _unwrap_proxied("https://cdn.example/video.mp4")
    assert url == "https://cdn.example/video.mp4"
    assert headers == {}


def test_unwrap_referer_and_ua() -> None:
    url = _proxy_url(
        url="https://cdn.example/v.mp4",
        protocol="https",
        referer="https://site.example/",
        userAgent="TestAgent/1",
    )
    real, headers = _unwrap_proxied(url)
    assert real == "https://cdn.example/v.mp4"
    assert headers["Referer"] == "https://site.example/"
    assert headers["User-Agent"] == "TestAgent/1"


def test_ctok_resolved_via_callback() -> None:
    url = _proxy_url(
        url="https://cdn.example/v.mp4",
        protocol="https",
        ctok="tok123",
    )
    real, headers = _unwrap_proxied(
        url, resolve_cookie_token=lambda t: "session=abc" if t == "tok123" else ""
    )
    assert real == "https://cdn.example/v.mp4"
    assert headers["Cookie"] == "session=abc"


def test_ctok_missing_resolver_skips_cookie() -> None:
    url = _proxy_url(url="https://cdn.example/v.mp4", protocol="https", ctok="tok")
    _, headers = _unwrap_proxied(url)
    assert "Cookie" not in headers


def test_ctok_expired_or_unknown_token() -> None:
    url = _proxy_url(url="https://cdn.example/v.mp4", protocol="https", ctok="gone")
    _, headers = _unwrap_proxied(url, resolve_cookie_token=lambda _t: "")
    assert "Cookie" not in headers


def test_raw_cookies_query_is_ignored() -> None:
    # Cookies travel only as opaque ctok tokens -- a raw cookies= query param
    # (which would put session cookies into URLs/logs) must never be honored.
    url = _proxy_url(
        url="https://cdn.example/v.mp4",
        protocol="https",
        cookies="a=1; b=2",
    )
    _, headers = _unwrap_proxied(url)
    assert "Cookie" not in headers


def test_ctok_wins_and_raw_cookies_stay_ignored() -> None:
    url = _proxy_url(
        url="https://cdn.example/v.mp4",
        protocol="https",
        ctok="t1",
        cookies="raw=1",
    )
    _, headers = _unwrap_proxied(url, resolve_cookie_token=lambda _t: "from-token=1")
    assert headers["Cookie"] == "from-token=1"
