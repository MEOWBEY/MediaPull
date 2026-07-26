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
        # "page"/"usage" contain the substring "age" -- these must NOT be
        # classified as age-restricted (403 with a cookies hint).
        ("Unsupported URL: no media found on this page", 422),
        ("Some message about API usage limits and retries", 502),
        ("This video is age-restricted", 403),
        ("Confirm your age to watch this video", 403),
        ("No video formats found", 422),
        ("Connection timed out", 504),
        ("Some totally unrelated failure", 502),
    ],
)
def test_status_mapping(text, expected):
    status, message = classify_extraction_error(RuntimeError(text))
    assert status == expected
    assert message  # always a user-facing message
