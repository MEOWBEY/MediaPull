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
    # in the user's browser; written to a throwaway temp file for one yt-dlp
    # call and deleted. Falls back to the server-side COOKIE_FILE when absent.
    cookies: str | None = Field(default=None, max_length=262_144)


# ----- internal extractor models ----------------------------------------


class VideoFormat(BaseModel):
    url: str | None = None
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


class GalleryInfo(BaseModel):
    title: str | None = None
    webpage_url: str | None = None
    images: list[GalleryImage] = Field(default_factory=list)
    method: str = "gallery-dl"


class ClientGalleryImage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    url: str
    width: int | None = None
    height: int | None = None
    filesize: int | None = None
    ext: str = "jpg"


class ClientGallery(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = None
    webpage_url: str | None = Field(default=None, alias="webpageUrl")
    images: list[ClientGalleryImage] = Field(default_factory=list)


class GalleryResponse(BaseModel):
    success: bool = True
    gallery: ClientGallery
    method: str
    cached: bool = False


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "directstream"
    version: str
    timestamp: str


# ----- transcription (auto-subtitles) ---------------------------------------------


class TranscribeRequest(BaseModel):
    """Kicks off auto-subtitle generation: speech becomes text in whatever
    language it was spoken -- no translation direction. If the video already
    has a usable caption track (``VideoInfo.subtitle_tracks``), the client
    should use that directly instead of calling this at all."""

    webpage_url: str
    formats: list[VideoFormat]
    cookies: str | None = Field(default=None, max_length=262_144)


class TranscribeStartResponse(BaseModel):
    job_id: str = Field(alias="jobId")

    model_config = ConfigDict(populate_by_name=True)


class TranscribeResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    language: str
    vtt_url: str = Field(alias="vttUrl")
    srt_url: str = Field(alias="srtUrl")
    waveform: list[float] | None = None


class TranscribeStatus(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId")
    status: str
    progress: float
    step_label: str = Field(alias="stepLabel")
    error: str | None = None
    result: TranscribeResult | None = None
