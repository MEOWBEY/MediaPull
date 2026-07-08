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
from .transcribe.base import Segment, Transcriber, TranscriptionResult
from .transcribe.groq_engine import GroqError
from .waveform import WaveformError, extract_peaks

logger = logging.getLogger("directstream.jobs")

# queued -> downloading -> chunking -> transcribing -> finalizing -> done | error | cancelled
_TERMINAL_STATUSES = ("done", "error", "cancelled")


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
        self._tasks: dict[str, asyncio.Task] = {}
        self._subscribers: dict[str, set[asyncio.Queue[TranscriptionJob]]] = {}
        self._lock = asyncio.Lock()
        # Bounds concurrent transcription jobs across all clients -- each one
        # pins a Groq-rate-limited pipeline plus local ffmpeg CPU work.
        self.semaphore = asyncio.Semaphore(settings.transcribe_max_concurrent_jobs)
        # Bounds concurrent CPU-bound steps (ffmpeg transcode + waveform)
        # independent of how many jobs are merely waiting on a Groq network
        # round-trip, so a small VPS doesn't run several ffmpeg transcodes
        # at once.
        self.cpu_semaphore = asyncio.Semaphore(settings.transcribe_workers)

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
            # Fan out to every open SSE connection for this job (see
            # `subscribe` below) -- put_nowait is safe here since each
            # subscriber's queue is unbounded and read-then-discarded by a
            # single consuming loop, never blocking the pipeline that's
            # calling `update`.
            for queue in self._subscribers.get(job_id, ()):
                queue.put_nowait(job)

    async def subscribe(self, job_id: str) -> asyncio.Queue[TranscriptionJob]:
        """Registers a queue that receives every future `update()` for this
        job -- used by the SSE endpoint. Caller must `unsubscribe` when done
        (e.g. in a `finally`) or the queue leaks for the job's lifetime."""
        queue: asyncio.Queue[TranscriptionJob] = asyncio.Queue()
        async with self._lock:
            self._subscribers.setdefault(job_id, set()).add(queue)
        return queue

    async def unsubscribe(self, job_id: str, queue: asyncio.Queue[TranscriptionJob]) -> None:
        async with self._lock:
            subs = self._subscribers.get(job_id)
            if subs is None:
                return
            subs.discard(queue)
            if not subs:
                del self._subscribers[job_id]

    async def set_task(self, job_id: str, task: asyncio.Task) -> None:
        async with self._lock:
            self._tasks[job_id] = task

    async def cancel(self, job_id: str) -> bool:
        """Request cancellation of a running job's task.

        Returns False when the job is unknown or already terminal (nothing to
        cancel -- 404-worthy from the caller's perspective); True when the job
        existed and cancellation was requested, whether or not a task was
        actually found still running (it may already be between awaits and
        about to finish on its own).
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.is_terminal:
                return False
            task = self._tasks.get(job_id)
            if task is not None and not task.done():
                task.cancel()
            return True

    def _sweep_expired_locked(self) -> None:
        ttl = self._settings.transcribe_job_ttl
        if ttl <= 0:
            return
        now = time.monotonic()
        expired = [jid for jid, job in self._jobs.items() if now - job.created_at > ttl]
        for jid in expired:
            del self._jobs[jid]
            self._tasks.pop(jid, None)
            self._subscribers.pop(jid, None)


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

    async def _pipeline() -> None:
        async with store.semaphore:
            await store.update(
                job_id, status="downloading", step_label="Acquiring audio…", progress=0.05
            )
            async with store.cpu_semaphore:
                audio_path = await acquire_audio(formats, settings, work_dir)

            await store.update(
                job_id, status="chunking", step_label="Preparing audio…", progress=0.15
            )
            chunks = await chunk_if_needed(audio_path, work_dir, settings)

            total = len(chunks)
            results: list[TranscriptionResult | None] = [None] * total
            chunk_semaphore = asyncio.Semaphore(settings.groq_chunk_concurrency)
            completed = 0

            async def _transcribe_one(index: int) -> None:
                nonlocal completed
                async with chunk_semaphore:
                    results[index] = await transcriber.transcribe(chunks[index].path)
                completed += 1
                await store.update(
                    job_id,
                    status="transcribing",
                    step_label=f"Transcribing... ({completed} of {total} done)"
                    if total > 1
                    else "Transcribing…",
                    progress=0.2 + 0.6 * (completed / total),
                )

            chunk_tasks = [asyncio.create_task(_transcribe_one(i)) for i in range(total)]
            try:
                await asyncio.gather(*chunk_tasks)
            except BaseException:
                # gather() only propagates the first failure -- it doesn't
                # cancel sibling tasks, so without this a chunk that's still
                # mid-request would keep running (and later call
                # store.update on an already-terminal job) after we've
                # already reported the failure below.
                for t in chunk_tasks:
                    t.cancel()
                await asyncio.gather(*chunk_tasks, return_exceptions=True)
                raise

            # gather() above only returns once every _transcribe_one has set
            # its slot (or raised, in which case we never reach this line) --
            # every entry is populated by now.
            finished: list[TranscriptionResult] = [r for r in results if r is not None]
            assert len(finished) == total, "gather() completed with an unfilled result slot"
            segments_by_chunk: list[tuple[float, list[Segment]]] = [
                (chunks[i].offset_seconds, finished[i].segments) for i in range(total)
            ]
            # Chunk 0 is deterministically the start of the video -- report
            # its detected language regardless of which chunk finished first.
            language = finished[0].language

            await store.update(
                job_id, status="finalizing", step_label="Generating subtitles…", progress=0.85
            )
            merged = merge_chunks(segments_by_chunk)
            vtt_text = to_vtt(merged)
            srt_text = to_srt(merged)

            try:
                async with store.cpu_semaphore:
                    waveform = await extract_peaks(audio_path, settings)
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

    try:
        await asyncio.wait_for(_pipeline(), timeout=settings.transcribe_job_timeout)
    except TimeoutError:
        logger.warning("transcription job %s timed out", job_id)
        await store.update(
            job_id,
            status="error",
            error=f"Job timed out after {settings.transcribe_job_timeout}s",
            step_label="Failed",
        )
    except asyncio.CancelledError:
        logger.info("transcription job %s cancelled", job_id)
        await store.update(job_id, status="cancelled", step_label="Cancelled", error=None)
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
