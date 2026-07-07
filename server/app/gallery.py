"""Image gallery extraction engine (gallery-dl).

Invoked as a subprocess (not `import`ed) so this app's own license stays
independent of gallery-dl's GPL-3.0 — the same isolation approach as calling
any other GPL CLI tool. Cookie handling is shared with the yt-dlp extractor
via `net_common` (both consume identical Netscape cookies.txt text).

Listing images is a fast, metadata-only operation (`gallery-dl -j`) — no
files are downloaded server-side, matching the existing "app never downloads
media except /transcribe" invariant.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .config import Settings
from .extractor import ExtractionError, classify_extraction_error, is_valid_url
from .models import GalleryImage, GalleryInfo
from .net_common import normalize_cookies

logger = logging.getLogger("directstream.gallery")


class GalleryExtractor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool = ThreadPoolExecutor(
            max_workers=settings.gallery_dl_workers, thread_name_prefix="gallerydl"
        )

    async def aclose(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    async def extract(self, url: str, cookies: str | None = None) -> GalleryInfo:
        if not is_valid_url(url):
            raise ValueError("Invalid URL format")

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(self._pool, self._extract_sync, url, cookies)
        except ExtractionError:
            raise
        except Exception as exc:  # noqa: BLE001 - classify and re-raise as ExtractionError
            status, message = classify_extraction_error(exc)
            raise ExtractionError(message, status=status) from exc

    @staticmethod
    def _base_cmd(binary: str) -> list[str]:
        """Resolve the gallery-dl invocation.

        pip-installed console scripts land in a Scripts/bin directory that
        isn't reliably on PATH (confirmed on Windows) -- `python -m
        gallery_dl` sidesteps that entirely by using the same interpreter
        this process is already running under. Only fall back to a bare
        binary name when the operator explicitly points GALLERY_DL_BINARY at
        something else (a custom wrapper script, a different install, etc.).
        """
        if binary == "gallery-dl":
            return [sys.executable, "-m", "gallery_dl"]
        return [binary]

    def _extract_sync(self, url: str, cookies: str | None) -> GalleryInfo:
        s = self._settings
        cmd = [
            *self._base_cmd(s.gallery_dl_binary),
            "-j",  # dump metadata as JSON, no download
            "--no-input",
        ]

        cookie_tmp: str | None = None
        cookie_text = normalize_cookies(cookies, url) if cookies else None
        if cookie_text:
            handle = tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, encoding="utf-8"
            )
            try:
                handle.write(cookie_text)
            finally:
                handle.close()
            cookie_tmp = handle.name
            cmd += ["--cookies", cookie_tmp]

        cmd.append(url)  # URL must be last -- a positional arg, not a flag value

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=s.gallery_dl_timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ExtractionError(
                f"gallery-dl is not installed or not on PATH ({s.gallery_dl_binary!r})",
                status=500,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError("Gallery extraction timed out", status=504) from exc
        finally:
            if cookie_tmp is not None:
                try:
                    os.unlink(cookie_tmp)
                except OSError:
                    pass

        if proc.returncode != 0 and not proc.stdout.strip():
            status, message = classify_extraction_error(RuntimeError(proc.stderr))
            raise ExtractionError(message, status=status)

        images = self._parse_dump_json(proc.stdout)
        if not images:
            raise ExtractionError("No images found at this URL", status=422)

        return GalleryInfo(
            title=self._guess_title(images, url),
            webpage_url=url,
            images=images,
        )

    @staticmethod
    def _guess_title(images: list[GalleryImage], url: str) -> str:
        return urlparse(url).path.rsplit("/", 1)[-1] or urlparse(url).netloc

    @classmethod
    def _parse_dump_json(cls, stdout: str) -> list[GalleryImage]:
        """Parse `gallery-dl -j` output into a flat image list.

        Output shape varies by gallery-dl version but is consistently a JSON
        array of `[status, url, metadata]` entries (metadata optional/last).
        Parsing is defensive — unexpected shapes are skipped rather than
        raising, since a partial gallery is better than none.
        """
        text = stdout.strip()
        if not text:
            return []

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("gallery-dl produced non-JSON output")
            return []

        if not isinstance(data, list):
            return []

        images: list[GalleryImage] = []
        for entry in data:
            image = cls._entry_to_image(entry)
            if image is not None:
                images.append(image)
        return images

    @staticmethod
    def _entry_to_image(entry) -> GalleryImage | None:  # noqa: ANN001
        url: str | None = None
        meta: dict = {}

        if isinstance(entry, (list, tuple)):
            for item in entry:
                if isinstance(item, str) and item.startswith(("http://", "https://")):
                    url = item
                elif isinstance(item, dict):
                    meta = item
        elif isinstance(entry, dict):
            meta = entry
            url = entry.get("url")

        if not url:
            return None

        return GalleryImage(
            url=url,
            # Field names vary by gallery-dl extractor/site backend -- these
            # are the actual keys observed (e.g. Danbooru: image_width/
            # image_height/file_size/extension), with generic fallbacks for
            # extractors that use plainer names.
            width=meta.get("image_width") or meta.get("width"),
            height=meta.get("image_height") or meta.get("height"),
            filesize=meta.get("file_size") or meta.get("filesize") or meta.get("size"),
            ext=meta.get("file_ext") or meta.get("extension") or meta.get("ext") or "jpg",
        )
