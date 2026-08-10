"""Admin moderation: IP bans, blocked domains, rules persistence, rate limit."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main
import app.admin as admin
from app.admin import hash_password


def _enable(monkeypatch, tmp_path) -> str:
    monkeypatch.setattr(main.settings, "admin_username", "boss", raising=False)
    monkeypatch.setattr(
        main.settings, "admin_password_hash", hash_password("hunter2"), raising=False
    )
    state = str(tmp_path / "state.json")
    monkeypatch.setattr(main.settings, "admin_state_path", state, raising=False)
    monkeypatch.setattr(main.settings, "admin_token", "", raising=False)
    admin._sessions.clear()
    admin._login_attempts.clear()
    admin.PAYLOAD_LIMITER._hits.clear()
    return state


@asynccontextmanager
async def _authed_client(monkeypatch, tmp_path):
    _enable(monkeypatch, tmp_path)
    app = main.create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/admin/login", json={"username": "boss", "password": "hunter2"}
            )
            yield client


@asynccontextmanager
async def _raw_client(monkeypatch, tmp_path, **headers):
    _enable(monkeypatch, tmp_path)
    app = main.create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers=headers
        ) as client:
            yield client


@pytest.mark.asyncio
async def test_banned_ip_blocked_everywhere(monkeypatch, tmp_path) -> None:
    state = _enable(monkeypatch, tmp_path)
    json.dump({"banned_ips": ["203.0.113.9"], "blocked_domains": []}, open(state, "w"))
    async with _raw_client(
        monkeypatch, tmp_path, **{"x-forwarded-for": "203.0.113.9"}
    ) as client:
        res = await client.get("/health")
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_domain_block_rejects_extraction(monkeypatch, tmp_path) -> None:
    state = _enable(monkeypatch, tmp_path)
    json.dump(
        {"banned_ips": [], "blocked_domains": ["example.com"]}, open(state, "w")
    )
    async with _raw_client(monkeypatch, tmp_path) as client:
        res = await client.post(
            "/extract-videos", json={"url": "https://www.example.com/watch?v=1"}
        )
        assert res.status_code == 403
        assert "blocked" in res.json()["detail"]
        # Subdomains of a blocked domain are blocked too (suffix match).
        res2 = await client.post(
            "/extract-videos", json={"url": "https://watch.example.com/x"}
        )
        assert res2.status_code == 403
        # Unrelated domains pass the domain check (they fail later for other
        # reasons -- extraction never reaches the network in tests, so any
        # non-403 answer means the check passed).
        res3 = await client.post(
            "/extract-gallery", json={"url": "https://flickr.com/photos/x"}
        )
        assert res3.status_code != 403


@pytest.mark.asyncio
async def test_rules_crud(monkeypatch, tmp_path) -> None:
    async with _authed_client(monkeypatch, tmp_path) as client:
        res = await client.get("/admin/rules")
        assert res.json() == {"bannedIps": [], "blockedDomains": []}

        ban = await client.post("/admin/rules/ips", json={"value": "198.51.100.7"})
        assert ban.json()["bannedIps"] == ["198.51.100.7"]
        block = await client.post("/admin/rules/domains", json={"value": "Youtube.com"})
        assert block.json()["blockedDomains"] == ["youtube.com"]

        # Persisted to the state file.
        saved = json.loads(open(tmp_path / "state.json").read())
        assert saved == {
            "banned_ips": ["198.51.100.7"],
            "blocked_domains": ["youtube.com"],
        }

        unban = await client.delete("/admin/rules/ips", params={"ip": "198.51.100.7"})
        assert unban.json()["bannedIps"] == []
        unblock = await client.delete("/admin/rules/domains", params={"domain": "youtube.com"})
        assert unblock.json()["blockedDomains"] == []


@pytest.mark.asyncio
async def test_usage_and_rate_limit(monkeypatch, tmp_path) -> None:
    async with _authed_client(monkeypatch, tmp_path) as client:
        admin.PAYLOAD_LIMITER._max_hits = 1
        r1 = await client.post("/extract-gallery", json={"url": "https://flickr.com/x"})
        assert r1.status_code != 429  # one hit allowed
        r2 = await client.post("/extract-gallery", json={"url": "https://flickr.com/y"})
        assert r2.status_code == 429

        usage = await client.get("/admin/usage")
        assert any(row["ip"] == "127.0.0.1" for row in usage.json()["topIps"])


@pytest.mark.asyncio
async def test_unauthenticated_admin_routes_401(monkeypatch, tmp_path) -> None:
    async with _raw_client(monkeypatch, tmp_path) as client:
        for path in (
            "/admin/overview",
            "/admin/rules",
            "/admin/logs",
            "/admin/env",
            "/admin/jobs",
            "/admin/cookies",
        ):
            assert (await client.get(path)).status_code == 401, path