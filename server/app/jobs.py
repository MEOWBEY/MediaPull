"""In-memory job store for the auto-subtitle (transcription) pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from .audio import (
    AudioChunk,
    AudioError,
    acquire_audio,
    chunk_audio,
    cleanup_work_dir,
    create_work_dir,
    extract_window,
    plan_acquisition,
    probe_duration,
)
from .config import Settings
from .models import VideoFormat
from .subtitles import merge_chunks, to_srt, to_vtt
from .transcribe.base import Transcriber, TranscriptionResult
from .transcribe.groq_engine import GroqError
from .dialogue_map import DialogueMapError, extract_peaks_chunks

logger = logging.getLogger("pullbox.jobs")

_QUEUED, _DOWNLOADING, _CHUNKING, _TRANSCRIBING, _FINALIZING = (
    "queued",
    "downloading",
    "chunking",
    "transcribing",
    "finalizing",
)
_TERMINAL_STATUSES = ("done", "error", "cancelled")


def _return_freed_memory_to_os() -> None:
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


@dataclass
class TranscriptionJob:
    id: str
    status: str = "queued"
    progress: float = 0.0
    step_label: str = "Queued"
    detail: str | None = None
    chunks_done: int = 0
    chunks_total: int = 0
    language: str | None = None
    vtt_text: str | None = None
    srt_text: str | None = None
    dialogue_map: list[float] | None = None
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
        self.semaphore = asyncio.Semaphore(settings.transcribe_max_concurrent_jobs)
        self.cpu_semaphore = asyncio.Semaphore(settings.transcribe_workers)

    async def create(self) -> TranscriptionJob:
        async with self._lock:
            self._sweep_expired_locked()
            max_jobs = self._settings.transcribe_max_jobs_stored
            if len(self._jobs) >= max_jobs:
                raise RuntimeError(
                    f"Too many transcription jobs in memory (max {max_jobs}); try again later"
                )
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
            for queue in self._subscribers.get(job_id, ()):
                queue.put_nowait(job)

    async def subscribe(self, job_id: str) -> asyncio.Queue[TranscriptionJob]:
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


_ACQUIRE_START, _ACQUIRE_END = 0.02, 0.55
_CHUNK_END = 0.58
_TRANSCRIBE_END = 0.96


async def run_transcription_job(
    job_id: str,
    formats: list[VideoFormat],
    settings: Settings,
    store: JobStore,
    transcriber: Transcriber,
    duration_hint: float | None = None,
    resolve_cookie_token: Callable[[str], str] | None = None,
) -> None:
    work_dir = create_work_dir()

    async def _pipeline() -> None:
        async with store.semaphore:
            await store.update(
                job_id,
                status=_DOWNLOADING,
                step_label="Acquiring audio…",
                detail="planning",
                progress=_ACQUIRE_START,
            )

            plan = await plan_acquisition(
                formats,
                settings,
                duration_hint=duration_hint,
                resolve_cookie_token=resolve_cookie_token,
            )

            async def _finalize(
                chunks: list[AudioChunk],
                finished: list[TranscriptionResult],
                dialogue_map_task: asyncio.Task,
            ) -> None:
                total = len(chunks)
                segments_by_chunk = [
                    (chunks[i].offset_seconds, finished[i].segments) for i in range(total)
                ]
                language = finished[0].language if finished else "en"
                await store.update(
                    job_id,
                    status=_FINALIZING,
                    step_label="Generating subtitles…",
                    detail="building_subtitles",
                    progress=_TRANSCRIBE_END,
                )
                merged = merge_chunks(segments_by_chunk)
                vtt_text = to_vtt(merged)
                srt_text = to_srt(merged)
                if not dialogue_map_task.done():
                    await store.update(
                        job_id,
                        status=_FINALIZING,
                        step_label="Building dialogue map…",
                        detail="dialogue_map",
                    )
                dialogue_map = await dialogue_map_task
                await store.update(
                    job_id,
                    status="done",
                    step_label="Done",
                    progress=1.0,
                    language=language or "en",
                    vtt_text=vtt_text,
                    srt_text=srt_text,
                    dialogue_map=dialogue_map,
                )

            async def _run_windowed(windows: list) -> bool:
                total = len(windows)
                extract_sem = asyncio.Semaphore(settings.transcribe_extract_parallelism)
                chunk_sem = asyncio.Semaphore(transcriber.max_concurrency)
                win_frac = [0.0] * total
                extracted = 0
                transcribed = 0
                chunks: list[AudioChunk | None] = [None] * total
                results: list[TranscriptionResult | None] = [None] * total
                spawned: list[asyncio.Task] = []

                async def _report() -> None:
                    span = _TRANSCRIBE_END - _ACQUIRE_START
                    last = -1.0
                    while True:
                        await asyncio.sleep(0.5)
                        overall = (sum(win_frac) / total + transcribed / total) / 2
                        progress = _ACQUIRE_START + span * overall
                        if progress - last >= 0.005:
                            last = progress
                            await store.update(job_id, progress=progress)

                async def _extract(i: int) -> AudioChunk:
                    nonlocal extracted
                    attempt = 0
                    while True:
                        try:
                            async with extract_sem, store.cpu_semaphore:
                                chunk = await extract_window(
                                    plan.url,
                                    plan.headers,
                                    work_dir,
                                    settings,
                                    plan.codec,
                                    windows[i],
                                    on_progress=lambda f, i=i: win_frac.__setitem__(i, min(f, 1.0)),
                                )
                            break
                        except AudioError:
                            attempt += 1
                            if attempt > settings.max_retries:
                                raise
                            await asyncio.sleep(min(2**attempt, 10))
                    win_frac[i] = 1.0
                    chunks[i] = chunk
                    extracted += 1
                    await store.update(
                        job_id,
                        status=_DOWNLOADING,
                        step_label=f"Extracting audio… ({extracted} of {total})"
                        if total > 1
                        else "Extracting audio…",
                        detail="extracting",
                    )
                    return chunk

                extract_tasks: list[asyncio.Task] = []

                async def _dialogue_map() -> list[float] | None:
                    try:
                        done = await asyncio.gather(*extract_tasks)
                        async with store.cpu_semaphore:
                            return await extract_peaks_chunks(
                                [c.path for c in done], settings
                            )
                    except (DialogueMapError, AudioError) as exc:
                        logger.warning("dialogue map extraction failed for job %s: %s", job_id, exc)
                        return None

                async def _transcribe(i: int) -> None:
                    nonlocal transcribed
                    chunk = await extract_tasks[i]
                    async with chunk_sem:
                        results[i] = await transcriber.transcribe(chunk.path)
                    transcribed += 1
                    await store.update(
                        job_id,
                        status=_TRANSCRIBING,
                        step_label=f"Transcribing… ({transcribed} of {total} done)"
                        if total > 1
                        else "Transcribing…",
                        detail="transcribing",
                        chunks_done=transcribed,
                        chunks_total=total,
                    )

                # Probe window 0 first to avoid spawning N tasks that would all
                # fail on the same anti-bot TLS rejection.
                probe_task = asyncio.create_task(_extract(0))
                spawned.append(probe_task)
                try:
                    await probe_task
                except AudioError as exc:
                    logger.warning(
                        "windowed extract failed on first window (%s) -- falling back to single-pass",
                        str(exc)[:200],
                    )
                    return False

                extract_tasks = [probe_task] + [
                    asyncio.create_task(_extract(i)) for i in range(1, total)
                ]
                spawned.extend(extract_tasks[1:])

                dialogue_map_task = asyncio.create_task(_dialogue_map())
                reporter = asyncio.create_task(_report())
                spawned += [dialogue_map_task, reporter]
                await store.update(job_id, chunks_done=0, chunks_total=total)

                transcribe_tasks = [
                    asyncio.create_task(_transcribe(i)) for i in range(total)
                ]
                spawned += transcribe_tasks

                try:
                    await asyncio.gather(*transcribe_tasks)
                finally:
                    # Teardown on success, failure, AND cancel/timeout — guarantees
                    # no extract/transcribe/reporter/dialogue_map task (and its
                    # ffmpeg child) outlives this frame.
                    for t in spawned:
                        if not t.done():
                            t.cancel()
                    await asyncio.gather(*spawned, return_exceptions=True)
                    if not results or any(r is None for r in results):
                        for leftover in work_dir.glob(f"chunk_*.{plan.codec.ext}"):
                            leftover.unlink(missing_ok=True)

                finished = [r for r in results if r is not None]
                if len(finished) != total:
                    raise GroqError(
                        f"Transcription incomplete: {len(finished)}/{total} chunks "
                        "returned no result — the Groq API may have dropped a request"
                    )
                ordered_chunks = [c for c in chunks if c is not None]
                await _finalize(ordered_chunks, finished, dialogue_map_task)
                return True

            async def _run_single_pass() -> None:
                await store.update(
                    job_id,
                    status=_DOWNLOADING,
                    step_label="Downloading source…",
                    detail="downloading_source",
                )
                acquire_frac = 0.0

                def _on_acquire(frac: float) -> None:
                    nonlocal acquire_frac
                    acquire_frac = max(acquire_frac, min(frac, 1.0))

                async def _report_acquire() -> None:
                    span = _ACQUIRE_END - _ACQUIRE_START
                    last = -1.0
                    while True:
                        await asyncio.sleep(0.5)
                        progress = _ACQUIRE_START + span * acquire_frac
                        if progress - last >= 0.005:
                            last = progress
                            await store.update(job_id, progress=progress)

                reporter = asyncio.create_task(_report_acquire())
                try:
                    async with store.cpu_semaphore:
                        audio_path = await acquire_audio(
                            formats,
                            settings,
                            work_dir,
                            duration_hint=duration_hint,
                            on_progress=_on_acquire,
                            resolve_cookie_token=resolve_cookie_token,
                        )
                finally:
                    reporter.cancel()
                    await asyncio.gather(reporter, return_exceptions=True)

                await store.update(
                    job_id,
                    status=_CHUNKING,
                    step_label="Preparing audio…",
                    detail="compressing",
                    progress=_ACQUIRE_END,
                )
                duration = await probe_duration(audio_path, settings.ffprobe_binary)
                chunks = await chunk_audio(audio_path, work_dir, settings, duration=duration)
                await store.update(job_id, progress=_CHUNK_END)

                async def _dialogue_map() -> list[float] | None:
                    try:
                        async with store.cpu_semaphore:
                            return await extract_peaks_chunks(
                                [c.path for c in chunks], settings
                            )
                    except (DialogueMapError, AudioError) as exc:
                        logger.warning("dialogue map extraction failed for job %s: %s", job_id, exc)
                        return None

                dialogue_map_task = asyncio.create_task(_dialogue_map())

                total = len(chunks)
                results: list[TranscriptionResult | None] = [None] * total
                chunk_semaphore = asyncio.Semaphore(transcriber.max_concurrency)
                completed = 0

                async def _transcribe_one(index: int) -> None:
                    nonlocal completed
                    async with chunk_semaphore:
                        results[index] = await transcriber.transcribe(chunks[index].path)
                    completed += 1
                    span = _TRANSCRIBE_END - _CHUNK_END
                    await store.update(
                        job_id,
                        status=_TRANSCRIBING,
                        step_label=f"Transcribing... ({completed} of {total} done)"
                        if total > 1
                        else "Transcribing…",
                        detail="transcribing",
                        chunks_done=completed,
                        chunks_total=total,
                        progress=_CHUNK_END + span * (completed / total),
                    )

                try:
                    await store.update(
                        job_id,
                        status=_TRANSCRIBING,
                        step_label="Transcribing…",
                        detail="transcribing",
                        chunks_done=0,
                        chunks_total=total,
                    )
                    chunk_tasks = [asyncio.create_task(_transcribe_one(i)) for i in range(total)]
                    try:
                        await asyncio.gather(*chunk_tasks)
                    except BaseException:
                        for t in chunk_tasks:
                            t.cancel()
                        await asyncio.gather(*chunk_tasks, return_exceptions=True)
                        raise
                    finished: list[TranscriptionResult] = [r for r in results if r is not None]
                    if len(finished) != total:
                        raise GroqError(
                            f"Transcription incomplete: {len(finished)}/{total} chunks "
                            "returned no result on the single-pass path"
                        )
                    await _finalize(chunks, finished, dialogue_map_task)
                except BaseException:
                    dialogue_map_task.cancel()
                    await asyncio.gather(dialogue_map_task, return_exceptions=True)
                    raise

            try:
                if plan.windows is not None:
                    ok = await _run_windowed(plan.windows)
                    if ok:
                        return
                await _run_single_pass()
            finally:
                cleanup_work_dir(work_dir)
                _return_freed_memory_to_os()

    try:
        await asyncio.wait_for(_pipeline(), timeout=settings.transcribe_job_timeout)
    except asyncio.CancelledError:
        logger.info("transcription job %s cancelled", job_id)
        await store.update(job_id, status="cancelled", step_label="Cancelled", progress=1.0)
    except asyncio.TimeoutError:
        # wait_for cancels _pipeline(), so its finally blocks still tear down
        # every spawned task and ffmpeg child. Report the cap as an error.
        logger.warning(
            "transcription job %s exceeded %ss wall-clock cap -- killed",
            job_id,
            settings.transcribe_job_timeout,
        )
        await store.update(
            job_id,
            status="error",
            step_label="Timed out",
            progress=1.0,
            error=(
                f"Transcription exceeded the {settings.transcribe_job_timeout}s time "
                "limit and was stopped. Try a shorter source or raise "
                "TRANSCRIBE_JOB_TIMEOUT."
            ),
        )
    except Exception as exc:
        logger.exception("transcription job %s failed", job_id)
        # AudioError/DialogueMapError/GroqError always carry an actionable message
        # (see their raise sites) -- str(exc) is empty here only for a raw,
        # unanticipated exception bubbling up from a dependency. Showing the
        # bare class name (e.g. "NotImplementedError") to the user is useless;
        # a generic-but-honest message beats that while the log line above
        # still has the real traceback for debugging.
        error = str(exc) or (
            f"Transcription failed unexpectedly ({type(exc).__name__}). "
            "Please try again or use a different video."
        )
        await store.update(
            job_id,
            status="error",
            step_label="Error",
            progress=1.0,
            error=error,
        )
