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


class ExtractResponse(BaseModel):
    success: bool = True
    video: ClientVideo
    method: str
    cached: bool = False


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str = "directstream"
    version: str
    timestamp: str
