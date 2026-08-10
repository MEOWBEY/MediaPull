"""Admin panel auth: login/logout/session + login rate limiting."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient, Response

import app.main as main
import app.admin as admin
from app.admin import hash_password, verify_password


@asynccontextmanager
async def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(main.settings, "admin_username", "boss", raising=False)
    monkeypatch.setattr(
        main.settings, "admin_password_hash", hash_password("hunter2"), raising=False
    )
    monkeypatch.setattr(main.settings, "admin_state_path", str(tmp_path / "state.json"), raising=False)
    admin._sessions.clear()
    admin._login_attempts.clear()
    app = main.create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def _login(client: AsyncClient, username: str = "boss", password: str = "hunter2") -> Response:
    return await client.post(
        "/admin/login", json={"username": username, "password": password}
    )


@pytest.mark.asyncio
async def test_hash_roundtrip() -> None:
    hashed = hash_password("s3cret")
    assert hashed.startswith("pbkdf2_sha256$600000$")
    assert verify_password("s3cret", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("s3cret", "garbage")


@pytest.mark.asyncio
async def test_login_disabled_when_not_configured(monkeypatch, tmp_path) -> None:
    async with _client(monkeypatch, tmp_path) as client:
        monkeypatch.setattr(main.settings, "admin_username", "", raising=False)
        res = await _login(client)
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_login_wrong_password(monkeypatch, tmp_path) -> None:
    async with _client(monkeypatch, tmp_path) as client:
        res = await _login(client, password="nope")
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_login_success_sets_http_only_cookie(monkeypatch, tmp_path) -> None:
    async with _client(monkeypatch, tmp_path) as client:
        res = await _login(client)
        assert res.status_code == 200
        assert res.json()["ok"] is True
        raw = res.headers["set-cookie"]
        assert "mediapull_admin=" in raw
        assert "HttpOnly" in raw
        assert "SameSite=strict" in raw
        assert "Secure" not in raw  # plain-http test client
        # The session cookie is stored by httpx's jar -> /admin/me works.
        assert (await client.get("/admin/me")).status_code == 200


@pytest.mark.asyncio
async def test_me_and_logout(monkeypatch, tmp_path) -> None:
    async with _client(monkeypatch, tmp_path) as client:
        assert (await client.get("/admin/me")).status_code == 401
        await _login(client)
        me = await client.get("/admin/me")
        assert me.status_code == 200
        assert me.json()["username"] == "boss"
        await client.post("/admin/logout")
        assert (await client.get("/admin/me")).status_code == 401


@pytest.mark.asyncio
async def test_login_rate_limited(monkeypatch, tmp_path) -> None:
    async with _client(monkeypatch, tmp_path) as client:
        monkeypatch.setattr(main.settings, "admin_login_rate_limit", 2, raising=False)
        assert (await _login(client, password="x1")).status_code == 401
        assert (await _login(client, password="x2")).status_code == 401
        res = await _login(client, password="x3")
        assert res.status_code == 429
        # Even a correct password is refused while throttled.
        assert (await _login(client)).status_code == 429