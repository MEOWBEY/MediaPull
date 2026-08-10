"""MediaPull API — application factory and routes."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import logging
import os
import shutil
import sys
import tempfile
import urllib.parse
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
import httpx


from . import __version__, admin
from .audio import AudioError, close_download_session, pick_audio_format
from .cache import TTLCache
from .config import settings
from .extractor import ExtractionError, Extractor
from .gallery import GalleryExtractor
from .split_audio import SplitAudioStore, run_split_audio_job
from .jobs import JobStore, TranscriptionJob, run_transcription_job
from .logging_context import LogContextMiddleware, RequestContextFilter, current_client_ip
from .net_common import normalize_cookies
from .models import (
    CookieUploadRequest,
    CookieUploadResponse,
    ExtractRequest,
    ExtractResponse,
    GalleryInfo,
    GalleryResponse,
    HealthResponse,
    ProxyTokenRequest,
    ProxyTokenResponse,
    SplitAudioStartResponse,
    SplitAudioStatus,
    SplitAudioUrlRequest,
    TranscribeRequest,
    TranscribeResult,
    TranscribeStartResponse,
    TranscribeStatus,
    VideoInfo,
)
from .proxy import ProxyService
from .serializers import to_client_gallery, to_client_video
from .transcribe.groq_engine import GroqTranscriber


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s [ip=%(client_ip)s req=%(request_id)s] - %(message)s"
        )
    )
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root.handlers = [handler]
    # httpx logs an INFO line per request; the Groq transcription path fires one
    # per audio chunk, so a single subtitle job spams several "HTTP Request: ...
    # 200 OK" lines that bury the app's own progress. Lift it to WARNING.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # The admin panel's in-memory ring buffer (also catches uvicorn/gunicorn
    # access lines -- see admin.attach_log_buffer).
    admin.attach_log_buffer()


logger = logging.getLogger("mediapull")


def _cookie_tag(cookies: str | None) -> str:
    """``no`` / ``yes(N)`` for logs — N counts non-comment, non-blank cookie
    lines so an empty or comment-only cookie blob reads as ``yes(0)`` instead of
    a misleading bare ``yes``."""
    if not cookies:
        return "no"
    count = sum(
        1
        for line in cookies.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    return f"yes({count})"


def _resolve_client_dir() -> Path | None:
    """Built static client to serve, or None if it isn't there yet.

    Uses ``CLIENT_DIR`` when set, else repo-root/client/build relative to this
    file (``server/app/main.py`` -> parents[2] is the repo root).
    """
    raw = settings.client_dir.strip()
    candidate = (
        Path(raw).expanduser().resolve()
        if raw
        else Path(__file__).resolve().parents[2] / "client" / "build"
    )
    return candidate if (candidate / "index.html").is_file() else None


def _check_binary(name: str, configured: str) -> bool:
    """shutil.which resolves both a bare PATH-only name and an absolute path
    the operator pointed FFMPEG_PATH/FFPROBE_PATH/GALLERY_DL_PATH at."""
    available = shutil.which(configured) is not None
    if not available:
        logger.warning(
            "%s (%r) was not found on PATH -- related features will fail until it's "
            "installed or the binary setting points at its real location",
            name,
            configured,
        )
    return available


async def _check_pot_provider(base_url: str) -> bool:
    """Ping the bgutil PO-token sidecar so /health and boot logs show whether
    YouTube bot-detection bypass is actually available -- age-restricted /
    datacenter-IP extraction leans on it. Advisory only (like ffmpeg): a down
    provider must not block startup. The sidecar answers GET /ping."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/ping")
        ok = resp.status_code < 500
    except Exception as exc:  # noqa: BLE001 - any transport error = unreachable
        logger.warning(
            "PO-token provider at %s is unreachable (%s) -- YouTube age-gated / "
            "bot-checked extraction may fail. Is mediapull-pot running?",
            base_url,
            exc,
        )
        return False
    if ok:
        logger.info("PO-token provider at %s: reachable", base_url)
    else:
        logger.warning("PO-token provider at %s returned %s", base_url, resp.status_code)
    return ok


async def _save_upload(
    file: UploadFile,
    max_bytes: int,
    prefix: str,
    what: str,
) -> tuple[Path, int]:
    """Stream an UploadFile into a temp file, capped at ``max_bytes``.

    Returns the temp path (owned by the caller -- it is deleted in the
    caller's cleanup) and the number of bytes written. A file over the cap
    returns a 413 before any more bytes are written; any I/O failure logs
    under ``what`` and reports a 500. Both paths unlink the temp file."""
    suffix = Path(file.filename or "upload").suffix or ".bin"
    tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=suffix, prefix=prefix)
    tmp_path = Path(tmp_path_str)
    try:
        written = 0
        with os.fdopen(tmp_fd, "wb") as fh:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"File exceeds the server's "
                            f"{max_bytes // 1_000_000}MB {what} limit"
                        ),
                    )
                fh.write(chunk)
    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        logger.error("%s upload failed: %s", what, exc)
        raise HTTPException(status_code=500, detail="Upload failed") from exc
    return tmp_path, written


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    app.state.extractor = Extractor(settings)
    app.state.gallery_extractor = GalleryExtractor(settings)
    app.state.proxy = ProxyService(settings)
    app.state.cache = TTLCache[VideoInfo](
        ttl=settings.cache_ttl, max_entries=settings.cache_max_entries
    )
    app.state.gallery_cache = TTLCache[GalleryInfo](
        ttl=settings.cache_ttl, max_entries=settings.cache_max_entries
    )
    app.state.jobs = JobStore(settings)
    app.state.split_audio = SplitAudioStore(settings)
    # Extractions whose HTTP client disconnected before they finished. The
    # request has to return immediately, but the yt-dlp thread-pool run can't
    # be cancelled mid-flight — so it keeps going detached and feeds the TTL
    # cache (a re-extract of the same URL then cache-hits). This set holds a
    # reference so the pending task isn't garbage-collected (and therefore
    # cancelled) between the client's disconnect and the run's natural end.
    app.state.detached_extracts: set[asyncio.Task] = set()
    # None when unconfigured -- /transcribe responds 503 rather than the
    # whole app failing to start over a missing optional feature's key.
    app.state.transcriber = GroqTranscriber(settings) if settings.groq_api_keys else None
    # Advisory only (not fatal): normal video extraction never touches ffmpeg,
    # so a missing install must not block startup. We still probe at boot so
    # GET /health and logs show ffmpegAvailable=false before anyone hits
    # /transcribe (where it would fail mid-job). Always checked — even when
    # GROQ_API_KEY is empty — so deploy tooling can catch a broken PATH early.
    app.state.ffmpeg_available = _check_binary("ffmpeg", settings.ffmpeg_path)
    app.state.ffprobe_available = _check_binary("ffprobe", settings.ffprobe_path)
    if settings.gallery_dl_path == "gallery-dl":
        # The default invokes `sys.executable -m gallery_dl` (see
        # GalleryExtractor._base_cmd), not a bare PATH lookup, so its
        # availability is really "is the gallery_dl module importable".
        app.state.gallery_dl_available = importlib.util.find_spec("gallery_dl") is not None
        if not app.state.gallery_dl_available:
            logger.warning("gallery_dl Python package is not installed -- /extract-gallery will fail")
    else:
        app.state.gallery_dl_available = _check_binary("gallery-dl", settings.gallery_dl_path)
    # Advisory PO-token provider probe -- see _check_pot_provider. Surfaced in
    # /health so you can tell at a glance whether YouTube bot-detection bypass
    # is live, instead of inferring it from the sidecar's own log.
    app.state.pot_available = await _check_pot_provider(settings.pot_probe_url)
    logger.info("MediaPull API %s ready", __version__)
    try:
        yield
    finally:
        await app.state.extractor.aclose()
        await app.state.gallery_extractor.aclose()
        await app.state.proxy.aclose()
        if app.state.transcriber is not None:
            await app.state.transcriber.aclose()
        # Close the shared audio-download session (lazily created on the
        # impersonated-download fallback path; no-op if never used).
        await close_download_session()
        logger.info("MediaPull API shut down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="MediaPull API",
        description=(
            "Paste a URL to extract downloadable video formats and image galleries. "
            "Optional proxy streaming and speech-to-text subtitles."
        ),
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )

    origins = settings.cors_origins
    wildcard = "*" in origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Browsers reject `Access-Control-Allow-Origin: *` together with
        # credentials (the response is dropped), so credentialed cross-origin
        # requests fail silently under the wildcard default. Only enable
        # credentials when the operator pinned an explicit origin list.
        allow_credentials=not wildcard and len(origins) > 0,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    # Pure-ASGI (see LogContextMiddleware): a BaseHTTPMiddleware here would
    # swallow client disconnects and leave the media proxy streaming from the
    # origin after the browser cancelled -- burning bandwidth for nobody.
    app.add_middleware(LogContextMiddleware)
    # Innermost: 403s banned IPs before any endpoint runs.
    app.add_middleware(admin.AdminGuardMiddleware)

    app.include_router(admin.router)

    # Caps concurrent extract work so a burst cannot queue unbounded thread-pool
    # jobs (and hold ASGI connections open) on a public VPS.
    extract_slots = asyncio.Semaphore(settings.extract_max_in_flight)

    async def _poll_disconnected(request: Request) -> None:
        """Return once the client's connection has gone away. Starlette's
        ``is_disconnected`` is a one-shot-per-message check, so poll it while
        the extract runs; the first disconnect trips this coroutine."""
        while not await request.is_disconnected():
            await asyncio.sleep(0.1)

    _T = TypeVar("_T")

    async def _extract_until_done_or_disconnect(
        run: Callable[[], Awaitable[_T]],
        cache: TTLCache[_T],
        cache_key: str,
        request: Request,
        endpoint: str,
    ) -> _T:
        """Run one extraction, racing it against the client's connection.

        A disconnect must free the request AND its admission slot as soon as
        it's noticed, not after yt-dlp finishes (the thread-pool run can't be
        cancelled, so it used to hold the connection open for the whole
        REQUEST_TIMEOUT). On disconnect the run is therefore let go detached:
        it keeps its slot until it genuinely ends, and its result still lands
        in the TTL cache — a re-extract of the same URL cache-hits instead of
        burning a second yt-dlp run nobody asked for."""
        task = asyncio.create_task(run())
        disconnect_task = asyncio.create_task(_poll_disconnected(request))
        try:
            done, _ = await asyncio.wait(
                {task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            if disconnect_task in done:
                disconnect_task.cancel()
                await asyncio.gather(disconnect_task, return_exceptions=True)

        if task in done:
            video = task.result()
            await cache.set(cache_key, video)
            return video

        logger.info(
            "%s: client disconnected during extraction, continuing in the "
            "background (result will be cached): %s",
            endpoint,
            cache_key.partition("#")[0],
        )
        # Keep the pending task alive (see lifespan's detached_extracts) and
        # unlink it once it settles so it doesn't linger in the set forever.
        app.state.detached_extracts.add(task)
        task.add_done_callback(app.state.detached_extracts.discard)
        raise HTTPException(status_code=499, detail="Client disconnected")

    @app.exception_handler(ExtractionError)
    async def _extraction_error(_: Request, exc: ExtractionError) -> JSONResponse:
        logger.warning("extraction failed (%s): %s", exc.status, exc)
        return JSONResponse(
            status_code=exc.status, content={"success": False, "error": str(exc)}
        )

    @app.post("/extract-videos", response_model=ExtractResponse)
    async def extract_videos(
        request: Request,
        payload: ExtractRequest,
        _: None = Depends(admin.payload_rate_guard),
    ) -> ExtractResponse:
        url = payload.url.strip()
        blocked = admin.check_url_allowed(url)
        if blocked:
            raise HTTPException(status_code=403, detail=blocked)
        cookies = payload.cookies
        cache: TTLCache[VideoInfo] = app.state.cache

        # Cookies change what's extractable (private/age/login-gated), so an
        # authenticated request must not be served a public-failed cache entry
        # (or vice-versa). Bucket the cache by a short, non-reversible cookie tag.
        cache_key = url
        if cookies:
            digest = hashlib.sha256(cookies.encode("utf-8", "ignore")).hexdigest()[:16]
            cache_key = f"{url}#c={digest}"

        cached = await cache.get(cache_key)
        if cached is not None:
            logger.info("cache hit: %s", url)
            return ExtractResponse(
                video=to_client_video(cached), method=cached.method, cached=True
            )

        logger.info("extracting: %s (cookies=%s)", url, _cookie_tag(cookies))

        async def _run_extract() -> VideoInfo:
            try:
                await asyncio.wait_for(extract_slots.acquire(), timeout=0.05)
            except TimeoutError as exc:
                raise HTTPException(status_code=503, detail="Server busy, try again") from exc
            try:
                try:
                    return await app.state.extractor.extract(url, cookies=cookies)
                except ValueError as exc:
                    logger.warning("invalid extract-videos request for %s: %s", url, exc)
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
            finally:
                extract_slots.release()

        video = await _extract_until_done_or_disconnect(
            _run_extract, cache, cache_key, request, "extract-videos"
        )
        return ExtractResponse(
            video=to_client_video(video), method=video.method, cached=False
        )

    @app.post("/extract-gallery", response_model=GalleryResponse)
    async def extract_gallery(
        request: Request,
        payload: ExtractRequest,
        _: None = Depends(admin.payload_rate_guard),
    ) -> GalleryResponse:
        url = payload.url.strip()
        blocked = admin.check_url_allowed(url)
        if blocked:
            raise HTTPException(status_code=403, detail=blocked)
        cookies = payload.cookies
        cache: TTLCache[GalleryInfo] = app.state.gallery_cache

        # Same cookie-bucket rule as /extract-videos: login-gated galleries
        # (Instagram/X) differ by session, so authed and anon results must not
        # share a cache key.
        cache_key = url
        if cookies:
            digest = hashlib.sha256(cookies.encode("utf-8", "ignore")).hexdigest()[:16]
            cache_key = f"{url}#c={digest}"

        cached = await cache.get(cache_key)
        if cached is not None:
            logger.info("gallery cache hit: %s", url)
            return GalleryResponse(
                gallery=to_client_gallery(cached), method=cached.method, cached=True
            )

        logger.info("extracting gallery: %s (cookies=%s)", url, _cookie_tag(cookies))

        async def _run_gallery_extract() -> GalleryInfo:
            try:
                await asyncio.wait_for(extract_slots.acquire(), timeout=0.05)
            except TimeoutError as exc:
                raise HTTPException(status_code=503, detail="Server busy, try again") from exc
            try:
                try:
                    return await app.state.gallery_extractor.extract(url, cookies=cookies)
                except ValueError as exc:
                    logger.warning("invalid extract-gallery request for %s: %s", url, exc)
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
            finally:
                extract_slots.release()

        gallery = await _extract_until_done_or_disconnect(
            _run_gallery_extract, app.state.gallery_cache, cache_key, request, "extract-gallery"
        )
        return GalleryResponse(
            gallery=to_client_gallery(gallery), method=gallery.method, cached=False
        )

    @app.get("/proxy-video")
    async def proxy_video(request: Request) -> Response:
        return await app.state.proxy.handle(request)

    @app.post("/proxy-token", response_model=ProxyTokenResponse)
    async def proxy_token(
        payload: ProxyTokenRequest,
        _: None = Depends(admin.payload_rate_guard),
    ) -> ProxyTokenResponse:
        # Exchange a source's auth cookies for a short-lived opaque token so the
        # cookies stay out of the (copyable / shareable) proxy URL.
        return ProxyTokenResponse(
            token=app.state.proxy.create_cookie_token(payload.cookies)
        )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        ffmpeg_ok = app.state.ffmpeg_available and app.state.ffprobe_available
        return HealthResponse(
            version=__version__,
            timestamp=datetime.now(timezone.utc).isoformat(),
            ffmpeg_available=ffmpeg_ok,
            gallery_dl_available=app.state.gallery_dl_available,
            pot_available=app.state.pot_available,
            transcribe_enabled=app.state.transcriber is not None and settings.transcribe_enabled,
            media_max_bytes=settings.media_max_source_bytes,
            local_files_enabled=settings.local_files_enabled,
            split_audio_enabled=ffmpeg_ok and settings.split_audio_enabled,
        )

    @app.post("/admin/cookies", response_model=CookieUploadResponse)
    async def admin_cookies(payload: CookieUploadRequest, request: Request) -> CookieUploadResponse:
        # Replace the server-side default cookie file without a redeploy:
        # extraction opens the file fresh every request (see Extractor._ytdlp_sync),
        # so the new cookies take effect on the next call. Use it when the saved
        # cookies stop working -- re-export from a logged-in browser and POST them.
        #
        # Gated by an admin session cookie OR the legacy ADMIN_TOKEN bearer
        # (the pre-panel curl workflow). Unset = feature off: 404 (not 401) so
        # an unconfigured deploy doesn't advertise the endpoint exists.
        expected = settings.admin_token
        if not expected and not admin.admin_authorized(request):
            raise HTTPException(status_code=404, detail="Not Found")
        if not admin.admin_authorized(request):
            raise HTTPException(status_code=401, detail="Invalid or missing admin token")

        # A shared default cookie file is multi-domain, so the Netscape export is
        # the only sensible shape -- a bare "a=b; c=d" header has no host and
        # would need a URL we don't have here. normalize_cookies returns None for
        # unusable input; the url arg only matters for the header path we reject.
        normalized = normalize_cookies(payload.cookies, "")
        if not normalized:
            raise HTTPException(
                status_code=422,
                detail="Cookies must be a Netscape/Mozilla cookies.txt export (tab-separated rows)",
            )

        paths = settings.cookie_file_paths
        if not paths:
            raise HTTPException(
                status_code=409,
                detail="No COOKIE_FILE_PATHS configured -- set one before uploading cookies",
            )

        # Write the first path in the rotation. Atomic replace (temp + rename in
        # the same dir) so a concurrent extraction never reads a half-written
        # file. Cookie files are secrets -> 0600.
        target = Path(paths[0])
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        # Cookie files are secrets: the temp file must be 0600 from its very
        # first byte (a chmod after writing leaves a world-readable window on
        # shared hosts). O_EXCL on a freshly-unlinked name so a leftover temp
        # file can't carry looser permissions into this write. Modes are
        # best-effort on filesystems/OSes that don't honor POSIX bits.
        tmp.unlink(missing_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(normalized)
        tmp.replace(target)

        cookie_lines = sum(
            1 for ln in normalized.splitlines() if ln.strip() and not ln.startswith("#")
        )
        logger.info(
            "admin cookie upload: wrote %d cookie lines to %s", cookie_lines, target
        )
        return CookieUploadResponse(path=str(target), cookie_lines=cookie_lines)

    # ---- Audio split (strip the audio track from a media file) ----------
    # Two sources: a local upload and a URL the server downloads.
    # Both are gated by SPLIT_AUDIO_ENABLED + ffmpeg being available.
    # The split mp3 lives for SPLIT_AUDIO_TTL seconds, then is swept.

    def _split_audio_guard() -> None:
        if not app.state.ffmpeg_available or not app.state.ffprobe_available:
            raise HTTPException(status_code=503, detail="ffmpeg is not available on this server")
        if not settings.split_audio_enabled:
            raise HTTPException(status_code=503, detail="Split audio is disabled on this server")

    @app.post("/split-audio/local", response_model=SplitAudioStartResponse)
    async def split_audio_local(
        file: UploadFile = File(...),
        _: None = Depends(admin.payload_rate_guard),
    ) -> SplitAudioStartResponse:
        _split_audio_guard()
        original_stem = Path(file.filename or "audio").stem
        src_path, _ = await _save_upload(
            file, settings.media_max_source_bytes, "mediapull-split-src-", "split audio"
        )

        job = await app.state.split_audio.create()
        await app.state.split_audio.update(job.id, client_ip=current_client_ip())
        output_filename = f"{original_stem}.mp3"
        task = asyncio.create_task(
            run_split_audio_job(job.id, src_path, output_filename, app.state.split_audio, settings, delete_source=True)
        )
        app.state.split_audio.attach(job.id, task)
        return SplitAudioStartResponse(export_id=job.id)

    @app.post("/split-audio/url", response_model=SplitAudioStartResponse)
    async def split_audio_url(
        payload: SplitAudioUrlRequest,
        _: None = Depends(admin.payload_rate_guard),
    ) -> SplitAudioStartResponse:
        _split_audio_guard()

        # Same contract as /transcribe: the client sends its whole format list
        # (proxied URLs) and the SERVER picks the smallest sound-bearing source
        # -- the playback track is often the biggest file, and for "just the
        # audio out of it" any sound-bearing stream works.
        if payload.formats is not None:
            try:
                fmt = pick_audio_format(payload.formats)
            except AudioError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            raw_url = (fmt.url or "").strip()
            protocol = fmt.protocol
        else:
            # Bare-URL legacy call: treat it as one unknown-protocol format.
            raw_url = (payload.url or "").strip()
            protocol = None
        if not raw_url:
            raise HTTPException(status_code=422, detail="url is required")

        # Unwrap /proxy-video URLs to get the real source + headers, so ffmpeg
        # fetches the origin directly (with proper headers) instead of bouncing
        # back through our own proxy (which would fail the SSRF guard).
        from .audio import _unwrap_proxied
        real_url, headers = _unwrap_proxied(
            raw_url, resolve_cookie_token=app.state.proxy.resolve_cookie_token
        )

        from .ssrf import assert_public_resolved_url
        try:
            await assert_public_resolved_url(real_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        original_stem = Path(urllib.parse.urlparse(real_url).path).stem or "audio"

        job = await app.state.split_audio.create()
        output_filename = f"{original_stem}.mp3"
        # Pass the real URL — ffmpeg fetches HTTP sources natively with headers.
        await app.state.split_audio.update(job.id, client_ip=current_client_ip())
        task = asyncio.create_task(
            run_split_audio_job(
                job.id, real_url, output_filename, app.state.split_audio,
                settings, headers=headers, protocol=protocol, delete_source=False
            )
        )
        app.state.split_audio.attach(job.id, task)
        return SplitAudioStartResponse(export_id=job.id)

    @app.get("/split-audio/{export_id}/status", response_model=SplitAudioStatus)
    async def get_split_audio_status(export_id: str) -> SplitAudioStatus:
        job = await app.state.split_audio.get(export_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown or expired split audio job")
        return SplitAudioStatus(
            export_id=job.id,
            status=job.status,
            progress=job.progress,
            error=job.error,
            download_url=f"/split-audio/{job.id}/file" if job.status == "done" else None,
            filename=job.filename,
            step_label=job.step_label or ("Queued" if job.status == "queued" else None),
        )

    @app.post("/split-audio/{export_id}/cancel")
    async def cancel_split_audio(export_id: str) -> dict:
        job = await app.state.split_audio.get(export_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown or expired split audio job")
        cancelled = await app.state.split_audio.cancel(export_id)
        return {"cancelled": cancelled}

    @app.get("/split-audio/{export_id}/file", include_in_schema=False)
    async def download_split_audio(export_id: str) -> Response:
        job = await app.state.split_audio.get(export_id)
        if job is None or job.status != "done" or job.output_path is None:
            raise HTTPException(status_code=404, detail="Split audio not ready or expired")
        filename = job.filename or "audio.mp3"
        return FileResponse(
            path=job.output_path,
            media_type="audio/mpeg",
            filename=filename,
        )

    # ---- Auto-subtitles (speech-to-text via Groq Whisper) ---------------
    # Opt-in, explicit, minutes-long job -- the only place in the app that
    # downloads media bytes to disk. Progress is pushed over SSE
    # (/transcribe/{id}/events); GET below still exists as a plain one-shot
    # status check (and a fallback for any client that can't hold an SSE
    # connection open). Only viable single-worker (already required -- see
    # the comment in mediapull.service -- so there's no cross-worker
    # fan-out to worry about for the in-memory subscriber queues below).

    def _build_status(job: TranscriptionJob) -> TranscribeStatus:
        result = None
        if job.status == "done":
            result = TranscribeResult(
                language=job.language or "en",
                vtt_url=f"/transcribe/{job.id}/subtitle.vtt",
                srt_url=f"/transcribe/{job.id}/subtitle.srt",
                dialogue_map=job.dialogue_map,
            )

        return TranscribeStatus(
            job_id=job.id,
            status=job.status,
            progress=job.progress,
            step_label=job.step_label,
            detail=job.detail,
            chunks_done=job.chunks_done,
            chunks_total=job.chunks_total,
            error=job.error,
            result=result,
        )

    @app.post("/transcribe", response_model=TranscribeStartResponse)
    async def start_transcribe(
        payload: TranscribeRequest,
        _: None = Depends(admin.payload_rate_guard),
    ) -> TranscribeStartResponse:
        if app.state.transcriber is None:
            raise HTTPException(
                status_code=503, detail="Auto-subtitles are not configured on this server"
            )

        try:
            job = await app.state.jobs.create()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        await app.state.jobs.update(job.id, client_ip=current_client_ip())
        logger.info(
            "transcription job %s started for %s",
            job.id,
            payload.webpage_url or "<url not sent>",
        )
        task = asyncio.create_task(
            run_transcription_job(
                job.id,
                payload.formats,
                settings,
                app.state.jobs,
                app.state.transcriber,
                duration_hint=payload.duration_seconds,
                resolve_cookie_token=app.state.proxy.resolve_cookie_token,
            )
        )
        await app.state.jobs.set_task(job.id, task)
        return TranscribeStartResponse(job_id=job.id)

    @app.post("/transcribe/local", response_model=TranscribeStartResponse)
    async def start_transcribe_local(
        file: UploadFile = File(...),
        _: None = Depends(admin.payload_rate_guard),
    ) -> TranscribeStartResponse:
        # Gated by the same TRANSCRIBE_ENABLED flag as the URL-based endpoint.
        if app.state.transcriber is None:
            raise HTTPException(
                status_code=503, detail="Auto-subtitles are not configured on this server"
            )

        # Cap upload size to the same limit as the download path
        # (MEDIA_MAX_SOURCE_BYTES).
        tmp_path, written = await _save_upload(
            file, settings.media_max_source_bytes, "mediapull-local-", "transcription"
        )

        try:
            job = await app.state.jobs.create()
        except RuntimeError as exc:
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        await app.state.jobs.update(job.id, client_ip=current_client_ip())

        logger.info(
            "local transcription job %s started: %s bytes, file=%s",
            job.id, written, file.filename or "<unnamed>",
        )
        task = asyncio.create_task(
            run_transcription_job(
                job.id,
                formats=None,
                settings=settings,
                store=app.state.jobs,
                transcriber=app.state.transcriber,
                source_path=tmp_path,
            )
        )
        await app.state.jobs.set_task(job.id, task)
        return TranscribeStartResponse(job_id=job.id)

    @app.get("/transcribe/{job_id}", response_model=TranscribeStatus)
    async def get_transcribe_status(job_id: str) -> TranscribeStatus:
        job = await app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown or expired job")

        return _build_status(job)

    @app.get("/transcribe/{job_id}/events", include_in_schema=False)
    async def stream_transcribe_status(job_id: str, request: Request) -> StreamingResponse:
        job = await app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown or expired job")

        async def event_stream() -> AsyncGenerator[str, None]:
            queue = await app.state.jobs.subscribe(job_id)
            try:
                # Send the current state immediately -- otherwise a client
                # that subscribes right as the job finishes could wait
                # forever for a change that already happened.
                current = await app.state.jobs.get(job_id)
                if current is None:
                    return
                yield f"data: {_build_status(current).model_dump_json(by_alias=True)}\n\n"
                if current.is_terminal:
                    return

                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        updated = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        # SSE comment line -- keeps intermediate proxies from
                        # deciding an idle connection is dead and closing it.
                        yield ": keep-alive\n\n"
                        continue
                    yield f"data: {_build_status(updated).model_dump_json(by_alias=True)}\n\n"
                    if updated.is_terminal:
                        return
            finally:
                await app.state.jobs.unsubscribe(job_id, queue)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                # Tells nginx specifically not to buffer this response --
                # without it, a default nginx reverse proxy would hold the
                # whole stream until it closes instead of forwarding each
                # event as it arrives, defeating the point of SSE. Caddy
                # doesn't buffer streaming responses by default, so this is
                # a no-op (and harmless) there.
                "X-Accel-Buffering": "no",
            },
        )

    @app.delete("/transcribe/{job_id}", status_code=204, include_in_schema=False)
    async def cancel_transcribe(job_id: str) -> Response:
        # Best-effort: requests cancellation of the background task via
        # JobStore.cancel -- the task's own except-CancelledError clause
        # (jobs.py) does the actual status flip + cleanup, not this handler.
        ok = await app.state.jobs.cancel(job_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Unknown or expired job")
        return Response(status_code=204)

    @app.get("/transcribe/{job_id}/subtitle.vtt", include_in_schema=False)
    async def get_transcribe_vtt(job_id: str) -> Response:
        job = await app.state.jobs.get(job_id)
        if job is None or job.vtt_text is None:
            raise HTTPException(status_code=404, detail="Subtitle not ready")
        return Response(content=job.vtt_text, media_type="text/vtt")

    @app.get("/transcribe/{job_id}/subtitle.srt", include_in_schema=False)
    async def get_transcribe_srt(job_id: str) -> Response:
        job = await app.state.jobs.get(job_id)
        if job is None or job.srt_text is None:
            raise HTTPException(status_code=404, detail="Subtitle not ready")
        return Response(
            content=job.srt_text,
            media_type="application/x-subrip",
            headers={"Content-Disposition": 'attachment; filename="subtitles.srt"'},
        )

    # ---- Static SPA (single-process deploy) ----------------------------
    # If the client has been built, serve it from this same origin so the SPA
    # can talk to the API with relative URLs (one port, no CORS). The API
    # routes above are registered first, so they always win; anything else
    # falls back to index.html for client-side routing. Skipped entirely when
    # the build is absent (e.g. dev, where Vite serves the client).
    client_dir = _resolve_client_dir()
    if client_dir is not None:
        logger.info("serving static client from %s", client_dir)

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str) -> Response:
            target = (client_dir / full_path).resolve()
            if full_path and client_dir in target.parents and target.is_file():
                return FileResponse(target)
            return FileResponse(client_dir / "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        access_log=settings.debug,
        reload=settings.debug,
    )
