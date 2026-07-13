"""JobStore lifecycle characterization tests."""

import asyncio
import time

import pytest

from app.config import Settings
from app.jobs import _TERMINAL_STATUSES, JobStore, TranscriptionJob


@pytest.fixture
def store():
    return JobStore(Settings())


async def test_create_assigns_id(store):
    job = await store.create()
    assert isinstance(job.id, str) and len(job.id) >= 8
    assert job.status == "queued"


async def test_update_notifies_subscribers(store):
    job = await store.create()
    queue = await store.subscribe(job.id)
    await store.update(job.id, status="transcribing", chunks_done=2)
    msg = await asyncio.wait_for(queue.get(), timeout=2)
    assert msg.status == "transcribing"
    assert msg.chunks_done == 2


async def test_cancel_unknown_returns_false(store):
    assert await store.cancel("does-not-exist") is False


def test_terminal_status_flag():
    for status in _TERMINAL_STATUSES:
        assert TranscriptionJob(id="x", status=status).is_terminal
    assert not TranscriptionJob(id="x", status="queued").is_terminal


async def test_sweep_expires_old(store):
    old = await store.create()
    old.created_at = time.monotonic() - 10_000  # far in the past
    store._settings.transcribe_job_ttl = 60
    await store.create()  # triggers a sweep
    assert await store.get(old.id) is None
