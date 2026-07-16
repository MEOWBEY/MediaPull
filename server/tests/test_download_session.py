"""The impersonated-download fallback reuses one shared curl_cffi session
across jobs instead of building (and tearing down) one per download."""

import pytest

from app import audio
from app.config import Settings


@pytest.fixture(autouse=True)
async def _clean_sessions():
    # Isolate each test from any session another test (or import) created.
    await audio.close_download_session()
    yield
    await audio.close_download_session()


def test_same_session_reused_for_same_proxy():
    settings = Settings()
    first = audio._get_download_session(settings)
    second = audio._get_download_session(settings)
    assert first is second  # one pool + TLS setup, not one per job


def test_distinct_session_per_proxy():
    direct = audio._get_download_session(Settings(PROXY_URL=""))
    proxied = audio._get_download_session(Settings(PROXY_URL="http://egress.local:8080"))
    assert direct is not proxied


async def test_close_is_idempotent_when_unused():
    # Never touched the fallback path -> nothing to close, must not raise.
    await audio.close_download_session()
    await audio.close_download_session()


async def test_close_clears_the_cache():
    audio._get_download_session(Settings())
    assert audio._download_sessions
    await audio.close_download_session()
    assert not audio._download_sessions
