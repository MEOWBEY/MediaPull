"""Error-classification mapping for extraction failures."""

import pytest

from app.extractor import classify_extraction_error


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Sign in to confirm you're not a bot", 429),
        ("HTTP Error 429: Too Many Requests", 429),
        ("HTTP Error 403: Forbidden", 403),
        ("HTTP 410 Gone", 410),
        ("HTTP 404 not found", 404),
        ("This video is geo-restricted", 451),
        ("This video is private", 403),
        ("Unsupported URL: https://example.com/x", 422),
        ("No video formats found", 422),
        ("Connection timed out", 504),
        ("Some totally unrelated failure", 502),
    ],
)
def test_status_mapping(text, expected):
    status, message = classify_extraction_error(RuntimeError(text))
    assert status == expected
    assert message  # always a user-facing message
