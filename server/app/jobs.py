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
from .transcribe.base import Segment, Transcriber, TranscriptionResult
from .transcribe.groq_engine import GroqError
from .waveform import WaveformError, extract_peaks_chunks

logger = logging.getLogger("directstream.jobs")

# queued -> downloading -> chunking -> transcribing -> finalizing -> done | error | cancelled
_TERMINAL_STATUSES = ("done", "error", "cancelled")


def _return_freed_memory_to_os() -> None:
    """Ask glibc to hand freed heap arenas back to the OS after a job.

    A transcription job briefly allocates large transient buffers (per-chunk
    audio bytes for the Groq upload, PCM decode blocks for the waveform).
    CPython frees them promptly, but glibc's allocator keeps the arenas mapped
    -- so process RSS climbs job-over-job and only drops on a restart, which is
    exactly the "RAM goes up but never down" symptom. ``malloc_trim(0)`` returns
    the now-empty arenas. glibc/Linux only; a silent no-op on musl/macOS/Windows.
    """
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
    # Fine-grained sub-stage code (planning / downloading_source / extracting /
    # compressing / transcribing / building_subtitles / waveform) -- the client
    # maps it to localized text. More specific than `status`.
    detail: str | None = None
    # Chunk counters exposed on the wire so the client can render/localize
    # its own "x of y" stage text instead of parsing `step_label`.
    chunks_done: int = 0
    chunks_total: int = 0
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


# How the whole job's progress bar is divided between stages. Acquisition
# (network download + ffmpeg transcode, now with real sub-progress) dominates
# a long video's wall clock; Groq itself is fast.
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
) -> None:
    """The whole pipeline for one job: acquire audio (one ffmpeg pass off the
    source URL wherever possible) -> chunk if needed -> transcribe chunks in
    parallel across the Groq key pool, with the waveform extracted
    concurrently since it only needs the audio track -> merge -> SRT/VTT.

    Progress is continuous, not stage-jumps: acquisition reports ffmpeg's
    out_time (or download bytes) against the video's duration, and each
    transcribed chunk ticks the bar forward.
    """
    work_dir = create_work_dir()

    async def _pipeline() -> None:
        async with store.semaphore:
            await store.update(
                job_id,
                status="downloading",
                step_label="Acquiring audio…",
                detail="planning",
                progress=_ACQUIRE_START,
            )

            plan = plan_acquisition(formats, settings, duration_hint=duration_hint)

            # ----- shared finalize (both acquisition paths end here) --------
            async def _finalize(
                chunks: list[AudioChunk],
                finished: list[TranscriptionResult],
                waveform_task: asyncio.Task,
            ) -> None:
                total = len(chunks)
                segments_by_chunk: list[tuple[float, list[Segment]]] = [
                    (chunks[i].offset_seconds, finished[i].segments) for i in range(total)
                ]
                # Chunk 0 is deterministically the start of the video -- report
                # its detected language regardless of which chunk finished first.
                language = finished[0].language
                await store.update(
                    job_id,
                    status="finalizing",
                    step_label="Generating subtitles…",
                    detail="building_subtitles",
                    progress=_TRANSCRIBE_END,
                )
                merged = merge_chunks(segments_by_chunk)
                vtt_text = to_vtt(merged)
                srt_text = to_srt(merged)
                # The waveform PCM decode is usually the last thing still
                # running here -- surface it as its own stage instead of a
                # silent wait on "Generating subtitles…".
                if not waveform_task.done():
                    await store.update(
                        job_id, status="finalizing", step_label="Building waveform…",
                        detail="waveform",
                    )
                waveform = await waveform_task
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

            # ================= fast parallel-window path ====================
            # Returns True if it ran the job to completion, False if the direct
            # read is unusable (anti-bot TLS on window 0) -> caller falls back.
            async def _run_windowed(windows) -> bool:
                total = len(windows)
                extract_sem = asyncio.Semaphore(settings.transcribe_extract_parallelism)
                chunk_sem = asyncio.Semaphore(transcriber.max_concurrency)
                win_frac = [0.0] * total  # intra-window ffmpeg out_time fraction
                extracted = 0
                transcribed = 0
                chunks: list[AudioChunk | None] = [None] * total
                results: list[TranscriptionResult | None] = [None] * total
                # Every task spawned below is tracked here so a cancel/timeout
                # (or any failure) at ANY await tears down every one of them --
                # otherwise an orphaned extract task keeps its ffmpeg child
                # downloading after the job is already gone.
                spawned: list[asyncio.Task] = []

                # One continuous bar across the overlapped extract+transcribe
                # span: extraction and transcription each count for half.
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
                                    plan.url, plan.headers, work_dir, settings,
                                    plan.codec, windows[i],
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
                        status="downloading",
                        step_label=f"Extracting audio… ({extracted} of {total})"
                        if total > 1
                        else "Extracting audio…",
                        detail="extracting",
                    )
                    return chunk

                async def _transcribe(i: int) -> None:
                    nonlocal transcribed
                    chunk = await extract_tasks[i]
                    async with chunk_sem:
                        results[i] = await transcriber.transcribe(chunk.path)
                    transcribed += 1
                    await store.update(
                        job_id,
                        status="transcribing",
                        step_label=f"Transcribing… ({transcribed} of {total} done)"
                        if total > 1
                        else "Transcribing…",
                        detail="transcribing",
                        chunks_done=transcribed,
                        chunks_total=total,
                    )

                # Waveform decodes the finished chunk files (after all windows
                # land) concurrently with the Groq round-trips. Non-fatal.
                async def _waveform() -> list[float] | None:
                    try:
                        done = await asyncio.gather(*extract_tasks)
                        async with store.cpu_semaphore:
                            return await extract_peaks_chunks([c.path for c in done], settings)
                    except (WaveformError, AudioError) as exc:
                        logger.warning("waveform extraction failed for job %s: %s", job_id, exc)
                        return None

                extract_tasks = [asyncio.create_task(_extract(i)) for i in range(total)]
                spawned += extract_tasks
                try:
                    # Commit to the parallel path only if window 0's direct read
                    # works -- an anti-bot TLS rejection is deterministic per
                    # host, so one failure means every window would fail. Bail
                    # cleanly so the caller runs the impersonating single pass.
                    try:
                        await extract_tasks[0]
                    except AudioError as exc:
                        logger.warning(
                            "windowed extract failed on first window (%s) -- "
                            "falling back to single-pass",
                            str(exc)[:200],
                        )
                        return False  # finally tears the rest down + cleans files

                    waveform_task = asyncio.create_task(_waveform())
                    reporter = asyncio.create_task(_report())
                    spawned += [waveform_task, reporter]
                    await store.update(job_id, chunks_done=0, chunks_total=total)

                    transcribe_tasks = [asyncio.create_task(_transcribe(i)) for i in range(total)]
                    spawned += transcribe_tasks
                    await asyncio.gather(*transcribe_tasks)

                    reporter.cancel()
                    await asyncio.gather(reporter, return_exceptions=True)

                    finished = [r for r in results if r is not None]
                    assert len(finished) == total, "a transcription slot was left unfilled"
                    ordered_chunks = [c for c in chunks if c is not None]
                    await _finalize(ordered_chunks, finished, waveform_task)
                    return True
                finally:
                    # Runs on success (already-done tasks ignore cancel), on
                    # failure, AND on cancel/timeout -- guarantees no extract/
                    # transcribe/reporter/waveform task (and its ffmpeg child)
                    # is left running once we leave this frame.
                    for t in spawned:
                        t.cancel()
                    await asyncio.gather(*spawned, return_exceptions=True)
                    # Drop partial/leftover chunk files (matters for the
                    # fallback so its chunker doesn't pick them up).
                    if not results or any(r is None for r in results):
                        for leftover in work_dir.glob(f"chunk_*.{plan.codec.ext}"):
                            leftover.unlink(missing_ok=True)

            # ================= single-pass fallback path ====================
            async def _run_single_pass() -> None:
                await store.update(
                    job_id, status="downloading", step_label="Downloading source…",
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
                            formats, settings, work_dir,
                            duration_hint=duration_hint, on_progress=_on_acquire,
                        )
                finally:
                    reporter.cancel()
                    await asyncio.gather(reporter, return_exceptions=True)

                await store.update(
                    job_id, status="chunking", step_label="Preparing audio…",
                    detail="compressing", progress=_ACQUIRE_END,
                )
                duration = await probe_duration(audio_path, settings.ffprobe_binary)
                chunks = await chunk_audio(audio_path, work_dir, settings, duration=duration)
                await store.update(job_id, progress=_CHUNK_END)

                async def _waveform() -> list[float] | None:
                    try:
                        async with store.cpu_semaphore:
                            return await extract_peaks_chunks([c.path for c in chunks], settings)
                    except (WaveformError, AudioError) as exc:
                        logger.warning("waveform extraction failed for job %s: %s", job_id, exc)
                        return None

                waveform_task = asyncio.create_task(_waveform())

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
                        status="transcribing",
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
                        job_id, status="transcribing", step_label="Transcribing…",
                        detail="transcribing", chunks_done=0, chunks_total=total,
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
                    assert len(finished) == total, "gather() completed with an unfilled result slot"
                    await _finalize(chunks, finished, waveform_task)
                except BaseException:
                    waveform_task.cancel()
                    await asyncio.gather(waveform_task, return_exceptions=True)
                    raise

            # Prefer the parallel windows; fall back to a single pass if the
            # source is HLS/unknown-duration (no windows) or if the direct read
            # is rejected on the first window.
            if plan.windows is not None and await _run_windowed(plan.windows):
                return
            await _run_single_pass()

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
        # Return this job's freed transient buffers to the OS so RSS doesn't
        # creep upward job-over-job (see _return_freed_memory_to_os).
        _return_freed_memory_to_os()
