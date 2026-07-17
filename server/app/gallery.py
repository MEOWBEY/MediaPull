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
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

from .config import Settings
from .extractor import ExtractionError, classify_extraction_error, is_valid_url
from .models import GalleryImage, GalleryInfo, GalleryWarning
from .net_common import cookie_tempfile, get_cookie_pool, normalize_cookies

logger = logging.getLogger("mediapull.gallery")

# classify_extraction_error's needles are tuned for yt-dlp's error vocabulary
# ("confirm you're not a bot", etc.), which gallery-dl's stderr essentially
# never matches -- most gallery-dl failures fall through to this generic
# message. Overridden with gallery-appropriate wording below.
_GENERIC_EXTRACTION_MESSAGE = (
    "Extraction failed. The site may be unsupported or temporarily unavailable."
)
_GENERIC_GALLERY_MESSAGE = (
    "Image extraction failed. The source may require cookies (Settings → Cookies), "
    "block automated access, or be temporarily unavailable."
)


def _warnings_from_stderr(stderr: str, *, truncated: bool) -> list[GalleryWarning]:
    """Map gallery-dl stderr phrases to soft client-facing warning codes."""
    text = (stderr or "").lower()
    warnings: list[GalleryWarning] = []
    seen: set[str] = set()

    def add(code: str, message: str) -> None:
        if code in seen:
            return
        seen.add(code)
        warnings.append(GalleryWarning(code=code, message=message))

    if any(n in text for n in ("login", "log in", "sign in", "authentication", "401", "403")):
        add(
            "login",
            "Some images may require cookies (Settings → Cookies).",
        )
    if any(n in text for n in ("rate", "429", "too many", "throttl")):
        add("rate_limit", "The site is rate-limiting requests.")
    if any(n in text for n in ("watermark", "lower", "preview", "thumbnail", "degrad")):
        add(
            "quality",
            "Image quality may be reduced without fresh cookies.",
        )
    if truncated:
        add("truncated", "Gallery was truncated to the server maximum.")
    return warnings


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
        binary name when the operator explicitly points GALLERY_DL_PATH at
        something else (a custom wrapper script, a different install, etc.).
        """
        if binary == "gallery-dl":
            return [sys.executable, "-m", "gallery_dl"]
        return [binary]

    def _extract_sync(self, url: str, cookies: str | None) -> GalleryInfo:
        s = self._settings
        cmd = [
            *self._base_cmd(s.gallery_dl_path),
            "-j",  # dump metadata as JSON, no download
            "--no-input",
        ]

        # Authentication cookies: per-request blob (from the user's Settings)
        # wins; otherwise the next server-side default file in the rotation
        # (COOKIE_FILE_PATHS may list several accounts), same fallback order
        # extractor.py uses for yt-dlp. Instagram/X mostly refuse to list
        # content at all without a logged-in session, so this matters more
        # here than for video sites.
        cookie_text = normalize_cookies(cookies, url) if cookies else None
        pool_cookie: str | None = None
        with cookie_tempfile(cookie_text) as cookie_tmp:
            if cookie_tmp:
                cmd += ["--cookies", cookie_tmp]
            else:
                pool_cookie = get_cookie_pool(s).pick()
                if pool_cookie:
                    cmd += ["--cookies", pool_cookie]

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
                    f"gallery-dl is not installed or not on PATH ({s.gallery_dl_path!r})",
                    status=500,
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise ExtractionError("Gallery extraction timed out", status=504) from exc

        images, skipped = self._parse_dump_json(proc.stdout)

        # Prefer stderr classification whenever the run failed or produced no
        # images — partial/non-JSON stdout used to surface as a misleading
        # "No images found" 422 instead of login/rate-limit guidance.
        if proc.returncode != 0 or not images:
            if proc.returncode != 0 or (proc.stderr or "").strip():
                status, message = classify_extraction_error(
                    RuntimeError(proc.stderr or proc.stdout or "gallery-dl failed")
                )
                if pool_cookie and status in (401, 403, 429):
                    get_cookie_pool(s).report_block(pool_cookie)
                if message == _GENERIC_EXTRACTION_MESSAGE:
                    message = _GENERIC_GALLERY_MESSAGE
                # Successful exit + empty listing is a real "no images" case.
                if proc.returncode == 0 and not (proc.stderr or "").strip():
                    raise ExtractionError("No images found at this URL", status=422)
                raise ExtractionError(message, status=status)
            raise ExtractionError("No images found at this URL", status=422)

        if skipped:
            logger.warning(
                "gallery-dl skipped %d unrecognized/errored entr%s for %s",
                skipped,
                "y" if skipped == 1 else "ies",
                url,
            )

        max_images = s.gallery_max_images
        truncated = False
        if len(images) > max_images:
            omitted = len(images) - max_images
            images = images[:max_images]
            skipped += omitted
            truncated = True
            logger.info(
                "gallery truncated to %d images (%d omitted) for %s",
                max_images,
                omitted,
                url,
            )

        # Instagram/X CDN URLs are frequently Referer- or session-gated; the
        # webpage itself is the Referer a real browser would send. The client
        # routes images through the same `/proxy-video` the player uses so
        # this actually gets applied (an <img> tag can't set headers itself).
        # Session cookies are minted client-side from Settings → Cookies via
        # ctok (never returned in extract JSON).
        headers = {"Referer": url}
        for image in images:
            image.http_headers = headers

        return GalleryInfo(
            title=self._guess_title(images, url),
            webpage_url=url,
            images=images,
            skipped=skipped,
            warnings=_warnings_from_stderr(proc.stderr or "", truncated=truncated),
        )

    @staticmethod
    def _guess_title(images: list[GalleryImage], url: str) -> str:
        return urlparse(url).path.rsplit("/", 1)[-1] or urlparse(url).netloc

    # gallery-dl's `-j` dump is a JSON array of message tuples, each tagged by
    # a leading kind code (see gallery_dl.extractor.message.Message). Only
    # Url (3) is an actual image; -1 is a genuine per-item failure. Every
    # other kind -- Directory (2) foremost, emitted once per gallery with the
    # post's metadata and no url -- is normal protocol chatter, not a failed
    # item, and must not be counted as one.
    _KIND_URL = 3
    _KIND_ERROR = -1

    @classmethod
    def _parse_dump_json(cls, stdout: str) -> tuple[list[GalleryImage], int]:
        """Parse `gallery-dl -j` output into a flat image list.

        Per-item failures come back as `(-1, {"error": ..., "message": ...})`
        -- counted in the returned ``skipped`` total and logged by the caller
        rather than silently vanishing, since a gallery that's half-failed
        (common on Instagram/X without fresh cookies) should look different
        from one that fully succeeded. Non-image protocol messages (notably
        the one `Directory` entry every dump starts with) are neither images
        nor failures and are ignored entirely.
        """
        text = stdout.strip()
        if not text:
            return [], 0

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("gallery-dl produced non-JSON output")
            return [], 0

        if not isinstance(data, list):
            return [], 0

        images: list[GalleryImage] = []
        skipped = 0
        for entry in data:
            kind = entry[0] if isinstance(entry, (list, tuple)) and entry else None
            if kind == cls._KIND_ERROR:
                skipped += 1
                continue
            if kind != cls._KIND_URL:
                continue
            image = cls._entry_to_image(entry)
            if image is not None:
                images.append(image)
            else:
                skipped += 1
        return images, skipped

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

        # Instagram (and other extractors with `videos_dash` on) replace a
        # video/reel's real CDN URL with a synthetic `ytdl:<url>` pseudo-URL
        # when it has a DASH manifest. The part after the prefix is a real,
        # directly-fetchable URL -- stripping it is enough to keep the item
        # instead of silently dropping every video in a mixed carousel.
        if url.startswith("ytdl:"):
            url = url[len("ytdl:") :]
            if not url.startswith(("http://", "https://")):
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
