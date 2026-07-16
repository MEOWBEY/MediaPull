"""Shared SSRF guards (plan 010)."""

from __future__ import annotations

import pytest

from app.extractor import is_valid_url
from app.ssrf import assert_public_http_url, is_blocked_ip


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
