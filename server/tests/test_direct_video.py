"""Direct-video URL detection: extension test on the path component only."""

from __future__ import annotations

import pytest

from app.extractor import is_direct_video


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.example.com/video.mp4",
        "https://cdn.example.com/video.mp4?sig=abc&expires=1",
        "https://cdn.example.com/a/b/clip.WEBM",
        "https://cdn.example.com/movie.mkv#t=10",
    ],
)
def test_direct_video_by_path_suffix(url: str) -> None:
    assert is_direct_video(url)


@pytest.mark.parametrize(
    "url",
    [
        # An extension inside a query parameter must not short-circuit real
        # extraction of the page the URL actually points at.
        "https://site.example/watch?redirect=https%3A%2F%2Fx.example%2Fv.mp4%3Fy",
        "https://site.example/watch?redirect=https://x.example/v.mp4?y",
        "https://site.example/player?file=x.mp4&z=1",
        "https://site.example/watch?v=abc123",
        "https://site.example/article/mp4-encoding-guide",
    ],
)
def test_not_direct_video(url: str) -> None:
    assert not is_direct_video(url)
