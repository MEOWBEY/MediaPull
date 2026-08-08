"""Audio acquisition + ffmpeg extraction/chunking for the transcription pipeline.

This is the ONLY place in the app that writes media bytes to disk. It runs
exclusively inside an explicit, opt-in ``POST /transcribe`` job -- extraction
(``extractor.py``) always resolves URLs with ``download=False`` and that
invariant is untouched by this module.

Built for latency: ffmpeg reads the source URL directly whenever it can (HLS
*and* progressive), so downloading and transcoding are one overlapped pass
with nothing but the final mono/16kHz/32kbps opus track ever touching disk.
Only when a host rejects ffmpeg's plain TLS (anti-bot CDNs) does it fall back
to a two-step: curl_cffi download with browser impersonation, then a
local transcode. Every step reports real progress -- ffmpeg's ``-progress``
stream for transcodes, byte counts for downloads -- so the job can show the
user an honest percentage instead of a stalled bar.
"""

from __future__ import annotations

import asyncio
import logging
import math
import shutil
import subprocess
import tempfile
from collections import namedtuple
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from curl_cffi.requests import AsyncSession

from . import proc_util
from .config import Settings
from .models import VideoFormat
from .net_common import impersonate_kwarg
from .ssrf import assert_public_resolved_url

logger = logging.getLogger("mediapull.audio")

# One shared curl_cffi session for the impersonated-download fallback, reused
# across transcription jobs instead of built per download -- mirrors how
# ProxyService and Extractor hold a single long-lived session, so we don't pay
# a fresh connection-pool + TLS setup on every job that falls back to it. Keyed
# by proxy so a config that routes through a different egress still gets a
# correct session. Created lazily (the fallback path is rarely hit) and closed
# on shutdown via ``close_download_session`` (wired into the app lifespan).
_download_sessions: dict[str | None, AsyncSession] = {}


def _get_download_session(settings: Settings) -> AsyncSession:
    proxy = settings.proxy_url or None
    session = _download_sessions.get(proxy)
    if session is None:
        session = AsyncSession(
            timeout=settings.request_timeout,
            proxies={"http": proxy, "https": proxy} if proxy else None,
        )
        _download_sessions[proxy] = session
    return session


async def close_download_session() -> None:
    """Close every shared download session. Idempotent -- safe to call on
    shutdown even if the fallback download path was never exercised."""
    sessions = list(_download_sessions.values())
    _download_sessions.clear()
    for session in sessions:
        await session.close()


# Intermediate audio codecs Whisper accepts, keyed by the TRANSCRIBE_AUDIO_CODEC
# setting. Each carries the ffmpeg output args (always mono/16kHz -- Whisper's
# native rate) and an approximate encoded-bytes-per-second, used only to size
# time windows so a chunk stays under Groq's upload cap. All drop the video
# track (-vn). opus: tiny (voip mode is speech-tuned and cheap); wav: raw PCM,
# zero encode CPU but ~8x larger; flac: fast lossless, roughly half of PCM.
@dataclass(frozen=True)
class _Codec:
    ext: str
    args: tuple[str, ...]
    bytes_per_second: float


_CODECS: dict[str, _Codec] = {
    "opus": _Codec(
        ext="opus",
        args=("-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "32k",
              "-application", "voip"),
        bytes_per_second=4_000.0,  # 32kbps
    ),
    "wav": _Codec(
        ext="wav",
        args=("-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"),
        bytes_per_second=32_000.0,  # 16kHz * 2 bytes
    ),
    "flac": _Codec(
        ext="flac",
        args=("-vn", "-ac", "1", "-ar", "16000", "-c:a", "flac"),
        bytes_per_second=18_000.0,  # ~55% of PCM for speech
    ),
}
_DEFAULT_CODEC = "opus"


def resolve_codec(name: str) -> _Codec:
    """Map the ``TRANSCRIBE_AUDIO_CODEC`` setting to a codec, defaulting to
    opus for any unrecognized value rather than failing the job."""
    codec = _CODECS.get((name or "").strip().lower())
    if codec is None:
        logger.warning("unknown TRANSCRIBE_AUDIO_CODEC %r -- falling back to opus", name)
        return _CODECS[_DEFAULT_CODEC]
    return codec


# Auto-pick order: cheapest CPU (biggest output) first. wav = raw PCM, zero
# encode work; flac = fast lossless; opus = most CPU but tiny. The picker walks
# this list and takes the FIRST whose whole track still fits one upload window,
# so a short clip skips the encode entirely and only a long one pays for opus.
_AUTO_ORDER = ("wav", "flac", "opus")


def build_custom_codec(settings: Settings) -> _Codec:
    """A ``_Codec`` from the ``TRANSCRIBE_CUSTOM_*`` settings (custom mode).
    Falls back to the opus preset when no custom args are configured so a
    half-set custom mode degrades gracefully instead of failing the job."""
    args = settings.transcribe_custom_ffmpeg_arg_list
    if not args:
        logger.warning(
            "TRANSCRIBE_MODE=custom but TRANSCRIBE_CUSTOM_FFMPEG_ARGS is empty -- "
            "using the opus preset"
        )
        return _CODECS[_DEFAULT_CODEC]
    ext = (settings.transcribe_custom_ext or "opus").strip().lstrip(".") or "opus"
    return _Codec(
        ext=ext,
        args=tuple(args),
        bytes_per_second=settings.transcribe_custom_bytes_per_second,
    )


def choose_codec(
    settings: Settings, *, duration_hint: float | None, cap_bytes: int
) -> _Codec:
    """Decide how the audio fed to Whisper is encoded.

    * ``custom`` mode -> the operator's own ffmpeg args (``build_custom_codec``).
    * ``auto`` mode   -> the fastest encode (least CPU) whose whole track still
      fits one upload window: wav if it fits, else flac, else opus. A track too
      long to fit even as opus still uses opus and gets windowed/chunked under
      the cap downstream. Unknown duration -> the ``TRANSCRIBE_AUDIO_CODEC``
      fallback (opus by default), the safe small choice when we can't size it.
    """
    if (settings.transcribe_mode or "auto").strip().lower() == "custom":
        return build_custom_codec(settings)

    if not duration_hint or duration_hint <= 0:
        return resolve_codec(settings.transcribe_audio_codec)

    budget = 0.8 * cap_bytes  # same headroom plan_windows targets
    for name in _AUTO_ORDER:
        codec = _CODECS[name]
        if codec.bytes_per_second * duration_hint <= budget:
            logger.info(
                "auto codec: %s (%.0fs track ~%.1fMB fits %.0fMB cap window)",
                name,
                duration_hint,
                codec.bytes_per_second * duration_hint / 1e6,
                cap_bytes / 1e6,
            )
            return codec
    logger.info("auto codec: opus (%.0fs track needs chunking under the cap)", duration_hint)
    return _CODECS["opus"]

# Fallback chunk length for the single-pass path (HLS / unknown-duration), where
# we can't window the extraction itself. At 32kbps opus this is ~1.2MB, far
# under the cap. The fast parallel path sizes its own windows from the cap and
# the extract parallelism instead (see ``plan_windows``).
CHUNK_SECONDS = 300
# Don't split when the whole track fits in one chunk plus slack -- a second
# request for 20 trailing seconds costs more than it saves.
_CHUNK_SLACK = 1.15

# Network-reading ffmpeg runs (extraction) get a generous cap -- the job's own
# wall-clock timeout is the real guard; this only reaps a fully wedged child.
_FFMPEG_EXTRACT_TIMEOUT = 900
# Local-only re-mux (segmenting) is disk-speed, never minutes.
_FFMPEG_SEGMENT_TIMEOUT = 120
# ffprobe is just reading a local file's metadata (no network).
_FFPROBE_TIMEOUT = 30
# ffmpeg's own per-read network timeout (microseconds) -- 30s.
_FFMPEG_RW_TIMEOUT = "30000000"
# Redirect-hop cap for the fallback curl_cffi download (matches the proxy's).
_MAX_DOWNLOAD_REDIRECTS = 5

# Reports fractional progress of one step, 0.0..1.0.
ProgressFn = Callable[[float], None]


def _unwrap_proxied(
    url: str,
    *,
    resolve_cookie_token: Callable[[str], str] | None = None,
) -> tuple[str, dict[str, str]]:
    """Recover the real source URL + headers from our own ``/proxy-video``
    wrapper, so server-side acquisition fetches the origin **directly** (with
    curl_cffi impersonation / ffmpeg ``-headers``) instead of bouncing back
    through the proxy.

    The proxy is for the browser, which can't set Referer/Cookie/User-Agent on
    a media element. ffmpeg and curl_cffi can, and going direct avoids a slow
    double-hop and the proxy's segment-extension rewriting that breaks ffmpeg's
    HLS demuxer. Non-proxied URLs pass through unchanged.

    Auth cookies travel ONLY as opaque ``ctok`` tokens -- a raw ``cookies=``
    query parameter is never honored (cookies in URLs leak through access logs
    and referrers). Pass ``resolve_cookie_token`` from
    ``ProxyService.resolve_cookie_token`` so the transcription path can restore
    the Cookie header server-side.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return url, {}

    if not parsed.path.endswith("/proxy-video"):
        return url, {}

    qs = parse_qs(parsed.query)
    real = (qs.get("url") or [None])[0]
    if not real:
        return url, {}

    headers: dict[str, str] = {}
    if qs.get("referer"):
        headers["Referer"] = qs["referer"][0]
    if qs.get("userAgent"):
        headers["User-Agent"] = qs["userAgent"][0]
    ctok = (qs.get("ctok") or [None])[0]
    if ctok and resolve_cookie_token is not None:
        cookies = resolve_cookie_token(ctok)
        if cookies:
            headers["Cookie"] = cookies
    return real, headers


class AudioError(Exception):
    """Raised when audio acquisition/extraction/chunking fails."""




AudioChunk = namedtuple("AudioChunk", ["path", "offset_seconds"])


@dataclass(frozen=True)
class Window:
    """One planned extraction slice: ``length`` seconds of audio starting at
    ``start`` seconds into the source. ``index`` fixes chunk order (and thus
    the output filename) independent of which window finishes extracting first."""
    index: int
    start: float
    length: float


def plan_windows(
    duration: float, codec: _Codec, cap_bytes: int, parallelism: int
) -> list[Window]:
    """Slice ``[0, duration]`` into contiguous windows that each stay under the
    Groq upload cap while giving the extract pool something to parallelize.

    The window length is the smaller of:
      * ``cap_seconds`` -- the longest slice whose encoded size stays under
        ~80% of the cap (margin for VBR/container overhead), and
      * an even split into ``parallelism`` pieces -- so a short-enough video
        still fans out across the workers instead of becoming one big window.
    """
    cap_seconds = 0.8 * cap_bytes / codec.bytes_per_second
    if cap_seconds <= 0:
        cap_seconds = duration
    even_split = duration / max(parallelism, 1)
    window = max(1.0, min(cap_seconds, even_split))
    count = max(1, math.ceil(duration / window))
    return [
        Window(index=i, start=i * window, length=min(window, duration - i * window))
        for i in range(count)
    ]


@dataclass(frozen=True)
class AcquisitionPlan:
    """What the job needs to acquire audio. ``windows`` is the fast parallel
    path (each extracted straight off ``url`` via a Range read); ``None`` means
    fall back to the single-pass ``acquire_audio`` (HLS, unknown duration, or a
    socks proxy ffmpeg can't use)."""
    codec: _Codec
    url: str
    headers: dict[str, str]
    windows: list[Window] | None


async def plan_acquisition(
    formats: list[VideoFormat],
    settings: Settings,
    *,
    duration_hint: float | None,
    resolve_cookie_token: Callable[[str], str] | None = None,
) -> AcquisitionPlan:
    """Decide how to pull the audio: parallel cap-sized windows when the source
    is progressive and its duration is known, else the single-pass fallback.

    When the client didn't send a duration, probe the picked source directly
    (``probe_duration_url``) before giving up on windowing -- a cheap metadata
    read that keeps the fast path available for unknown-duration sources instead
    of dropping every one of them to the slow single connection."""
    fmt = pick_audio_format(formats)
    real_url, extra_headers = _unwrap_proxied(
        fmt.url or "", resolve_cookie_token=resolve_cookie_token
    )
    # Resolve-and-check (not just the string gate): a transcribe request could
    # name a public-looking host that resolves to a private address. Residual
    # gap: ffmpeg fetches the URL itself and follows origin redirects with no
    # DNS re-check; only the curl_cffi fallback path re-gates every hop.
    try:
        await assert_public_resolved_url(real_url)
    except ValueError as exc:
        raise AudioError(str(exc)) from exc
    headers = {**(fmt.http_headers or {}), **extra_headers}
    is_hls = fmt.protocol == "m3u8_native"

    # No duration from the client -> probe it ourselves so windowing stays on
    # the table. HLS can't be windowed regardless, so don't spend a probe on it.
    if (duration_hint is None or duration_hint <= 0) and not is_hls:
        probed = await probe_duration_url(real_url, headers, settings, hls=is_hls)
        if probed:
            logger.info("planning: probed source duration %.0fs (client sent none)", probed)
            duration_hint = probed

    # Duration may have just been filled in by the probe -- pick the codec after,
    # so the auto-codec sizing sees it too.
    codec = choose_codec(
        settings,
        duration_hint=duration_hint,
        cap_bytes=settings.transcribe_max_upload_bytes,
    )

    socks_proxy = bool(settings.proxy_url) and not settings.proxy_url.startswith("http")
    can_window = (
        not is_hls
        and duration_hint is not None
        and duration_hint > 0
        and not socks_proxy
        and settings.transcribe_extract_parallelism >= 1
    )
    windows = (
        plan_windows(
            duration_hint,  # type: ignore[arg-type]  (guarded above)
            codec,
            settings.transcribe_max_upload_bytes,
            settings.transcribe_extract_parallelism,
        )
        if can_window
        else None
    )
    return AcquisitionPlan(codec=codec, url=real_url, headers=headers, windows=windows)


def create_work_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="ds-transcribe-"))


def cleanup_work_dir(work_dir: Path) -> None:
    shutil.rmtree(work_dir, ignore_errors=True)


def pick_audio_format(formats: list[VideoFormat]) -> VideoFormat:
    """Pick the format to pull audio from -- the video track itself is unused,
    so the goal is the SMALLEST download that still carries audio. The client
    sends its whole format list; we always re-pick here and ignore whatever it
    plays with, because the smallest audio source is rarely the playback pick.

    Ranking (best first). We only know ``ext``/``resolution``/``protocol``/
    ``video_only``/``tbr`` here (a heuristic, not an exact codec check):

    1. **Audio-bearing, audio-only best.** Primary key. A muxed (audio+video)
       stream makes ffmpeg download the whole *picture* just to drop it
       (``-vn``); a ``video_only`` stream has no audio to transcribe at all, so
       it's last and only used if nothing else exists.
    2. **Progressive over HLS.** Second key, ABOVE size on purpose: only a
       progressive (single-file, Range-capable) URL can run the fast windowed
       path -- parallel cap-sized slices that sidestep per-connection CDN
       throttling. HLS (``m3u8_native``) forces the slow single-pass download,
       so it sorts last within its tier even when it's the smaller stream. A
       slightly bigger progressive that downloads in parallel beats a small
       HLS that dribbles through one throttled connection.
    3. **Smallest first**, by bitrate -- the size proxy, since every format of
       one video shares its duration. Unknown bitrate sorts last so an
       unknown-size format never poses as "smallest"; resolution breaks ties
       and stands in when bitrate is missing.
    """
    candidates = [f for f in formats if f.url]
    if not candidates:
        raise AudioError("No downloadable format available for this video")

    def score(f: VideoFormat) -> tuple[int, int, float, int]:
        is_audio_only = f.resolution is None and not f.video_only
        tier = 0 if is_audio_only else (2 if f.video_only else 1)
        is_hls = 1 if f.protocol == "m3u8_native" else 0  # progressive (0) first
        bitrate = f.tbr if (f.tbr and f.tbr > 0) else float("inf")
        resolution = f.resolution or 0
        return (tier, is_hls, bitrate, resolution)

    chosen = sorted(candidates, key=score)[0]
    # Prove the smallest audio source really is what we pull to disk -- shows
    # up once per job so a "why did it download the big file?" suspicion is
    # answerable from the logs.
    kind = (
        "audio-only" if (chosen.resolution is None and not chosen.video_only)
        else "video-only" if chosen.video_only
        else "muxed"
    )
    logger.info(
        "audio source: format=%s %s tbr=%s res=%s proto=%s (smallest of %d)",
        chosen.format_id, kind, chosen.tbr, chosen.resolution, chosen.protocol,
        len(candidates),
    )
    return chosen


async def _run_ffmpeg(
    args: list[str],
    binary: str = "ffmpeg",
    *,
    timeout: float = _FFMPEG_EXTRACT_TIMEOUT,
    on_out_time: Callable[[float], None] | None = None,
) -> None:
    """Run ffmpeg to completion. With ``on_out_time``, ffmpeg's ``-progress``
    stream is parsed and the callback receives the output timestamp (seconds
    of media produced so far) roughly twice a second -- divide by the track's
    duration for a real percentage."""
    prefix = ["-y", "-hide_banner", "-loglevel", "error"]
    if on_out_time is not None:
        prefix += ["-nostats", "-progress", "pipe:1"]
    try:
        proc = await proc_util.spawn(
            [binary, *prefix, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        # The configured binary path stays in the server log -- clients get a
        # message with no server-filesystem detail.
        logger.error("ffmpeg binary %r is not runnable: %s", binary, exc)
        raise AudioError(
            "Audio processing is unavailable: ffmpeg is not installed on this "
            "server (or FFMPEG_PATH points at the wrong location)."
        ) from exc

    loop = asyncio.get_running_loop()

    def _pump_stdout() -> None:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            if on_out_time is None:
                continue
            text = raw_line.decode(errors="ignore").strip()
            # ffmpeg quirk: out_time_ms is ALSO microseconds (same as
            # out_time_us) -- both divide by 1e6. Value is "N/A" early on.
            if text.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    value = max(0, int(text.split("=", 1)[1])) / 1_000_000
                except ValueError:
                    continue
                loop.call_soon_threadsafe(on_out_time, value)

    def _pump_stderr() -> bytes:
        assert proc.stderr is not None
        return proc.stderr.read()

    async def _consume() -> bytes:
        # stdout/stderr are drained concurrently (each in its own thread) --
        # sequentially would risk a classic pipe deadlock if one fills while
        # only the other is being read.
        _, stderr = await asyncio.gather(
            asyncio.to_thread(_pump_stdout), asyncio.to_thread(_pump_stderr)
        )
        await asyncio.to_thread(proc.wait)
        return stderr

    try:
        stderr = await proc_util.guarded(_consume, proc=proc, timeout=timeout)
    except TimeoutError as exc:
        raise AudioError("Audio extraction timed out") from exc
    if proc.returncode != 0:
        # Raw stderr can quote source URLs, header values, and local paths --
        # keep it in the server log only and hand clients a generic message.
        logger.error(
            "ffmpeg exited %s: %s",
            proc.returncode,
            stderr.decode(errors="ignore")[-2000:].strip(),
        )
        raise AudioError("Audio conversion failed")


async def probe_duration(path: Path, binary: str = "ffprobe") -> float:
    try:
        proc = await proc_util.spawn(
            [
                binary,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        logger.error("ffprobe binary %r is not runnable: %s", binary, exc)
        raise AudioError(
            "Audio processing is unavailable: ffprobe is not installed on this "
            "server (or FFPROBE_PATH points at the wrong location)."
        ) from exc
    try:
        stdout, stderr = await proc_util.guarded(
            lambda: proc_util.communicate(proc), proc=proc, timeout=_FFPROBE_TIMEOUT
        )
    except TimeoutError as exc:
        raise AudioError("ffprobe timed out") from exc
    if proc.returncode != 0:
        # Same rule as ffmpeg above: stderr detail is server-log only.
        logger.error(
            "ffprobe exited %s: %s",
            proc.returncode,
            stderr.decode(errors="ignore")[-500:].strip(),
        )
        raise AudioError("Could not read the audio file's metadata")
    try:
        return float(stdout.decode().strip())
    except ValueError as exc:
        raise AudioError("Could not determine audio duration") from exc


async def probe_duration_url(
    url: str,
    headers: dict[str, str] | None,
    settings: Settings,
    *,
    hls: bool = False,
) -> float | None:
    """Best-effort probe of a REMOTE source's duration: ffprobe reads the URL's
    container metadata directly (a few KB, never the media bytes) using the
    same proxy/headers/rw-timeout ffmpeg would. Returns the duration in seconds,
    or ``None`` on any failure -- a missing duration just means the caller falls
    back to the single-pass path, so a failed probe must never fail the job.

    This is what lets the fast windowed path run when the client didn't send a
    ``durationSeconds`` (metadata not yet loaded, or a live/adaptive source):
    without a duration there's nothing to slice windows out of.
    """
    args = [
        "-v", "error",
        *_url_input_args(url, headers, settings, hls=hls),
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        url,
    ]
    try:
        proc = await proc_util.spawn(
            [settings.ffprobe_path, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        logger.warning("ffprobe not runnable for URL duration probe: %s", exc)
        return None
    try:
        stdout, _ = await proc_util.guarded(
            lambda: proc_util.communicate(proc), proc=proc, timeout=_FFPROBE_TIMEOUT
        )
    except TimeoutError:
        logger.warning("ffprobe URL duration probe timed out -- planning without a duration")
        return None
    if proc.returncode != 0:
        return None
    try:
        duration = float(stdout.decode().strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


async def _download_stream(
    url: str,
    headers: dict[str, str],
    ext: str,
    settings: Settings,
    work_dir: Path,
    on_progress: ProgressFn | None = None,
) -> Path:
    """Stream a progressive media URL to disk (with browser impersonation),
    capped at ``media_max_source_bytes`` (MEDIA_MAX_SOURCE_BYTES). Reports
    bytes/Content-Length as fractional progress when the server discloses a
    length."""
    max_bytes = settings.media_max_source_bytes
    dest = work_dir / f"source.{ext or 'bin'}"

    # Shared, long-lived session (see _get_download_session) -- NOT an
    # `async with`, which would tear down the connection pool after one job.
    session = _get_download_session(settings)
    kwargs: dict = {"headers": headers, "stream": True, "allow_redirects": False}
    kwargs.update(impersonate_kwarg(settings))

    # Redirects are followed by hand so EVERY hop re-passes the public-URL
    # gate -- an origin must not be able to bounce this server-side download
    # into localhost or a private address.
    try:
        current = url
        for _ in range(_MAX_DOWNLOAD_REDIRECTS):
            resp = await session.get(current, **kwargs)
            if resp.status_code not in (301, 302, 303, 307, 308):
                break
            location = resp.headers.get("location")
            await resp.aclose()
            if not location:
                raise AudioError("Source media redirect had no destination")
            current = urljoin(current, location)
            try:
                await assert_public_resolved_url(current)
            except ValueError as exc:
                raise AudioError(str(exc)) from exc
        else:
            raise AudioError("Source media redirected too many times")
    except NotImplementedError as exc:
        # curl_cffi raises a bare (often message-less) NotImplementedError
        # when the configured IMPERSONATE_CLIENT needs a TLS feature the
        # installed curl-impersonate build doesn't support on this
        # platform. Distinct from a normal network failure, so it gets
        # its own actionable message instead of falling into the generic
        # "Failed to reach source media: " branch below (which would be
        # left with nothing after the colon).
        raise AudioError(
            "Browser impersonation isn't supported for the configured "
            "IMPERSONATE_CLIENT on this server. Try a different "
            "IMPERSONATE_CLIENT, or disable ENABLE_IMPERSONATION."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - surface as a clean AudioError
        raise AudioError(f"Failed to reach source media: {exc}") from exc

    if resp.status_code >= 400:
        await resp.aclose()
        raise AudioError(f"Failed to download source media: HTTP {resp.status_code}")

    try:
        total = int(resp.headers.get("content-length", "0")) or None
    except ValueError:
        total = None

    written = 0
    try:
        with dest.open("wb") as fh:
            async for chunk in resp.aiter_content():
                written += len(chunk)
                if written > max_bytes:
                    raise AudioError(
                        "Source media exceeds the server's transcription download size limit"
                    )
                await asyncio.to_thread(fh.write, chunk)
                if on_progress is not None and total:
                    on_progress(min(written / total, 1.0))
    except AudioError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface as a clean AudioError
        raise AudioError(f"Failed while downloading source media: {exc}") from exc
    finally:
        await resp.aclose()

    return dest


def _out_time_progress(duration_hint: float | None, on_progress: ProgressFn | None):
    """Adapt an absolute out_time (seconds transcoded) to a 0..1 fraction --
    only possible when the track's duration is known."""
    if on_progress is None or not duration_hint or duration_hint <= 0:
        return None

    def _cb(out_time: float) -> None:
        on_progress(min(out_time / duration_hint, 1.0))

    return _cb


async def extract_audio_track(
    source: Path,
    work_dir: Path,
    settings: Settings,
    codec: _Codec,
    *,
    duration_hint: float | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    out = work_dir / f"audio.{codec.ext}"
    if duration_hint is None and on_progress is not None:
        try:
            duration_hint = await probe_duration(source, settings.ffprobe_path)
        except AudioError:
            duration_hint = None  # progress stays indeterminate; extraction still runs
    await _run_ffmpeg(
        ["-i", str(source), *codec.args, str(out)],
        settings.ffmpeg_path,
        on_out_time=_out_time_progress(duration_hint, on_progress),
    )
    return out


def _ffmpeg_proxy_args(settings: Settings) -> list[str]:
    # ffmpeg's http protocol only speaks http(s) proxies -- socks stays on the
    # curl_cffi fallback path.
    if settings.proxy_url and settings.proxy_url.startswith("http"):
        return ["-http_proxy", settings.proxy_url]
    return []


_ALLOWED_FFMPEG_HEADER_NAMES = frozenset({"referer", "user-agent", "cookie", "range"})


def _safe_header_value(value: str) -> str:
    """Strip CR/LF/NUL so client-controlled values cannot smuggle extra headers."""
    return value.replace("\r", "").replace("\n", "").replace("\0", "")[:4096]


def _url_input_args(
    url: str, headers: dict[str, str] | None, settings: Settings, *, hls: bool
) -> list[str]:
    """The common ffmpeg input args for reading a source URL directly: proxy,
    the source's own request headers, HLS extension allow-list, and the
    per-read network timeout."""
    args: list[str] = [*_ffmpeg_proxy_args(settings)]
    if headers:
        safe_pairs = [
            (k, _safe_header_value(v))
            for k, v in headers.items()
            if k.lower() in _ALLOWED_FFMPEG_HEADER_NAMES and v
        ]
        if safe_pairs:
            header_lines = "".join(f"{k}: {v}\r\n" for k, v in safe_pairs)
            args += ["-headers", header_lines]
    if hls:
        args += ["-allowed_extensions", "ALL"]
    args += ["-rw_timeout", _FFMPEG_RW_TIMEOUT]
    return args


async def _extract_audio_from_url(
    url: str,
    headers: dict[str, str] | None,
    work_dir: Path,
    settings: Settings,
    codec: _Codec,
    *,
    hls: bool,
    duration_hint: float | None = None,
    on_progress: ProgressFn | None = None,
) -> Path:
    """ffmpeg reads the source URL directly -- download and transcode become
    one overlapped pass and the source file never hits the disk.

    Fetches the origin with the source's own headers (Referer/UA/Cookie).
    For HLS, ``-allowed_extensions ALL`` covers fragmented-MP4 (.m4s) segments
    that aren't in ffmpeg's default allow-list. ``-rw_timeout`` bounds each
    network read so a dead host can't wedge the job.
    """
    out = work_dir / f"audio.{codec.ext}"
    args = _url_input_args(url, headers, settings, hls=hls)
    args += ["-i", url, *codec.args, str(out)]
    await _run_ffmpeg(
        args,
        settings.ffmpeg_path,
        on_out_time=_out_time_progress(duration_hint, on_progress),
    )
    return out


async def extract_window(
    url: str,
    headers: dict[str, str] | None,
    work_dir: Path,
    settings: Settings,
    codec: _Codec,
    window: Window,
    *,
    on_progress: ProgressFn | None = None,
) -> AudioChunk:
    """Extract one planned ``Window`` straight off the source URL into its own
    chunk file. ``-ss``/``-t`` sit *before* ``-i`` so ffmpeg issues an HTTP
    Range request and starts reading near the window instead of from byte 0
    (on range-capable progressive origins -- the common case). Re-encoding
    makes the seek sample-accurate, so the chunk's offset is exactly
    ``window.start`` with no probing needed."""
    out = work_dir / f"chunk_{window.index:03d}.{codec.ext}"
    args = _url_input_args(url, headers, settings, hls=False)
    args += [
        "-ss", f"{window.start:.3f}",
        "-t", f"{window.length:.3f}",
        "-i", url,
        *codec.args,
        str(out),
    ]
    await _run_ffmpeg(
        args,
        settings.ffmpeg_path,
        on_out_time=_out_time_progress(window.length, on_progress),
    )
    return AudioChunk(path=out, offset_seconds=window.start)


async def acquire_audio(
    formats: list[VideoFormat],
    settings: Settings,
    work_dir: Path,
    *,
    duration_hint: float | None = None,
    on_progress: ProgressFn | None = None,
    resolve_cookie_token: Callable[[str], str] | None = None,
) -> Path:
    """Resolve the audio track for the transcription job into ONE file (the
    single-pass fallback used for HLS / unknown-duration sources), reporting
    0..1 progress across the whole acquire step.

    The client sends proxied (``/proxy-video?...``) URLs (that's what the
    player uses). For server-side acquisition we unwrap them and hit the origin
    directly with the source's own headers -- see ``_unwrap_proxied``.

    Fast path for every protocol is a single ffmpeg pass straight off the URL.
    A progressive host that rejects ffmpeg's TLS (anti-bot CDNs that need
    browser impersonation) falls back to curl_cffi download + local transcode.
    """
    codec = choose_codec(
        settings,
        duration_hint=duration_hint,
        cap_bytes=settings.transcribe_max_upload_bytes,
    )
    fmt = pick_audio_format(formats)
    real_url, extra_headers = _unwrap_proxied(
        fmt.url or "", resolve_cookie_token=resolve_cookie_token
    )
    # Resolve-and-check (not just the string gate): a transcribe request could
    # name a public-looking host that resolves to a private address. Residual
    # gap: ffmpeg fetches the URL itself and follows origin redirects with no
    # DNS re-check; only the curl_cffi fallback path re-gates every hop.
    try:
        await assert_public_resolved_url(real_url)
    except ValueError as exc:
        raise AudioError(str(exc)) from exc
    headers = {**(fmt.http_headers or {}), **extra_headers}

    if fmt.protocol == "m3u8_native":
        return await _extract_audio_from_url(
            real_url, headers, work_dir, settings, codec,
            hls=True, duration_hint=duration_hint, on_progress=on_progress,
        )

    # A socks proxy forces the curl_cffi path -- ffmpeg can't speak it.
    if not (settings.proxy_url and not settings.proxy_url.startswith("http")):
        try:
            return await _extract_audio_from_url(
                real_url, headers, work_dir, settings, codec,
                hls=False, duration_hint=duration_hint, on_progress=on_progress,
            )
        except AudioError as exc:
            logger.warning(
                "direct ffmpeg read failed (%s) -- falling back to impersonated download",
                str(exc)[:300],
            )

    # Fallback: impersonated download (first ~55%% of the step), then local
    # transcode (the rest). The weights are honest-ish, not measured -- both
    # sub-steps scale with the same source length.
    def _dl_progress(frac: float) -> None:
        if on_progress is not None:
            on_progress(frac * 0.55)

    def _tc_progress(frac: float) -> None:
        if on_progress is not None:
            on_progress(0.55 + frac * 0.45)

    downloaded = await _download_stream(
        real_url, headers, fmt.ext, settings, work_dir, on_progress=_dl_progress
    )
    audio = await extract_audio_track(
        downloaded, work_dir, settings, codec,
        duration_hint=duration_hint, on_progress=_tc_progress,
    )
    # The source file is by far the largest thing in the work dir -- drop it
    # as soon as the opus track exists instead of holding disk until cleanup.
    downloaded.unlink(missing_ok=True)
    return audio


async def chunk_audio(
    audio_path: Path, work_dir: Path, settings: Settings, *, duration: float
) -> list[AudioChunk]:
    """Split into ``CHUNK_SECONDS`` pieces with ONE ffmpeg segmenting pass
    (``-c copy``, no re-encode) -- not one invocation per chunk. Offsets are
    then measured from the produced files (cumulative real durations), so
    merged subtitle timing is exact regardless of where the muxer could
    actually cut. Used only on the single-pass fallback path."""
    if duration <= CHUNK_SECONDS * _CHUNK_SLACK:
        return [AudioChunk(path=audio_path, offset_seconds=0.0)]

    ext = audio_path.suffix.lstrip(".") or "opus"
    pattern = work_dir / f"chunk_%03d.{ext}"
    await _run_ffmpeg(
        [
            "-i",
            str(audio_path),
            "-f",
            "segment",
            "-segment_time",
            str(CHUNK_SECONDS),
            "-reset_timestamps",
            "1",
            "-c",
            "copy",
            str(pattern),
        ],
        settings.ffmpeg_path,
        timeout=_FFMPEG_SEGMENT_TIMEOUT,
    )

    paths = sorted(work_dir.glob(f"chunk_*.{ext}"))
    if not paths:
        raise AudioError("Audio chunking produced no output")

    # Sequential probes on purpose: local metadata reads are ~50ms each, and
    # fanning out N ffprobe processes at once is needless load on a small VPS.
    chunks: list[AudioChunk] = []
    offset = 0.0
    for path in paths:
        chunks.append(AudioChunk(path=path, offset_seconds=offset))
        offset += await probe_duration(path, settings.ffprobe_path)

    logger.info("split %.0fs audio into %d chunk(s)", duration, len(chunks))
    return chunks
