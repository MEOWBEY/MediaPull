"""Serializer wire-shape tests (plan 011 — no Cookie on the wire)."""

from __future__ import annotations

from app.models import GalleryImage, GalleryInfo, VideoFormat, VideoInfo
from app.serializers import _public_headers, to_client_gallery, to_client_video


def test_public_headers_strips_cookie_case_insensitive() -> None:
    out = _public_headers(
        {"Referer": "https://x/", "Cookie": "a=1", "cookie": "b=2", "User-Agent": "ua"}
    )
    assert "Cookie" not in out
    assert "cookie" not in out
    assert out["Referer"] == "https://x/"
    assert out["User-Agent"] == "ua"


def test_public_headers_empty() -> None:
    assert _public_headers(None) == {}
    assert _public_headers({}) == {}


def test_to_client_video_strips_format_cookies() -> None:
    info = VideoInfo(
        id="1",
        title="t",
        webpage_url="https://example.com/v",
        formats=[
            VideoFormat(
                format_id="f1",
                url="https://cdn.example/v.mp4",
                ext="mp4",
                protocol="https",
                http_headers={"Cookie": "secret=1", "Referer": "https://example.com/"},
            )
        ],
    )
    client = to_client_video(info)
    assert client.formats[0].http_headers.get("Cookie") is None
    assert "cookie" not in {k.lower() for k in (client.formats[0].http_headers or {})}
    assert client.formats[0].http_headers["Referer"] == "https://example.com/"


def test_to_client_gallery_strips_image_cookies() -> None:
    info = GalleryInfo(
        title="g",
        webpage_url="https://example.com/g",
        images=[
            GalleryImage(
                url="https://cdn.example/i.jpg",
                http_headers={"Cookie": "s=1", "Referer": "https://example.com/g"},
            )
        ],
    )
    client = to_client_gallery(info)
    headers = client.images[0].http_headers or {}
    assert "Cookie" not in headers
    assert headers["Referer"] == "https://example.com/g"
