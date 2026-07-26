"""Shared SSRF guards (plan 010)."""

from __future__ import annotations

import socket

import pytest

import app.ssrf as ssrf_mod
from app.extractor import is_valid_url
from app.ssrf import assert_public_http_url, assert_public_resolved_url, is_blocked_ip


def test_blocked_ip_literals() -> None:
    assert is_blocked_ip("127.0.0.1")
    assert is_blocked_ip("10.0.0.1")
    assert is_blocked_ip("192.168.1.1")
    assert is_blocked_ip("::1")
    assert not is_blocked_ip("example.com")
    assert not is_blocked_ip("8.8.8.8")


def test_assert_public_http_url_ok() -> None:
    assert_public_http_url("https://example.com/path")
    assert_public_http_url("http://cdn.example.org/v.mp4")


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/secret",
        "http://10.0.0.5/meta",
        "http://192.168.0.1/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "not-a-url",
    ],
)
def test_assert_public_http_url_rejects(url: str) -> None:
    with pytest.raises(ValueError):
        assert_public_http_url(url)


def test_is_valid_url_rejects_private() -> None:
    assert is_valid_url("https://youtube.com/watch?v=x")
    assert not is_valid_url("http://127.0.0.1/video.mp4")
    assert not is_valid_url("http://192.168.1.10/")


# ----- DNS resolve-and-check (extract/transcribe entry gate) ------------


async def test_resolved_url_rejects_private_resolution(monkeypatch) -> None:
    """A public-looking hostname that resolves to a private address must not
    pass the extract-side gate (DNS rebinding)."""

    def fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("10.0.0.7", 0))]

    monkeypatch.setattr(ssrf_mod.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        await assert_public_resolved_url("https://rebind.example.com/x")


async def test_resolved_url_allows_public_resolution(monkeypatch) -> None:
    def fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(ssrf_mod.socket, "getaddrinfo", fake_getaddrinfo)
    await assert_public_resolved_url("https://example.com/x")


async def test_resolved_url_rejects_unresolvable(monkeypatch) -> None:
    def failing_getaddrinfo(host, port):
        raise socket.gaierror("name not known")

    monkeypatch.setattr(ssrf_mod.socket, "getaddrinfo", failing_getaddrinfo)
    with pytest.raises(ValueError):
        await assert_public_resolved_url("https://nx.example.com/x")


async def test_resolved_url_skips_dns_for_ip_literal(monkeypatch) -> None:
    """An IP literal is fully judged by the string checks -- no DNS lookup."""

    def boom(host, port):  # pragma: no cover - must never run
        raise AssertionError("getaddrinfo must not be called for an IP literal")

    monkeypatch.setattr(ssrf_mod.socket, "getaddrinfo", boom)
    await assert_public_resolved_url("http://93.184.216.34/x")
    with pytest.raises(ValueError):
        await assert_public_resolved_url("http://127.0.0.1/x")
