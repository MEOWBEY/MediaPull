"""Admin log ring buffer + jobs endpoints."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main
import app.admin as admin
from app.admin import hash_password


@asynccontextmanager
async def _admin_client(monkeypatch, tmp_path):
    monkeypatch.setattr(main.settings, "admin_username", "boss", raising=False)
    monkeypatch.setattr(
        main.settings, "admin_password_hash", hash_password("hunter2"), raising=False
    )
    monkeypatch.setattr(main.settings, "admin_state_path", str(tmp_path / "state.json"), raising=False)
    admin._sessions.clear()
    app = main.create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/admin/login", json={"username": "boss", "password": "hunter2"}
            )
            yield client


@pytest.mark.asyncio
async def test_log_buffer_captures_and_filters() -> None:
    admin.attach_log_buffer()  # idempotent; standalone logger test has no lifespan
    admin.LOG_BUFFER._records.clear()
    logger = logging.getLogger("mediapull.test")
    logger.warning("needle line %s", 42)
    logger.info("haystack line")

    entries = admin.LOG_BUFFER.recent(q="needle")
    assert len(entries) == 1
    assert entries[0]["message"] == "needle line 42"
    assert entries[0]["level"] == "WARNING"

    assert admin.LOG_BUFFER.recent(level="ERROR") == []
    assert admin.LOG_BUFFER.recent(limit=1)[0]["level"] == "INFO"
    admin.LOG_BUFFER._records.clear()


@pytest.mark.asyncio
async def test_admin_logs_endpoint(monkeypatch, tmp_path) -> None:
    async with _admin_client(monkeypatch, tmp_path) as client:
        logging.getLogger("mediapull.test").warning("panel-visible")
        res = await client.get("/admin/logs", params={"q": "panel-visible"})
        assert res.status_code == 200
        assert len(res.json()["entries"]) == 1


@pytest.mark.asyncio
async def test_jobs_list_and_cancel(monkeypatch, tmp_path) -> None:
    async with _admin_client(monkeypatch, tmp_path) as client:
        state = client._transport.app.state
        await state.jobs.create()
        res = await client.get("/admin/jobs")
        assert res.status_code == 200
        jobs = res.json()["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["type"] == "transcribe"
        assert jobs[0]["status"] == "queued"

        first = await client.post(f"/admin/jobs/transcribe/{jobs[0]['id']}/cancel")
        assert first.status_code == 200
        missing = await client.post("/admin/jobs/transcribe/nope/cancel")
        assert missing.status_code == 404

        purge = await client.post("/admin/cache/purge")
        assert purge.status_code == 200