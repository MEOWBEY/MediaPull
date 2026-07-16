"""Lightweight ASGI route smoke tests."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_health_ok() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Lifespan must run so app.state is populated.
        async with app.router.lifespan_context(app):
            res = await client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert "version" in body
    assert "ffmpegAvailable" in body or "ffmpeg_available" in body
