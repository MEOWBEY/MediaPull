"""Audio acquisition + ffmpeg extraction/chunking for the transcription pipeline.

This is the ONLY place in the app that writes media bytes to disk. It runs
exclusively inside an explicit, opt-in ``POST /transcribe`` job -- extraction
(``extractor.py``) always resolves URLs with ``download=False`` and that
invariant is untouched by this module.

Each step (no-download-needed / download / extract / chunk) only runs when
actually necessary:
  * an HLS source lets ffmpeg pull audio straight off the manifest URL, no
    manual segment reassembly;
  * a progressive source is downloaded once, then ffmpeg strips it to a
    mono/16kHz/low-bitrate track sized for Whisper;
  * chunking only kicks in when the extracted track exceeds
    ``transcribe_chunk_seconds`` (kept comfortably under Groq's per-request
    size limit at the default bitrate).
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from curl_cffi.requests import AsyncSession

from .config import Settings
from .models import VideoFormat

logger = logging.getLogger("directstream.audio")

_FFMPEG_AUDIO_ARGS = ("-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "32k")
# Bound every ffmpeg/ffprobe call so a stalled network read (e.g. a dead HLS
# segment) can't hang forever and pin a concurrency slot.
_FFMPEG_TIMEOUT = 300
# ffmpeg's own per-read network timeout (microseconds) -- 30s.
_FFMPEG_RW_TIMEOUT = "30000000"


def _unwrap_proxied(url: str) -> tuple[str, dict[str, str]]:
    """Recover the real source URL + headers from our own ``/proxy-video``
    wrapper, so server-side acquisition fetches the origin **directly** (with
    curl_cffi impersonation / ffmpeg ``-headers``) instead of bouncing back
    through the proxy.

    The proxy is for the browser, which can't set Referer/Cookie/User-Agent on
    a media element. ffmpeg and curl_cffi can, and going direct avoids a slow
    double-hop and the proxy's segment-extension rewriting that breaks ffmpeg's
    HLS demuxer. Non-proxied URLs pass through unchanged.
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
    if qs.get("cookies"):
        headers["Cookie"] = qs["cookies"][0]
    return real, headers


class AudioError(Exception):
    """Raised when audio acquisition/extraction/chunking fails."""


@dataclass
class AudioChunk:
    path: Path
    offset_seconds: float


def create_work_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="ds-transcribe-"))


def cleanup_work_dir(work_dir: Path) -> None:
    shutil.rmtree(work_dir, ignore_errors=True)


def pick_audio_format(formats: list[VideoFormat]) -> VideoFormat:
    """Pick the format to pull audio from -- the video track itself is unused.

    Ranking (best first), because we only know ``ext``/``resolution``/
    ``protocol``/``video_only`` here (a heuristic, not an exact codec check):

    1. **Progressive over HLS.** A progressive (single-file) URL is a plain
       download ffmpeg reads directly. An HLS URL goes through our proxy,
       which rewrites the playlist's segment URLs and drops their extensions
       -- ffmpeg then refuses them ("not in allowed_segment_extensions").
       So progressive is strongly preferred; HLS is a last resort (and
       ``_extract_audio_from_url`` passes ``-allowed_extensions ALL`` for it).
    2. **Audio-bearing over video-only.** A ``video_only`` stream has no audio
       to transcribe at all, so it's worst. Audio-only (no resolution, not
       video-only) is best; muxed (audio+video) is the middle.
    3. **Smaller bitrate first** -- less to download.
    """
    candidates = [f for f in formats if f.url]
    if not candidates:
        raise AudioError("No downloadable format available for this video")

    def score(f: VideoFormat) -> tuple[int, int, float]:
        is_hls = 1 if f.protocol == "m3u8_native" else 0
        is_audio_only = f.resolution is None and not f.video_only
        tier = 0 if is_audio_only else (2 if f.video_only else 1)
        return (is_hls, tier, f.tbr or 0.0)

    return sorted(candidates, key=score)[0]


async def _run_ffmpeg(args: list[str]) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise AudioError(f"ffmpeg is not installed or not on PATH: {exc}") from exc
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_FFMPEG_TIMEOUT)
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise AudioError("Audio extraction timed out") from exc
    if proc.returncode != 0:
        raise AudioError(f"ffmpeg failed: {stderr.decode(errors='ignore')[-2000:].strip()}")


async def probe_duration(path: Path) -> float:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise AudioError(f"ffprobe is not installed or not on PATH: {exc}") from exc
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise AudioError(f"ffprobe failed: {stderr.decode(errors='ignore')[-500:].strip()}")
    try:
        return float(stdout.decode().strip())
    except ValueError as exc:
        raise AudioError("Could not determine audio duration") from exc


async def _download_stream(
    url: str, headers: dict[str, str], ext: str, settings: Settings, work_dir: Path
) -> Path:
    """Stream a progressive media URL to disk (with browser impersonation),
    capped at ``transcribe_max_download_bytes``."""
    impersonate = settings.impersonate_client if settings.enable_impersonation else None
    proxy = settings.proxy_url or None
    max_bytes = settings.transcribe_max_download_bytes
    dest = work_dir / f"source.{ext or 'bin'}"

    async with AsyncSession(
        timeout=settings.request_timeout,
        proxies={"http": proxy, "https": proxy} if proxy else None,
    ) as session:
        kwargs: dict = {"headers": headers, "stream": True, "allow_redirects": True}
        if impersonate:
            kwargs["impersonate"] = impersonate

        try:
            resp = await session.get(url, **kwargs)
        except Exception as exc:  # noqa: BLE001 - surface as a clean AudioError
            raise AudioError(f"Failed to reach source media: {exc}") from exc

        if resp.status_code >= 400:
            await resp.aclose()
            raise AudioError(f"Failed to download source media: HTTP {resp.status_code}")

        written = 0
        try:
            with dest.open("wb") as fh:
                async for chunk in resp.aiter_content():
                    written += len(chunk)
                    if written > max_bytes:
                        raise AudioError(
                            "Source media exceeds the server's transcription download size limit"
                        )
                    fh.write(chunk)
        except AudioError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface as a clean AudioError
            raise AudioError(f"Failed while downloading source media: {exc}") from exc
        finally:
            await resp.aclose()

    return dest


async def extract_audio_track(source: Path, work_dir: Path) -> Path:
    out = work_dir / "audio.opus"
    await _run_ffmpeg(["-i", str(source), *_FFMPEG_AUDIO_ARGS, str(out)])
    return out


async def _extract_audio_from_url(url: str, headers: dict[str, str] | None, work_dir: Path) -> Path:
    """ffmpeg reads an HLS (or any ffmpeg-readable) URL directly -- no need to
    download and manually reassemble segments first.

    Fetches the origin directly with the source's own headers (Referer/UA/
    Cookie), so segment URLs keep their real extensions. ``-allowed_extensions
    ALL`` covers fragmented-MP4 (.m4s) segments that aren't in ffmpeg's default
    allow-list; ``-rw_timeout`` bounds each network read.
    """
    out = work_dir / "audio.opus"
    header_args: list[str] = []
    if headers:
        header_lines = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
        header_args = ["-headers", header_lines]
    await _run_ffmpeg(
        [
            *header_args,
            "-allowed_extensions",
            "ALL",
            "-rw_timeout",
            _FFMPEG_RW_TIMEOUT,
            "-i",
            url,
            *_FFMPEG_AUDIO_ARGS,
            str(out),
        ]
    )
    return out


async def acquire_audio(
    formats: list[VideoFormat], settings: Settings, work_dir: Path
) -> Path:
    """Resolve the audio track for the transcription job: one mono/16kHz/opus file.

    The client sends proxied (``/proxy-video?...``) URLs (that's what the
    player uses). For server-side acquisition we unwrap them and hit the origin
    directly with the source's own headers -- see ``_unwrap_proxied``.
    """
    fmt = pick_audio_format(formats)
    real_url, extra_headers = _unwrap_proxied(fmt.url or "")
    headers = {**(fmt.http_headers or {}), **extra_headers}

    if fmt.protocol == "m3u8_native":
        return await _extract_audio_from_url(real_url, headers, work_dir)

    downloaded = await _download_stream(real_url, headers, fmt.ext, settings, work_dir)
    return await extract_audio_track(downloaded, work_dir)


async def chunk_if_needed(audio_path: Path, work_dir: Path, settings: Settings) -> list[AudioChunk]:
    """Split into ``transcribe_chunk_seconds``-sized pieces only when needed.

    Re-cuts with ``-c copy`` (no re-encode) since the source is already the
    low-bitrate opus track ``acquire_audio`` produced.
    """
    duration = await probe_duration(audio_path)
    max_seconds = settings.transcribe_chunk_seconds
    if duration <= max_seconds:
        return [AudioChunk(path=audio_path, offset_seconds=0.0)]

    chunks: list[AudioChunk] = []
    offset = 0.0
    index = 0
    while offset < duration:
        chunk_path = work_dir / f"chunk_{index:03d}.opus"
        await _run_ffmpeg(
            ["-ss", str(offset), "-t", str(max_seconds), "-i", str(audio_path), "-c", "copy", str(chunk_path)]
        )
        chunks.append(AudioChunk(path=chunk_path, offset_seconds=offset))
        offset += max_seconds
        index += 1

    logger.info("split audio into %d chunk(s) (%.0fs each)", len(chunks), max_seconds)
    return chunks
