"""Boot-time PO-token provider probe surfaced via /health.potAvailable."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

import app.main as main
from app.main import _check_pot_provider, create_app


@pytest.mark.asyncio
async def test_health_exposes_pot_available() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            res = await client.get("/health")
    assert res.status_code == 200
    # Field is always present; value reflects the boot probe (typically False
    # in CI where no sidecar runs).
    assert "potAvailable" in res.json()


@pytest.mark.asyncio
async def test_probe_false_when_unreachable(monkeypatch) -> None:
    # Point at a port nothing is listening on -> connection refused -> False,
    # and startup must not raise (advisory only).
    ok = await _check_pot_provider("http://127.0.0.1:9")
    assert ok is False


@pytest.mark.asyncio
async def test_probe_true_on_2xx(monkeypatch) -> None:
    class _Resp:
        status_code = 200

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            assert url.endswith("/ping")
            return _Resp()

    monkeypatch.setattr(main.httpx, "AsyncClient", _FakeClient)
    assert await _check_pot_provider("http://127.0.0.1:4416") is True
