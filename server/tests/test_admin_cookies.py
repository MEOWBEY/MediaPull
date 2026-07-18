"""POST /admin/cookies -- authenticated server-side cookie refresh.

Covers the auth gate (disabled when unset, 401 on bad token), input
normalization/rejection, and the atomic write to the first configured
COOKIE_FILE_PATHS entry.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main
from app.main import create_app

# A minimal valid Netscape export (tab-separated). One real cookie row.
_NETSCAPE = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t9999999999\tSID\tabc123\n"
)


async def _post(app, body, headers=None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            return await client.post("/admin/cookies", json=body, headers=headers or {})


@pytest.mark.asyncio
async def test_disabled_when_token_unset(monkeypatch) -> None:
    # No ADMIN_TOKEN -> endpoint must 404 (not even advertise itself).
    monkeypatch.setattr(main.settings, "admin_token", "", raising=False)
    res = await _post(create_app(), {"cookies": _NETSCAPE})
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_rejects_missing_and_wrong_token(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "admin_token", "s3cret", raising=False)
    app = create_app()

    no_auth = await _post(app, {"cookies": _NETSCAPE})
    assert no_auth.status_code == 401

    bad = await _post(app, {"cookies": _NETSCAPE}, {"Authorization": "Bearer nope"})
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_rejects_unusable_cookie_blob(monkeypatch, tmp_path) -> None:
    target = tmp_path / "cookies.txt"
    monkeypatch.setattr(main.settings, "admin_token", "s3cret", raising=False)
    monkeypatch.setattr(main.settings, "cookie_file_paths_raw", str(target), raising=False)
    # Empty/garbage (no tabs, no key=val pairs) normalizes to None -> 422.
    res = await _post(
        create_app(), {"cookies": "   "}, {"Authorization": "Bearer s3cret"}
    )
    assert res.status_code == 422
    assert not target.exists()


@pytest.mark.asyncio
async def test_409_when_no_cookie_path_configured(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "admin_token", "s3cret", raising=False)
    monkeypatch.setattr(main.settings, "cookie_file_paths_raw", "", raising=False)
    res = await _post(
        create_app(), {"cookies": _NETSCAPE}, {"Authorization": "Bearer s3cret"}
    )
    assert res.status_code == 409


@pytest.mark.asyncio
async def test_writes_normalized_cookies_to_first_path(monkeypatch, tmp_path) -> None:
    target = tmp_path / "nested" / "cookies.txt"
    monkeypatch.setattr(main.settings, "admin_token", "s3cret", raising=False)
    # Two paths -> only the first is written (the rotation's primary).
    other = tmp_path / "second.txt"
    monkeypatch.setattr(
        main.settings, "cookie_file_paths_raw", f"{target},{other}", raising=False
    )

    res = await _post(
        create_app(), {"cookies": _NETSCAPE}, {"Authorization": "Bearer s3cret"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["cookieLines"] == 1
    assert body["path"] == str(target)

    written = target.read_text(encoding="utf-8")
    assert "# Netscape HTTP Cookie File" in written
    assert "SID\tabc123" in written
    assert not other.exists()  # second path untouched


@pytest.mark.asyncio
async def test_adds_missing_netscape_header(monkeypatch, tmp_path) -> None:
    target = tmp_path / "cookies.txt"
    monkeypatch.setattr(main.settings, "admin_token", "s3cret", raising=False)
    monkeypatch.setattr(main.settings, "cookie_file_paths_raw", str(target), raising=False)
    # Header-less tab-separated rows -> normalize_cookies prepends the magic line.
    headerless = ".x.com\tTRUE\t/\tTRUE\t9999999999\tauth_token\tzzz\n"
    res = await _post(
        create_app(), {"cookies": headerless}, {"Authorization": "Bearer s3cret"}
    )
    assert res.status_code == 200
    assert target.read_text(encoding="utf-8").startswith("# Netscape HTTP Cookie File")
