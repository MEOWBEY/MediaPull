"""Audio split jobs for the /split-audio endpoints.

Splits the audio track out of a media file into a standalone mp3 -- either
from a local upload (POST /split-audio/local) or a URL the server downloads
(POST /split-audio/url).

ffmpeg drops the video track and re-encodes the audio to an mp3 that lives in
a temp file for SPLIT_AUDIO_TTL seconds, then is deleted automatically. The
client polls /split-audio/{id}/status and downloads from
/split-audio/{id}/file once status == "done".
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from . import proc_util
from .config import Settings

logger = logging.getLogger("mediapull.split_audio")


# ffmpeg stderr time-of-day forms, newest first. All map to elapsed seconds.
_FFMPEG_TIME_PATTERNS = (
    (re.compile(r"(?:out_time_us|time_us)=(\d+)"), 1e-6),  # microseconds
    (re.compile(r"(?:out_time_ms|time_ms)=(\d+)"), 1e-3),  # milliseconds
    (re.compile(r"(?:out_time|time)=(\d+):(\d+):(\d{2}(?:\.\d+)?)"), "clock"),
)


class FfmpegProgress:
    """Parses ffmpeg's stderr progress lines into 0..1 completion.

    ffmpeg prints a stream of `time=`/`out_time` progress lines while
    encoding; the input duration arrives early ("Duration:"). Until the
    duration is seen we report None (stay put client-side) rather than guess.
    Once encoding starts, we report at least 0.1 even before Duration appears.
    """

    _duration_re = re.compile(r"Duration:\s*(\d+):(\d+):(\d{2}(?:\.\d+)?)")

    def __init__(self) -> None:
        self._duration: float | None = None
        self._seen_progress = False

    def push(self, line: str) -> float | None:
        if self._duration is None:
            m = self._duration_re.search(line)
            if m:
                h, mi, s = m.groups()
                self._duration = int(h) * 3600 + int(mi) * 60 + float(s)

        clock = _parse_ffmpeg_clock(line)
        if clock is not None:
            self._seen_progress = True

        if self._duration is None or self._duration <= 0:
            # No duration yet, but if we've seen any progress line, report 0.1
            # so progress doesn't stay stuck at initial 0.05 for short files.
            return 0.1 if self._seen_progress else None

        if clock is None:
            return None

        return min(clock / self._duration, 1.0)


def _parse_ffmpeg_clock(line: str) -> float | None:
    for pattern, scale in _FFMPEG_TIME_PATTERNS:
        m = pattern.search(line)
        if not m:
            continue
        if scale == "clock":
            h, mi, s = m.groups()
            return int(h) * 3600 + int(mi) * 60 + float(s)
        return int(m.group(1)) * scale
    return None


@dataclass
class SplitAudioJob:
    id: str
    status: str = "queued"  # queued | splitting | done | error | cancelled
    progress: float = 0.0
    error: str | None = None
    # Absolute path to the output audio file (set once splitting starts).
    output_path: Path | None = None
    filename: str | None = None
    step_label: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    # Client IP stamped at creation (from the request context) so the admin
    # panel can see who started what.
    client_ip: str = "-"


class SplitAudioStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jobs: dict[str, SplitAudioJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    def _sweep_expired(self) -> None:
        ttl = self._settings.split_audio_ttl
        now = time.monotonic()
        expired = [jid for jid, j in self._jobs.items() if now - j.created_at > ttl]
        for jid in expired:
            job = self._jobs.pop(jid)
            if job.output_path:
                job.output_path.unlink(missing_ok=True)
            # A running job that outlives its TTL still gets cleaned up here; the
            # task reference goes too, so cancel() can't reach it anymore.
            self._tasks.pop(jid, None)

    async def create(self) -> SplitAudioJob:
        async with self._lock:
            self._sweep_expired()
            job = SplitAudioJob(id=uuid.uuid4().hex)
            self._jobs[job.id] = job
            return job

    def attach(self, job_id: str, task: asyncio.Task) -> None:
        """Link the background run to its job so a cancel can stop ffmpeg."""
        self._tasks[job_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(job_id, None))

    async def get(self, job_id: str) -> SplitAudioJob | None:
        async with self._lock:
            self._sweep_expired()
            return self._jobs.get(job_id)

    async def all(self) -> list[SplitAudioJob]:
        async with self._lock:
            self._sweep_expired()
            return list(self._jobs.values())

    async def cancel(self, job_id: str) -> bool:
        """Stop a running split: kill its ffmpeg child (the job's cancel path
        unlinks the temp file) and mark it cancelled. False if there is
        nothing left to cancel."""
        async with self._lock:
            self._sweep_expired()
            job = self._jobs.get(job_id)
            if job is None or job.status in ("done", "error"):
                return False
            task = self._tasks.get(job_id)
            if task is not None and not task.done():
                task.cancel()
            job.status = "cancelled"
            return True

    async def update(self, job_id: str, **fields: object) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)


async def _drain_ffmpeg_stderr(
    proc: subprocess.Popen,
    progress: FfmpegProgress,
    on_progress: Callable[[float], Awaitable[None]],
) -> bytes:
    """Read ffmpeg's stderr line-by-line off the event loop, feeding each line
    to FfmpegProgress and awaiting the resulting progress updates. Returns the
    full stderr for error reporting (the same contract as
    proc_util.communicate). The blocking reads happen on a worker thread, so
    nothing here blocks the event loop: it works under uvicorn's
    SelectorEventLoop too (see proc_util's docstring)."""
    loop = asyncio.get_running_loop()
    queue: "asyncio.Queue[bytes | None]" = asyncio.Queue()

    def _read() -> None:
        assert proc.stderr is not None
        for raw in iter(proc.stderr.readline, b""):
            loop.call_soon_threadsafe(queue.put_nowait, raw)
        loop.call_soon_threadsafe(queue.put_nowait, None)

    reading = asyncio.create_task(asyncio.to_thread(_read))
    chunks: list[bytes] = []
    try:
        while True:
            raw = await queue.get()
            if raw is None:
                break
            chunks.append(raw)
            frac = progress.push(raw.decode("utf-8", errors="replace"))
            if frac is not None:
                await on_progress(frac)
    finally:
        if not reading.done():
            reading.cancel()
        # Popen.returncode only becomes meaningful once wait()/poll() has been
        # called (the drain above only proves stderr hit EOF).
        await asyncio.to_thread(proc.wait)
    return b"".join(chunks)


async def run_split_audio_job(
    job_id: str,
    source: "Path | str",
    output_filename: str,
    store: SplitAudioStore,
    settings: Settings,
    *,
    headers: dict[str, str] | None = None,
    protocol: str | None = None,
    delete_source: bool = False,
) -> None:
    """Split audio off source (a local Path or an HTTP URL) into a temp mp3.

    URL sources are read by ffmpeg directly, using the same input args as the
    transcription pipeline (``audio._url_input_args``: proxy, the source's own
    Referer/Cookie/UA headers, HLS extension allow-list, per-read timeout).
    Hosts that reject ffmpeg's plain TLS (anti-bot CDNs) get the SAME fallback
    transcribe uses: a curl_cffi download with browser impersonation, then a
    local split -- instead of failing the job with "Server returned 4XX".
    The whole download+split shares one wall-clock cap (split_audio_ttl).
    """
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=".mp3", prefix="mediapull-split-")
    output_path = Path(tmp_path_str)
    os.close(tmp_fd)

    source_arg = source if isinstance(source, str) else str(source)
    is_url = isinstance(source, str)
    is_hls = is_url and protocol == "m3u8_native"

    async def _attempt(
        input_args: list[str], src: str, progress_lo: float, progress_span: float
    ) -> tuple[str, str]:
        """Run ONE ffmpeg split pass. Returns ``(outcome, stderr)`` where
        outcome is "ok", "failed", or "timeout". A timeout is terminal: the
        output is deleted and the job marked errored (the caller must stop).

        Progress is ``progress_lo + frac * progress_span`` from ffmpeg's
        ``time=`` lines -- plus a slow gentle FLOOR that starts climbing a
        couple ticks after the pass starts, so a phase ffmpeg hasn't reported
        into yet (a slow URL read, a remote file being digitalized) still
        moves the bar in small steps like the transcription pipeline does,
        instead of parking at the window's start until "done".
        """
        floor = {"v": progress_lo}

        async def _creep_floor() -> None:
            step = progress_span * 0.006
            cap = progress_lo + progress_span * 0.85
            await asyncio.sleep(0.5 * 4)  # grace: let real first ticks win
            while True:
                await asyncio.sleep(0.5)
                floor["v"] = min(floor["v"] + step, cap)
                job = await store.get(job_id)
                if job is not None and floor["v"] > job.progress:
                    await store.update(job_id, progress=floor["v"])

        args = [settings.ffmpeg_path, "-y"]
        args += input_args
        args += [
            "-i", src,
            "-vn",
            "-c:a", "libmp3lame",
            "-q:a", "2",
            "-map_metadata", "0",
            str(output_path),
        ]

        progress = FfmpegProgress()

        async def _on_progress(frac: float) -> None:
            real = progress_lo + min(frac, 1.0) * progress_span
            await store.update(job_id, progress=max(real, floor["v"]))

        proc = await proc_util.spawn(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # `guarded`, not a bare asyncio.wait_for: it kills + reaps the ffmpeg
        # child on BOTH timeout and cancellation, so a wedged split can't leave
        # a zombie process behind (see proc_util for why this job can't use
        # native asyncio subprocesses).
        creep = asyncio.create_task(_creep_floor())
        try:
            _, stderr_bytes = (None, await proc_util.guarded(
                lambda: _drain_ffmpeg_stderr(proc, progress, _on_progress),
                proc=proc,
                timeout=float(settings.split_audio_ttl),
            ))
        except TimeoutError:
            logger.warning(
                "split-audio job %s exceeded %ss wall-clock cap -- killed",
                job_id,
                settings.split_audio_ttl,
            )
            output_path.unlink(missing_ok=True)
            await store.update(
                job_id,
                status="error",
                error=(
                    f"Split audio exceeded the {settings.split_audio_ttl}s time "
                    "limit and was stopped."
                ),
            )
            return "timeout", ""
        finally:
            creep.cancel()
            await asyncio.gather(creep, return_exceptions=True)

        if proc.returncode != 0:
            return "failed", (stderr_bytes or b"").decode("utf-8", errors="replace")
        return "ok", ""

    try:
        # step_label is left None so the client falls back to its own i18n key
        # (t('localFile.splittingAudio')) — which renders in the user's language.
        await store.update(job_id, status="splitting", progress=0.05, step_label=None)

        if is_url:
            from .audio import _download_stream, _url_input_args
            input_args = _url_input_args(source_arg, headers, settings, hls=is_hls)
        else:
            input_args = []

        outcome, stderr_text = await _attempt(input_args, source_arg, 0.05, 0.9)
        if outcome == "timeout":
            return
        if outcome == "failed" and is_url and not is_hls:
            # Direct read rejected (anti-bot CDN) — retry the way the
            # transcription pipeline does: impersonated download (first ~50%
            # of the step), then local split (the rest).
            logger.warning(
                "split-audio job %s: direct ffmpeg read failed (%s) -- "
                "retrying via impersonated download",
                job_id,
                stderr_text.strip()[-200:],
            )
            work_dir = Path(tempfile.mkdtemp(prefix="mediapull-split-dl-"))
            try:
                dl_frac = 0.0

                def _on_download(frac: float) -> None:
                    nonlocal dl_frac
                    dl_frac = max(dl_frac, min(frac, 1.0))

                async def _report_download(dest: Path) -> None:
                    """Report actual byte progress when the server discloses a
                    Content-Length (``dl_frac``); otherwise creep while bytes
                    keep arriving so the bar still inches forward in small
                    steps instead of sitting at 5% for a long download."""
                    last = -1.0
                    last_size = 0
                    creep = 0.0
                    idle_ticks = 0
                    while True:
                        await asyncio.sleep(0.5)
                        try:
                            size = dest.stat().st_size
                        except OSError:
                            size = 0
                        growing = size > last_size
                        last_size = size
                        if growing:
                            creep = min(creep + 0.015, 0.5)
                            idle_ticks = 0
                        else:
                            idle_ticks += 1
                        # A Content-Length reported by the server outranks the
                        # creep; the creep holds when the header was absent.
                        frac = max(dl_frac, creep)
                        if idle_ticks > 8:
                            frac = dl_frac  # download stuck: stop pretending
                        progress = 0.05 + frac * 0.5
                        if progress - last >= 0.01:
                            last = progress
                            await store.update(job_id, progress=progress)

                ext = Path(urlparse(source_arg).path).suffix.lstrip(".") or "mp4"
                dest = work_dir / f"source.{ext}"
                reporter = asyncio.create_task(_report_download(dest))
                try:
                    downloaded = await _download_stream(
                        source_arg,
                        headers or {},
                        ext,
                        settings,
                        work_dir,
                        on_progress=_on_download,
                    )
                finally:
                    reporter.cancel()
                    await asyncio.gather(reporter, return_exceptions=True)

                outcome, stderr_text = await _attempt([], str(downloaded), 0.55, 0.4)
                if outcome == "timeout":
                    return
            except Exception as exc:  # noqa: BLE001 - surface as a clean error
                logger.error("split-audio job %s impersonated download failed: %s", job_id, exc)
                outcome, stderr_text = "failed", str(exc)
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)

        if outcome != "ok":
            # Distinguish "no audio track" from a generic ffmpeg failure so the
            # client can show a meaningful message instead of a generic error.
            logger.error("split-audio ffmpeg failed (job %s): %s", job_id, stderr_text[-400:])
            output_path.unlink(missing_ok=True)
            no_audio = (
                "does not contain any stream" in stderr_text
                or "Output file #0 does not contain" in stderr_text
                or "no streams" in stderr_text
            )
            await store.update(
                job_id,
                status="error",
                error=(
                    "no_audio_stream"
                    if no_audio
                    else f"Audio split failed: {stderr_text.strip()[-300:]}"
                ),
            )
            return

        await store.update(
            job_id,
            status="done",
            progress=1.0,
            output_path=output_path,
            filename=output_filename,
            step_label="Done",
        )
        logger.info("split-audio job %s done: %s", job_id, output_path)

    except asyncio.CancelledError:
        output_path.unlink(missing_ok=True)
        # A user cancel marks status="cancelled" first (store.cancel); a
        # cancellation that wasn't requested (e.g. app shutdown) is an error.
        current = await store.get(job_id)
        if current is not None and current.status != "cancelled":
            await store.update(job_id, status="error", error="Cancelled")
    except Exception as exc:  # noqa: BLE001
        output_path.unlink(missing_ok=True)
        logger.error("split-audio job %s failed: %s", job_id, exc)
        await store.update(job_id, status="error", error=str(exc))
    finally:
        if delete_source and isinstance(source, Path):
            source.unlink(missing_ok=True)