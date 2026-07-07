"""In-memory job store for the auto-subtitle (transcription) pipeline.

Same "no persistence anywhere" philosophy as ``cache.py`` -- a server
restart mid-job loses it, which is acceptable for this hobby-scale app that
already has zero persistence elsewhere. Job mutation semantics (progress
ticks updated in place as the pipeline runs) don't fit ``TTLCache``'s
copy-on-set model, so this is a small bespoke store rather than a subclass.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from .audio import AudioError, acquire_audio, chunk_if_needed, cleanup_work_dir, create_work_dir
from .config import Settings
from .models import VideoFormat
from .subtitles import merge_chunks, to_srt, to_vtt
from .transcribe.base import Segment, Transcriber
from .transcribe.groq_engine import GroqError
from .waveform import WaveformError, extract_peaks

logger = logging.getLogger("directstream.jobs")

# queued -> downloading -> chunking -> transcribing -> finalizing -> done | error
_TERMINAL_STATUSES = ("done", "error")


@dataclass
class TranscriptionJob:
    id: str
    status: str = "queued"
    progress: float = 0.0
    step_label: str = "Queued"
    language: str | None = None
    vtt_text: str | None = None
    srt_text: str | None = None
    waveform: list[float] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_STATUSES


class JobStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jobs: dict[str, TranscriptionJob] = {}
        self._lock = asyncio.Lock()
        # Bounds concurrent transcription jobs across all clients -- each one
        # pins a Groq-rate-limited pipeline plus local ffmpeg CPU work.
        self.semaphore = asyncio.Semaphore(settings.transcribe_max_concurrent_jobs)

    async def create(self) -> TranscriptionJob:
        async with self._lock:
            self._sweep_expired_locked()
            job = TranscriptionJob(id=uuid.uuid4().hex)
            self._jobs[job.id] = job
            return job

    async def get(self, job_id: str) -> TranscriptionJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def update(self, job_id: str, **fields: object) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)

    def _sweep_expired_locked(self) -> None:
        ttl = self._settings.transcribe_job_ttl
        if ttl <= 0:
            return
        now = time.monotonic()
        expired = [jid for jid, job in self._jobs.items() if now - job.created_at > ttl]
        for jid in expired:
            del self._jobs[jid]


async def run_transcription_job(
    job_id: str,
    formats: list[VideoFormat],
    settings: Settings,
    store: JobStore,
    transcriber: Transcriber,
) -> None:
    """The whole pipeline for one job: acquire audio -> chunk if needed ->
    transcribe each chunk -> merge -> SRT/VTT + waveform. Each step only runs
    when actually necessary (chunking is skipped for short audio; the
    waveform failing is non-fatal since subtitles still work without it).
    """
    work_dir = create_work_dir()
    try:
        async with store.semaphore:
            await store.update(
                job_id, status="downloading", step_label="Acquiring audio…", progress=0.05
            )
            audio_path = await acquire_audio(formats, settings, work_dir)

            await store.update(
                job_id, status="chunking", step_label="Preparing audio…", progress=0.15
            )
            chunks = await chunk_if_needed(audio_path, work_dir, settings)

            segments_by_chunk: list[tuple[float, list[Segment]]] = []
            language: str | None = None
            total = len(chunks)
            for i, chunk in enumerate(chunks):
                label = (
                    f"Transcribing part {i + 1} of {total}…"
                    if total > 1
                    else "Transcribing…"
                )
                await store.update(
                    job_id,
                    status="transcribing",
                    step_label=label,
                    progress=0.2 + 0.6 * (i / total),
                )
                result = await transcriber.transcribe(chunk.path)
                segments_by_chunk.append((chunk.offset_seconds, result.segments))
                if language is None:
                    language = result.language

            await store.update(
                job_id, status="finalizing", step_label="Generating subtitles…", progress=0.85
            )
            merged = merge_chunks(segments_by_chunk)
            vtt_text = to_vtt(merged)
            srt_text = to_srt(merged)

            try:
                waveform = await extract_peaks(audio_path)
            except WaveformError as exc:
                logger.warning("waveform extraction failed for job %s: %s", job_id, exc)
                waveform = None  # non-fatal -- subtitles still work without it

            await store.update(
                job_id,
                status="done",
                step_label="Done",
                progress=1.0,
                language=language or "en",
                vtt_text=vtt_text,
                srt_text=srt_text,
                waveform=waveform,
            )
    except (AudioError, GroqError) as exc:
        logger.warning("transcription job %s failed: %s", job_id, exc)
        await store.update(job_id, status="error", error=str(exc), step_label="Failed")
    except Exception:  # noqa: BLE001 - surface any unexpected failure cleanly
        logger.exception("transcription job %s failed unexpectedly", job_id)
        await store.update(
            job_id, status="error", error="Unexpected server error", step_label="Failed"
        )
    finally:
        cleanup_work_dir(work_dir)
