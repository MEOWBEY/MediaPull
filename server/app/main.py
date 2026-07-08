"""DirectStream API — application factory and routes."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import logging
import shutil
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from . import __version__
from .cache import TTLCache
from .config import settings
from .extractor import ExtractionError, Extractor
from .gallery import GalleryExtractor
from .jobs import JobStore, run_transcription_job
from .logging_context import (
    RequestContextFilter,
    client_ip_from_headers,
    set_request_context,
)
from .models import (
    ExtractRequest,
    ExtractResponse,
    GalleryInfo,
    GalleryResponse,
    HealthResponse,
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
            "%(asctime)s %(levelname)s %(name)s [ip=%(client_ip)s ua=%(user_agent)s] - %(message)s"
        )
    )
    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    root.handlers = [handler]


logger = logging.getLogger("directstream")


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
    the operator pointed FFMPEG_BINARY/FFPROBE_BINARY/GALLERY_DL_BINARY at."""
    available = shutil.which(configured) is not None
    if not available:
        logger.warning(
            "%s (%r) was not found on PATH -- related features will fail until it's "
            "installed or the binary setting points at its real location",
            name,
            configured,
        )
    return available


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
    # None when unconfigured -- /transcribe responds 503 rather than the
    # whole app failing to start over a missing optional feature's key.
    app.state.transcriber = GroqTranscriber(settings) if settings.groq_api_key else None
    # Advisory only (not fatal): normal extraction never touches ffmpeg, so a
    # broken install shouldn't block startup -- but it silently breaks
    # /transcribe otherwise, so surface it now instead of mid-job. Checked
    # even when transcription is unconfigured, since gallery-dl always matters.
    app.state.ffmpeg_available = _check_binary("ffmpeg", settings.ffmpeg_binary)
    app.state.ffprobe_available = _check_binary("ffprobe", settings.ffprobe_binary)
    if settings.gallery_dl_binary == "gallery-dl":
        # The default invokes `sys.executable -m gallery_dl` (see
        # GalleryExtractor._base_cmd), not a bare PATH lookup, so its
        # availability is really "is the gallery_dl module importable".
        app.state.gallery_dl_available = importlib.util.find_spec("gallery_dl") is not None
        if not app.state.gallery_dl_available:
            logger.warning("gallery_dl Python package is not installed -- /extract-gallery will fail")
    else:
        app.state.gallery_dl_available = _check_binary("gallery-dl", settings.gallery_dl_binary)
    logger.info("DirectStream API %s ready", __version__)
    try:
        yield
    finally:
        await app.state.extractor.aclose()
        await app.state.gallery_extractor.aclose()
        await app.state.proxy.aclose()
        if app.state.transcriber is not None:
            await app.state.transcriber.aclose()
        logger.info("DirectStream API shut down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="DirectStream API",
        description="Extract direct video links and metadata from any webpage.",
        version=__version__,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def _log_context_middleware(request: Request, call_next):
        set_request_context(
            client_ip_from_headers(
                request.headers, request.client.host if request.client else None
            ),
            request.headers.get("user-agent", "-"),
        )
        return await call_next(request)

    @app.exception_handler(ExtractionError)
    async def _extraction_error(_: Request, exc: ExtractionError) -> JSONResponse:
        logger.warning("extraction failed (%s): %s", exc.status, exc)
        return JSONResponse(
            status_code=exc.status, content={"success": False, "error": str(exc)}
        )

    @app.post("/extract-videos", response_model=ExtractResponse)
    async def extract_videos(payload: ExtractRequest) -> ExtractResponse:
        url = payload.url.strip()
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

        logger.info("extracting: %s (cookies=%s)", url, "yes" if cookies else "no")
        try:
            video = await app.state.extractor.extract(url, cookies=cookies)
        except ValueError as exc:
            logger.warning("invalid extract-videos request for %s: %s", url, exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        await cache.set(cache_key, video)
        return ExtractResponse(
            video=to_client_video(video), method=video.method, cached=False
        )

    @app.post("/extract-gallery", response_model=GalleryResponse)
    async def extract_gallery(payload: ExtractRequest) -> GalleryResponse:
        url = payload.url.strip()
        cookies = payload.cookies
        cache: TTLCache[GalleryInfo] = app.state.gallery_cache

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

        logger.info("extracting gallery: %s (cookies=%s)", url, "yes" if cookies else "no")
        try:
            gallery = await app.state.gallery_extractor.extract(url, cookies=cookies)
        except ValueError as exc:
            logger.warning("invalid extract-gallery request for %s: %s", url, exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        await cache.set(cache_key, gallery)
        return GalleryResponse(
            gallery=to_client_gallery(gallery), method=gallery.method, cached=False
        )

    @app.get("/proxy-video")
    async def proxy_video(request: Request) -> Response:
        return await app.state.proxy.handle(request)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            version=__version__,
            timestamp=datetime.now(timezone.utc).isoformat(),
            ffmpeg_available=app.state.ffmpeg_available and app.state.ffprobe_available,
            gallery_dl_available=app.state.gallery_dl_available,
        )

    # ---- Auto-subtitles (speech-to-text via Groq Whisper) ---------------
    # Opt-in, explicit, minutes-long job -- the only place in the app that
    # downloads media bytes to disk. Progress is polled (GET), not pushed;
    # see the ADR in the project plan for why SSE/WebSocket was skipped.

    @app.post("/transcribe", response_model=TranscribeStartResponse)
    async def start_transcribe(payload: TranscribeRequest) -> TranscribeStartResponse:
        if app.state.transcriber is None:
            raise HTTPException(
                status_code=503, detail="Auto-subtitles are not configured on this server"
            )

        job = await app.state.jobs.create()
        asyncio.create_task(
            run_transcription_job(
                job.id, payload.formats, settings, app.state.jobs, app.state.transcriber
            )
        )
        return TranscribeStartResponse(job_id=job.id)

    @app.get("/transcribe/{job_id}", response_model=TranscribeStatus)
    async def get_transcribe_status(job_id: str) -> TranscribeStatus:
        job = await app.state.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Unknown or expired job")

        result = None
        if job.status == "done":
            result = TranscribeResult(
                language=job.language or "en",
                vtt_url=f"/transcribe/{job_id}/subtitle.vtt",
                srt_url=f"/transcribe/{job_id}/subtitle.srt",
                waveform=job.waveform,
            )

        return TranscribeStatus(
            job_id=job.id,
            status=job.status,
            progress=job.progress,
            step_label=job.step_label,
            error=job.error,
            result=result,
        )

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
