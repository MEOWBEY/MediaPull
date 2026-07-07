"""Map internal extractor models to the client-facing wire shape.

The SvelteKit client consumes `{ metadata, formats }` with camelCase keys and
builds the proxied URL itself from `sourceVideoUrl` + `httpHeaders`. Keeping this
mapping in one place lets the extractor stay UI-agnostic.
"""

from __future__ import annotations

from .models import (
    ClientFormat,
    ClientGallery,
    ClientGalleryImage,
    ClientMetadata,
    ClientSubtitleTrack,
    ClientVideo,
    GalleryInfo,
    VideoInfo,
)


def to_client_video(info: VideoInfo) -> ClientVideo:
    return ClientVideo(
        metadata=ClientMetadata(
            id=info.id,
            title=info.title,
            duration=info.duration,
            width=info.width,
            height=info.height,
            thumbnail=info.thumbnail,
            upload_date=info.upload_date,
            webpage_url=info.webpage_url,
            aspect_ratio=info.aspect_ratio,
        ),
        formats=[
            ClientFormat(
                format_id=fmt.format_id,
                resolution=fmt.resolution,
                ext=fmt.ext,
                tbr=fmt.tbr,
                protocol=fmt.protocol,
                source_video_url=fmt.url,
                http_headers=fmt.http_headers,
                video_only=fmt.video_only,
            )
            for fmt in info.formats
        ],
        subtitle_tracks=[
            ClientSubtitleTrack(
                lang=track.lang,
                label=track.label,
                url=track.url,
                ext=track.ext,
                is_auto=track.is_auto,
            )
            for track in info.subtitle_tracks
        ],
    )


def to_client_gallery(info: GalleryInfo) -> ClientGallery:
    return ClientGallery(
        title=info.title,
        webpage_url=info.webpage_url,
        images=[
            ClientGalleryImage(
                url=img.url,
                width=img.width,
                height=img.height,
                filesize=img.filesize,
                ext=img.ext,
            )
            for img in info.images
        ],
    )
