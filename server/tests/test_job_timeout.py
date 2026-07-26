"""The configured transcribe_job_timeout must actually stop a stuck job."""

import asyncio

import pytest

import app.jobs as jobs_mod
from app.audio import AudioChunk, AudioError
from app.config import Settings
from app.jobs import JobStore, run_transcription_job


class _HangingTranscriber:
    max_concurrency = 1

    async def transcribe(self, path):
        await asyncio.sleep(3600)  # never returns within the test window

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_job_times_out_and_is_marked_error(monkeypatch):
    settings = Settings()
    settings.transcribe_job_timeout = 1  # 1s cap

    async def fake_plan_acquisition(formats, settings, duration_hint=None, **_kwargs):
        class _Plan:
            windows = None  # force the single-pass path

        return _Plan()

    async def fake_acquire_audio(*a, **k):
        return a[2] / "audio.opus"  # a[2] is work_dir

    async def fake_probe_duration(*a, **k):
        return 10.0

    async def fake_chunk_audio(*a, **k):
        return [AudioChunk(path=a[0], offset_seconds=0.0)]

    async def fake_extract_peaks_chunks(*a, **k):
        return [0.0]

    monkeypatch.setattr(jobs_mod, "plan_acquisition", fake_plan_acquisition)
    monkeypatch.setattr(jobs_mod, "acquire_audio", fake_acquire_audio)
    monkeypatch.setattr(jobs_mod, "probe_duration", fake_probe_duration)
    monkeypatch.setattr(jobs_mod, "chunk_audio", fake_chunk_audio)
    monkeypatch.setattr(jobs_mod, "extract_peaks_chunks", fake_extract_peaks_chunks)

    store = JobStore(settings)
    job = await store.create()
    await run_transcription_job(
        job.id, [], settings, store, _HangingTranscriber(), duration_hint=10.0
    )
    result = await store.get(job.id)
    assert result.status == "error"
    assert "time limit" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_work_dir_cleaned_when_planning_fails(monkeypatch, tmp_path):
    """A failure raised before any run call (e.g. a request with no usable
    formats) must still remove the ds-transcribe-* work dir."""
    settings = Settings()
    work_dir = tmp_path / "ds-transcribe-test"

    def fake_create_work_dir():
        work_dir.mkdir()
        return work_dir

    async def failing_plan_acquisition(*a, **k):
        raise AudioError("No downloadable format available for this video")

    monkeypatch.setattr(jobs_mod, "create_work_dir", fake_create_work_dir)
    monkeypatch.setattr(jobs_mod, "plan_acquisition", failing_plan_acquisition)

    store = JobStore(settings)
    job = await store.create()
    await run_transcription_job(job.id, [], settings, store, _HangingTranscriber())
    result = await store.get(job.id)
    assert result.status == "error"
    assert not work_dir.exists()
