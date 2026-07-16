"""Gallery extract helpers (warnings, parse classification)."""

from __future__ import annotations

from app.gallery import GalleryExtractor, _warnings_from_stderr


def test_warnings_login_and_rate() -> None:
    ws = _warnings_from_stderr("HTTP Error 403: login required", truncated=False)
    codes = {w.code for w in ws}
    assert "login" in codes


def test_warnings_quality_and_truncated() -> None:
    ws = _warnings_from_stderr("serving lower resolution watermarked preview", truncated=True)
    codes = {w.code for w in ws}
    assert "quality" in codes
    assert "truncated" in codes


def test_parse_dump_json_url_entries() -> None:
    # Minimal gallery-dl -j shape: Directory chatter + Url messages.
    payload = """[
      [2, {"category": "test"}],
      [3, "https://cdn.example/a.jpg", {"extension": "jpg", "width": 100, "height": 80}],
      [3, "https://cdn.example/b.png", {"extension": "png"}]
    ]"""
    images, skipped = GalleryExtractor._parse_dump_json(payload)
    assert skipped == 0
    assert len(images) == 2
    assert images[0].url.endswith("a.jpg")
    assert images[0].ext == "jpg"


def test_parse_counts_errors_as_skipped() -> None:
    payload = """[
      [3, "https://cdn.example/ok.jpg", {"extension": "jpg"}],
      [-1, {"error": "HttpError", "message": "403"}]
    ]"""
    images, skipped = GalleryExtractor._parse_dump_json(payload)
    assert len(images) == 1
    assert skipped == 1
