"""Admin cookie file manager: list files, add/update/delete entries."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main
import app.admin as admin
from app.admin import hash_password


@asynccontextmanager
async def _client(monkeypatch, tmp_path, cookie_file):
    monkeypatch.setattr(main.settings, "admin_username", "boss", raising=False)
    monkeypatch.setattr(
        main.settings, "admin_password_hash", hash_password("hunter2"), raising=False
    )
    monkeypatch.setattr(
        main.settings, "cookie_file_paths_raw", str(cookie_file), raising=False
    )
    admin._sessions.clear()
    app = main.create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/admin/login", json={"username": "boss", "password": "hunter2"}
            )
            yield client


@pytest.mark.asyncio
async def test_cookie_list_new_file(monkeypatch, tmp_path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    async with _client(monkeypatch, tmp_path, cookie_file) as client:
        res = await client.get("/admin/cookies")
        assert res.status_code == 200
        files = res.json()["files"]
        assert len(files) == 1
        assert files[0]["path"] == str(cookie_file)
        assert files[0]["exists"] is False


@pytest.mark.asyncio
async def test_add_update_delete_entry(monkeypatch, tmp_path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    async with _client(monkeypatch, tmp_path, cookie_file) as client:
        now = int(time.time())
        add = await client.put(
            "/admin/cookies/entries",
            json={
                "path": str(cookie_file),
                "domain": ".example.com",
                "name": "session_id",
                "value": "abc123",
                "cookiePath": "/",
                "secure": True,
                "includeSubdomains": True,
                "expires": now + 3600,
            },
        )
        assert add.status_code == 200
        assert add.json()["replaced"] is False

        text = cookie_file.read_text(encoding="utf-8")
        assert text.startswith("# Netscape HTTP Cookie File")
        assert ".example.com\tTRUE\t/\tTRUE\t" in text
        assert "\tsession_id\tabc123" in text

        res = await client.get("/admin/cookies")
        entries = res.json()["files"][0]["entries"]
        assert len(entries) == 1
        assert entries[0]["name"] == "session_id"
        assert entries[0]["secure"] is True

        # Updating the same (domain, path, name) replaces in place.
        update = await client.put(
            "/admin/cookies/entries",
            json={
                "path": str(cookie_file),
                "domain": ".example.com",
                "name": "session_id",
                "value": "zzz999",
                "cookiePath": "/",
                "expires": 0,
            },
        )
        assert update.status_code == 200
        assert update.json()["replaced"] is True
        updated = (await client.get("/admin/cookies")).json()["files"][0]["entries"]
        assert len(updated) == 1
        assert updated[0]["value"] == "zzz999"
        assert updated[0]["expires"] == 0  # session cookie

        # Expired / expiring entries are flagged.
        expired = await client.put(
            "/admin/cookies/entries",
            json={
                "path": str(cookie_file),
                "domain": ".old.example.com",
                "name": "gone",
                "value": "1",
                "cookiePath": "/",
                "expires": 1,
            },
        )
        assert expired.status_code == 200
        files = (await client.get("/admin/cookies")).json()["files"]
        assert files[0]["expiredCount"] == 1

        # Delete by (domain, name, path).
        delete = await client.delete(
            "/admin/cookies/entries",
            params={
                "path": str(cookie_file),
                "domain": ".example.com",
                "name": "session_id",
                "cookie_path": "/",
            },
        )
        assert delete.status_code == 200
        remaining = (await client.get("/admin/cookies")).json()["files"][0]["entries"]
        assert [e["name"] for e in remaining] == ["gone"]

        gone = await client.delete(
            "/admin/cookies/entries",
            params={
                "path": str(cookie_file),
                "domain": ".example.com",
                "name": "session_id",
                "cookie_path": "/",
            },
        )
        assert gone.status_code == 404