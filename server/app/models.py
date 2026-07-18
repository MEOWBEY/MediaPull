"""Request/response schemas. These define the wire contract with the client.

Two layers:
  * Internal models (`VideoFormat`, `VideoInfo`) — what the extractor produces.
  * Client models (`ClientFormat`/`ClientMetadata`/`ClientVideo`) — the exact
    camelCase shape the SvelteKit client consumes (`{ metadata, formats }`).
    `serializers.to_client_video` maps internal → client.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExtractRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    # Optional per-request authentication cookies for the URL's site, supplied
    # by the user from the client's Settings → Cookies panel. Either Netscape
    # cookies.txt text or a single "Cookie: a=b; c=d" header line. Stored only
    # in the user's browser; written to a throwaway temp file for one yt-dlp or
    # gallery-dl run and deleted. Cap matches MAX_COOKIE_BYTES. Falls back to
    # the server-side COOKIE_FILE_PATHS when absent.
    cookies: str | None = Field(default=None, max_length=262_144)


# ----- internal extractor models ----------------------------------------


class VideoFormat(BaseModel):
    url: str | None = Field(default=None, max_length=8192)
    ext: str = "mp4"
    tbr: float | None = None
    format_id: str = "unknown"
    protocol: str = "https"
    http_headers: dict[str, str] | None = None
    resolution: int | None = None
    # True for adaptive streams that carry video but no audio (e.g. YouTube's
    # high-res formats). Surfaced so the UI can flag "video only".
    video_only: bool = False


class SubtitleTrack(BaseModel):
    """An existing caption track the source already provides (from yt-dlp's
    ``subtitles``/``automatic_captions`` metadata) -- free to surface, no
    transcription needed. The transcription pipeline is a fallback for videos
    that have none of these, or none in the language the user wants."""

    lang: str
    label: str
    url: str
    ext: str = "vtt"
    is_auto: bool = False


class VideoInfo(BaseModel):
    id: str | None = None
    title: str | None = None
    thumbnail: str | None = None
    duration: float | None = None
    upload_date: str | None = None
    webpage_url: str | None = None
    width: int | None = None
    height: int | None = None
    aspect_ratio: float | None = None
    formats: list[VideoFormat] = Field(default_factory=list)
    subtitle_tracks: list[SubtitleTrack] = Field(default_factory=list)
    method: str = "unknown"


# ----- client-facing models (camelCase wire shape) ----------------------


class ClientFormat(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    format_id: str = "unknown"
    resolution: int | None = None
    ext: str = "mp4"
    tbr: float | None = None
    protocol: str = "https"
    source_video_url: str | None = Field(default=None, alias="sourceVideoUrl")
    http_headers: dict[str, str] | None = Field(default=None, alias="httpHeaders")
    video_only: bool = Field(default=False, alias="videoOnly")


class ClientSubtitleTrack(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lang: str
    label: str
    url: str
    ext: str = "vtt"
    is_auto: bool = Field(default=False, alias="isAuto")


class ClientMetadata(BaseModel):
    id: str | None = None
    title: str | None = None
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    thumbnail: str | None = None
    upload_date: str | None = None
    webpage_url: str | None = None
    aspect_ratio: float | None = None


class ClientVideo(BaseModel):
    metadata: ClientMetadata
    formats: list[ClientFormat] = Field(default_factory=list)
    subtitle_tracks: list[ClientSubtitleTrack] = Field(
        default_factory=list, alias="subtitleTracks"
    )

    model_config = ConfigDict(populate_by_name=True)


class ExtractResponse(BaseModel):
    success: bool = True
    video: ClientVideo
    method: str
    cached: bool = False


# ----- gallery/image extraction (gallery-dl) -----------------------------


class GalleryImage(BaseModel):
    url: str
    width: int | None = None
    height: int | None = None
    filesize: int | None = None
    ext: str = "jpg"
    # Referer (and, when available, cookies) the client needs to actually load
    # this image -- Instagram/X CDN URLs are frequently Referer- or
    # session-gated, so an <img> tag pointed straight at them 403s. Mirrors
    # VideoFormat.http_headers; the client proxies through the same
    # `/proxy-video` the player already uses.
    http_headers: dict[str, str] | None = None


class GalleryWarning(BaseModel):
    """Soft notice about a gallery extract (login, quality, truncation, …)."""

    code: str
    message: str


class GalleryInfo(BaseModel):
    title: str | None = None
    webpage_url: str | None = None
    images: list[GalleryImage] = Field(default_factory=list)
    method: str = "gallery-dl"
    # Entries gallery-dl reported as errors, or that came back in a shape this
    # app doesn't recognize -- surfaced instead of silently vanishing, so a
    # partially-failed gallery (common on Instagram/X without fresh cookies)
    # is visible to the user rather than looking like "extraction is flaky".
    skipped: int = 0
    warnings: list[GalleryWarning] = Field(default_factory=list)


class ClientGalleryImage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    width: int | None = None
    height: int | None = None
    filesize: int | None = None
    ext: str = "jpg"
    http_headers: dict[str, str] | None = Field(default=None, alias="httpHeaders")


class ClientGalleryWarning(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    code: str
    message: str


class ClientGallery(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    webpage_url: str | None = Field(default=None, alias="webpageUrl")
    images: list[ClientGalleryImage] = Field(default_factory=list)
    skipped: int = Field(default=0, alias="skippedCount")
    warnings: list[ClientGalleryWarning] = Field(default_factory=list)


class GalleryResponse(BaseModel):
    success: bool = True
    gallery: ClientGallery
    method: str
    cached: bool = False


class ProxyTokenRequest(BaseModel):
    """Client exchanges a source's auth cookies for an opaque token so the
    cookies never ride in the proxy URL (which gets copied / QR'd / shared)."""

    cookies: str = Field(max_length=262_144)


class ProxyTokenResponse(BaseModel):
    token: str


class CookieUploadRequest(BaseModel):
    """Admin pushes freshly-exported cookies to replace a server-side default
    cookie file (see POST /admin/cookies). The blob is normalized to Netscape
    format server-side, same as per-request cookies."""

    cookies: str = Field(max_length=262_144)


class CookieUploadResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    path: str
    cookie_lines: int = Field(alias="cookieLines")


class HealthResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = "healthy"
    service: str = "mediapull"
    version: str
    timestamp: str
    # Surfaced so deploy tooling (install.sh's verification step, uptime
    # monitoring) can catch a broken ffmpeg/gallery-dl install at boot
    # instead of only discovering it when a real /transcribe or
    # /extract-gallery request fails.
    ffmpeg_available: bool = Field(default=True, alias="ffmpegAvailable")
    gallery_dl_available: bool = Field(default=True, alias="galleryDlAvailable")
    # Whether the bgutil PO-token sidecar answered at boot. False means YouTube
    # age-gated / bot-checked extraction will likely fail even with cookies --
    # check that mediapull-pot is running.
    pot_available: bool = Field(default=False, alias="potAvailable")


# ----- transcription (auto-subtitles) ---------------------------------------------


class TranscribeRequest(BaseModel):
    """Kicks off auto-subtitle generation: speech becomes text in whatever
    language it was spoken -- no translation direction. If the video already
    has a usable caption track (``VideoInfo.subtitle_tracks``), the client
    should use that directly instead of calling this at all."""

    webpage_url: str = Field(max_length=4096)
    formats: list[VideoFormat] = Field(min_length=1, max_length=40)
    cookies: str | None = Field(default=None, max_length=262_144)
    # Video duration as the player knows it -- lets the server turn ffmpeg's
    # out_time into a real acquisition percentage even for sources it can't
    # cheaply probe (HLS). Optional: progress degrades gracefully without it.
    duration_seconds: float | None = Field(default=None, ge=0, le=86_400)


class TranscribeStartResponse(BaseModel):
    job_id: str = Field(alias="jobId")

    model_config = ConfigDict(populate_by_name=True)


class TranscribeResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    language: str
    vtt_url: str = Field(alias="vttUrl")
    srt_url: str = Field(alias="srtUrl")
    dialogue_map: list[float] | None = Field(default=None, alias="dialogueMap")


class TranscribeStatus(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId")
    status: str
    progress: float
    step_label: str = Field(alias="stepLabel")
    # Fine-grained sub-stage code the client maps to its own localized text
    # (planning / downloading_source / extracting / compressing / transcribing /
    # building_subtitles / dialogue_map). More specific than `status`, which stays
    # coarse for back-compat. None until the pipeline sets one.
    detail: str | None = Field(default=None, alias="detail")
    # Transcription chunk counters (0 until that stage) -- lets the client
    # render/localize its own "x of y" text instead of parsing stepLabel.
    chunks_done: int = Field(default=0, alias="chunksDone")
    chunks_total: int = Field(default=0, alias="chunksTotal")
    error: str | None = None
    result: TranscribeResult | None = None
