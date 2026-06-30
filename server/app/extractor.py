"""Video extraction engine.

Strategy chain (first success wins):
  1. yt-dlp (native extractors)
  2. yt-dlp generic extractor
  3. raw HTML regex scrape

Direct video-file URLs short-circuit the chain with a HEAD probe.

Blocking work (yt-dlp) runs in a bounded thread pool; all network I/O for
direct/scrape paths uses async httpx so the event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from urllib.parse import urlparse

import httpx
import yt_dlp
from curl_cffi.requests import AsyncSession

from .config import Settings
from .models import VideoFormat, VideoInfo

logger = logging.getLogger("directstream.extractor")

VIDEO_EXTENSIONS = (
    ".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".3gp", ".ts",
)
# Broad "media URL anywhere in the page/inline-JSON" patterns. Run against the
# slash-unescaped page so `https:\/\/…\.mp4` (very common in embedded JSON)
# matches too.
_SCRAPE_PATTERNS = (
    re.compile(r'https?://[^"\s<>\\]+\.mp4[^"\s<>\\]*', re.IGNORECASE),
    re.compile(r'https?://[^"\s<>\\]+\.webm[^"\s<>\\]*', re.IGNORECASE),
    re.compile(r'https?://[^"\s<>\\]+\.m3u8[^"\s<>\\]*', re.IGNORECASE),
    re.compile(r'https?://[^"\s<>\\]+\.(?:mov|m4v|ts)[^"\s<>\\]*', re.IGNORECASE),
)
# Targeted selectors — sites that don't expose a bare media URL often still
# declare the stream in metadata or a <video>/<source> tag. These are trusted
# (intended-for-playback) so we keep them even without a media extension and let
# downstream link-validation drop any that turn out to be HTML landing pages.
_META_VIDEO_PATTERNS = (
    re.compile(
        r'<meta[^>]+(?:property|name)=["\'](?:og:video(?::secure_url|:url)?|twitter:player:stream)["\']'
        r'[^>]*\bcontent=["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
    re.compile(  # same tag, attribute order reversed (content before property)
        r'<meta[^>]+\bcontent=["\']([^"\']+)["\'][^>]+'
        r'(?:property|name)=["\'](?:og:video(?::secure_url|:url)?|twitter:player:stream)["\']',
        re.IGNORECASE,
    ),
)
_SOURCE_SRC_PATTERN = re.compile(r'<(?:source|video)[^>]+\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)
_JSONLD_URL_PATTERN = re.compile(r'"(?:contentUrl|embedUrl)"\s*:\s*"([^"]+)"', re.IGNORECASE)
_OG_TITLE_PATTERN = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]*\bcontent=["\']([^"\']+)["\']', re.IGNORECASE
)
_TITLE_PATTERN = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
_OG_IMAGE_PATTERN = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]*\bcontent=["\']([^"\']+)["\']', re.IGNORECASE
)
_MEDIA_EXT_HINT = re.compile(r"\.(?:mp4|webm|m3u8|mov|m4v|ts)(?:[?#]|$)", re.IGNORECASE)


def _build_impersonate(client: str):
    """Build a yt-dlp ImpersonateTarget, or None if unavailable.

    Browser impersonation routes yt-dlp's requests through curl_cffi so the
    TLS/HTTP fingerprint matches a real browser. A lot of sites (tiktok, …) now gate on this and answer plain-Python
    requests with 403/410. If curl_cffi isn't installed we degrade gracefully —
    extraction still runs, just without the anti-bot bypass.
    """
    if not client:
        return None
    try:
        import curl_cffi  # noqa: F401  (presence check — yt-dlp uses it internally)
        from yt_dlp.networking.impersonate import ImpersonateTarget
    except Exception:  # noqa: BLE001 - missing dep / yt-dlp internals moved
        logger.warning(
            "curl_cffi unavailable; browser impersonation off "
            "(some sites may return 403/410). Install it: pip install curl_cffi"
        )
        return None
    try:
        return ImpersonateTarget.from_str(client)
    except Exception as exc:  # noqa: BLE001 - bad client string
        logger.warning("could not build impersonate target %r: %s", client, exc)
        return None


class ExtractionError(Exception):
    """Raised when every strategy fails. Carries an HTTP status for the API."""

    def __init__(self, message: str, *, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def classify_extraction_error(exc: Exception | None) -> tuple[int, str]:
    """Map a raw yt-dlp/httpx failure to (http_status, user-facing message).

    Messages stay in English on purpose (they quote upstream tools and are
    technical). Falls back to a clean generic message when nothing matches.
    """
    text = str(exc or "").lower()

    def has(*needles: str) -> bool:
        return any(n in text for n in needles)

    if has(
        "confirm you're not a bot",
        "confirm you’re not a bot",
        "sign in to confirm",
        "not a bot",
    ):
        return 429, (
            "The source flagged the server as a bot (common on datacenter IPs). "
            "Add your cookies in Settings → Cookies, or try again later."
        )
    if has("rate-limit", "rate limit", "too many requests", "429"):
        return 429, (
            "The source is rate-limiting requests (HTTP 429). Slow down, or add "
            "your cookies in Settings → Cookies to authenticate."
        )
    if has("403", "forbidden", "access denied"):
        return 403, (
            "The source blocked the request (HTTP 403). The link may require "
            "login/cookies or be hotlink-protected. Add cookies in Settings or "
            "try the proxy toggle."
        )
    if has("410", "gone"):
        return 410, "The video is no longer available at the source (HTTP 410)."
    if has("404", "not found"):
        return 404, "The page or video could not be found (HTTP 404)."
    if has("geo", "not available in your country", "geo-restricted", "geo restricted"):
        return 451, "This video is geo-restricted and not available from the server's region."
    if has("private video", "this video is private"):
        return 403, (
            "This video is private. If you have access, add your cookies in "
            "Settings → Cookies."
        )
    if has("age", "age-restricted", "age restricted", "confirm your age", "inappropriate for some"):
        return 403, (
            "This video is age-restricted. Add cookies from a logged-in "
            "account in Settings → Cookies to extract it."
        )
    if has("login required", "requested content is not available", "private", "members-only"):
        return 401, (
            "This content needs sign-in. Add your cookies in Settings → Cookies "
            "to access it."
        )
    if has("sign in", "log in", "authentication"):
        return 401, (
            "This video requires sign-in. Add your cookies in Settings → Cookies."
        )
    if has("unsupported url", "no suitable", "is not a valid url"):
        return 422, "This site or URL isn't supported by the extractor."
    if has("no video", "no valid video formats", "no video formats", "no video urls"):
        return 422, "No playable video formats were found on this page."
    if has("timed out", "timeout"):
        return 504, "The source took too long to respond. Please try again."
    return 502, "Extraction failed. The site may be unsupported or temporarily unavailable."


def is_direct_video(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) or f"{ext}?" in url.lower() for ext in VIDEO_EXTENSIONS)


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return bool(parsed.netloc and parsed.scheme in ("http", "https"))
    except ValueError:
        return False


class Extractor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._impersonate = (
            _build_impersonate(settings.impersonate_client)
            if settings.enable_impersonation
            else None
        )
        if self._impersonate is not None:
            logger.info("browser impersonation enabled: %s", settings.impersonate_client)
        self._pool = ThreadPoolExecutor(
            max_workers=settings.extract_workers, thread_name_prefix="ytdlp"
        )
        # Optional outbound proxy, shared by the scrape client, the probe session
        # and (via ProxyService) media streaming, so everything leaves the box
        # from the same egress.
        self._proxy = settings.proxy_url or None
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(settings.request_timeout),
            headers={"User-Agent": settings.user_agent},
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            proxy=self._proxy,
        )
        # Impersonating session used only to validate format URLs — it mirrors
        # what the proxy does, so a probe that fails is a genuinely dead link
        # (not just one that needs proxy headers). Lazily created.
        self._probe_session: AsyncSession | None = None

    def _probe_kwargs(self) -> dict:
        s = self._settings
        if s.enable_impersonation and s.impersonate_client:
            return {"impersonate": s.impersonate_client}
        return {}

    async def aclose(self) -> None:
        await self._client.aclose()
        if self._probe_session is not None:
            await self._probe_session.close()
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ----- public API ---------------------------------------------------

    async def extract(self, url: str, cookies: str | None = None) -> VideoInfo:
        if not is_valid_url(url):
            raise ValueError("Invalid URL format")

        if is_direct_video(url):
            return await self._direct_video(url)

        timeout = self._settings.request_timeout
        half = max(10, timeout // 2)
        strategies = (
            ("yt-dlp", lambda: self._ytdlp(url, generic=False, cookies=cookies), timeout),
            ("yt-dlp-generic", lambda: self._ytdlp(url, generic=True, cookies=cookies), half),
            ("html-scrape", lambda: self._scrape(url), half),
        )

        last_error: Exception | None = None
        for name, make_coro, budget in strategies:
            try:
                info = await asyncio.wait_for(make_coro(), timeout=budget)
            except Exception as exc:  # noqa: BLE001 - record and fall through
                last_error = exc
                logger.warning("strategy %s failed: %s", name, exc)
                continue

            if self._settings.validate_formats:
                info.formats = await self._validate_formats(info.formats)
                if not info.formats:
                    # Every link this strategy found is dead — fall through to the
                    # next one (which may surface working links).
                    last_error = ExtractionError("All extracted links were unreachable")
                    logger.warning("strategy %s: all formats failed validation", name)
                    continue

            return info

        status, message = classify_extraction_error(last_error)
        raise ExtractionError(message, status=status) from last_error

    # ----- format validation -------------------------------------------

    async def _validate_formats(self, formats: list[VideoFormat]) -> list[VideoFormat]:
        """Probe each format and drop only the ones confirmed dead.

        "Confirmed dead" = a definitive 4xx/5xx or an HTML error page when
        fetched the same way the proxy would (impersonation + the format's own
        headers). Anything uncertain — a timeout, a network blip, a server that
        refuses probes — is *kept*: hiding a working link is worse than leaving a
        dead one. Probes run concurrently, deduped by URL.
        """
        if not formats:
            return formats

        if self._probe_session is None:
            self._probe_session = AsyncSession(
                timeout=self._settings.validate_timeout,
                max_clients=self._settings.validate_concurrency,
                proxies={"http": self._proxy, "https": self._proxy} if self._proxy else None,
            )

        sem = asyncio.Semaphore(self._settings.validate_concurrency)
        verdicts: dict[str, bool] = {}

        async def check(url: str, headers: dict | None) -> None:
            async with sem:
                verdicts[url] = await self._probe_ok(url, headers)

        # One probe per unique URL.
        seen: dict[str, dict | None] = {}
        for fmt in formats:
            if fmt.url and fmt.url not in seen:
                seen[fmt.url] = fmt.http_headers
        await asyncio.gather(*(check(u, h) for u, h in seen.items()))

        kept = [f for f in formats if f.url and verdicts.get(f.url, True)]
        dropped = len(formats) - len(kept)
        if dropped:
            logger.info("validation dropped %d/%d dead formats", dropped, len(formats))
        return kept

    async def _probe_ok(self, url: str, http_headers: dict | None) -> bool:
        """True unless the URL is *unambiguously* gone.

        Deliberately conservative — only **404/410** or a **200 HTML page** (a
        "video unavailable" landing page served instead of media) count as dead.
        Signed CDN links (TikTok, etc.) often answer a re-issued probe with 403
        even though real playback works, and 403/needs-proxy links work through
        the proxy, so 403/401/5xx/timeouts all *keep* the format. We use a
        single tiny ranged GET (HEAD is widely rejected).
        """
        headers = dict(http_headers or {})
        kwargs = self._probe_kwargs()
        if kwargs:
            # Impersonation sets a matching UA; a conflicting one defeats it.
            headers.pop("User-Agent", None)
            headers.pop("user-agent", None)

        try:
            resp = await self._probe_session.get(
                url,
                headers={**headers, "Range": "bytes=0-1"},
                allow_redirects=True,
                stream=True,
                **kwargs,
            )
            status = resp.status_code
            content_type = resp.headers.get("content-type", "")
            await resp.aclose()
        except Exception:  # noqa: BLE001 - uncertain → keep the format
            return True

        if status in (404, 410):
            return False
        # A 2xx that hands back HTML is a landing/error page, not media.
        # (HLS/m3u8 is text but not text/html, so it's safe.)
        if status < 400 and "text/html" in content_type.lower():
            return False
        return True

    # ----- strategies ---------------------------------------------------

    async def _direct_video(self, url: str) -> VideoInfo:
        try:
            resp = await self._client.head(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExtractionError(f"Could not process direct video URL: {exc}") from exc

        filename = (urlparse(url).path.rsplit("/", 1)[-1]) or "video.mp4"
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "mp4"
        return VideoInfo(
            id=filename,
            title=filename.rsplit(".", 1)[0],
            webpage_url=url,
            method="direct",
            formats=[VideoFormat(url=url, ext=ext, format_id="direct")],
        )

    async def _ytdlp(self, url: str, *, generic: bool, cookies: str | None = None) -> VideoInfo:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, self._ytdlp_sync, url, generic, cookies)

    def _build_extractor_args(self) -> dict:
        """yt-dlp extractor_args from config (currently YouTube only).

        Lets the deploy choose player clients (e.g. ``default,tv,web_safari`` —
        keeps the full quality ladder while adding age-gate-capable clients) and
        pass PO token(s) so a datacenter IP can clear bot-detection.
        """
        s = self._settings
        youtube: dict[str, list[str]] = {}
        if s.youtube_player_client_list:
            youtube["player_client"] = s.youtube_player_client_list
        if s.youtube_po_token_list:
            youtube["po_token"] = s.youtube_po_token_list
        return {"youtube": youtube} if youtube else {}

    def _normalize_cookies(self, raw: str, url: str) -> str | None:
        """Coerce user-pasted cookies into Netscape cookies.txt text.

        Accepts either the Netscape/Mozilla export (tab-separated rows, what the
        "Get cookies.txt LOCALLY" extension produces) or a single
        ``Cookie: a=b; c=d`` header line, which we convert to Netscape rows
        scoped to the URL's host. Returns None when there's nothing usable.
        """
        text = (raw or "").strip()
        if not text:
            return None

        # Netscape/Mozilla format already (rows are tab-separated). Ensure the
        # magic header line is present — MozillaCookieJar refuses files without it.
        if "\t" in text:
            return text if text.lstrip().startswith("#") else "# Netscape HTTP Cookie File\n" + text

        # Header-style cookies: "Cookie: a=b; c=d" or just "a=b; c=d".
        if text.lower().startswith("cookie:"):
            text = text.split(":", 1)[1]
        pairs = [p.strip() for p in text.split(";") if "=" in p]
        if not pairs:
            return None

        host = (urlparse(url).hostname or "").lower()
        domain = host[4:] if host.startswith("www.") else host
        if not domain:
            return None
        dot_domain = "." + domain

        # domain \t include_subdomains \t path \t secure \t expiry \t name \t value
        lines = ["# Netscape HTTP Cookie File"]
        for pair in pairs:
            name, _, value = pair.partition("=")
            name = name.strip()
            if name:
                lines.append("\t".join((dot_domain, "TRUE", "/", "TRUE", "0", name, value.strip())))
        return "\n".join(lines) + "\n" if len(lines) > 1 else None

    def _ytdlp_sync(self, url: str, generic: bool, cookies: str | None = None) -> VideoInfo:
        s = self._settings
        opts: dict[str, object] = {
            "quiet": True,
            "no_warnings": True,
            # No "format" pin: we want the full ladder in info["formats"] and do
            # our own selection in _select_formats (pinning would only matter for
            # downloads and can hide adaptive/high-res streams).
            "extract_flat": False,
            "ignoreerrors": True,
            "noplaylist": True,
            "retries": s.max_retries,
            "extractor_retries": s.max_retries,
            "fragment_retries": 0,
            "socket_timeout": s.request_timeout,
            "geo_bypass": True,
            "no_color": True,
            "no_progress": True,
            # NOTE: youtube player_client is NOT pinned by default. yt-dlp's
            # default selection returns the full ladder (144p–2160p); forcing a
            # single mobile client collapses YouTube to 360p. Override via
            # YOUTUBE_PLAYER_CLIENTS (keep "default" in the list to preserve it).
        }

        if self._impersonate is not None:
            # Let curl_cffi mimic a real browser end-to-end. Don't also force a
            # User-Agent header — a UA that disagrees with the impersonated TLS
            # fingerprint defeats the point and can trigger the very 403 we're
            # dodging.
            opts["impersonate"] = self._impersonate
        else:
            opts["http_headers"] = {"User-Agent": s.user_agent}

        if self._proxy:
            opts["proxy"] = self._proxy
        if s.sleep_requests:
            # Random-ish spacing between extractor requests — the cheapest way to
            # avoid 429/"used too much" blocks under load.
            opts["sleep_interval_requests"] = s.sleep_requests
        extractor_args = self._build_extractor_args()
        if extractor_args:
            opts["extractor_args"] = extractor_args

        if generic:
            opts.update(force_generic_extractor=True, nocheckcertificate=True)

        # Authentication cookies: per-request blob (from the user's Settings)
        # wins; otherwise the server-side default file. The temp file lives only
        # for this one extraction and is removed right after.
        cookie_tmp: str | None = None
        cookie_text = self._normalize_cookies(cookies, url) if cookies else None
        if cookie_text:
            handle = tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, encoding="utf-8"
            )
            try:
                handle.write(cookie_text)
            finally:
                handle.close()
            cookie_tmp = handle.name
            opts["cookiefile"] = cookie_tmp
        elif s.cookie_file:
            opts["cookiefile"] = s.cookie_file

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        finally:
            if cookie_tmp is not None:
                try:
                    os.unlink(cookie_tmp)
                except OSError:
                    pass

        if not info:
            raise ExtractionError("No video information extracted")

        raw_formats = info.get("formats") or []
        formats = self._select_formats(raw_formats, s.max_formats)
        if not formats and info.get("url"):
            formats = [self._to_format(info)]
        if not formats:
            raise ExtractionError("No valid video formats found")

        title = (info.get("title") or "Unknown Video")[:200]
        return VideoInfo(
            id=info.get("id") or info.get("title"),
            title=title,
            thumbnail=info.get("thumbnail"),
            duration=info.get("duration"),
            upload_date=info.get("upload_date"),
            webpage_url=info.get("webpage_url") or info.get("original_url") or url,
            width=info.get("width"),
            height=info.get("height"),
            aspect_ratio=info.get("aspect_ratio"),
            formats=formats,
            method="generic_ydl" if generic else "ydl",
        )

    @classmethod
    def _select_formats(cls, raw_formats: list[dict], limit: int) -> list[VideoFormat]:
        """Filter junk, keep playable streams, dedupe, sort best-first.

        yt-dlp returns formats worst-first and mixes in storyboards/images. We
        keep progressive (audio+video), HLS, audio-only AND high-res video-only
        adaptive streams (so YouTube's >720p qualities show up, flagged
        ``video_only``). We drop only true junk and segmented-DASH manifests the
        browser can't play directly.

        Dedupe by (resolution, family, video_only) so a muxed and a video-only
        stream at the same resolution both survive; rank muxed above video-only
        at equal resolution.
        """
        candidates: list[VideoFormat] = []
        for fmt in raw_formats:
            if not cls._is_playable(fmt):
                continue
            candidates.append(cls._to_format(fmt))

        # Highest resolution first; at equal resolution prefer muxed (has audio)
        # over video-only; then highest bitrate.
        candidates.sort(
            key=lambda f: ((f.resolution or 0), (0 if f.video_only else 1), (f.tbr or 0)),
            reverse=True,
        )

        seen: set[tuple] = set()
        unique: list[VideoFormat] = []
        for fmt in candidates:
            family = "hls" if fmt.protocol == "m3u8_native" else fmt.ext
            key = (fmt.resolution or 0, family, fmt.video_only)
            if key in seen:
                continue
            seen.add(key)
            unique.append(fmt)
            if len(unique) >= limit:
                break
        return unique

    @staticmethod
    def _is_playable(fmt: dict) -> bool:
        if not fmt.get("url"):
            return False

        protocol = (fmt.get("protocol") or "").lower()
        # Storyboards / segmented-DASH manifests / unsupported transports the
        # browser can't play directly.
        if "mhtml" in protocol or protocol in ("dash", "http_dash_segments"):
            return False

        ext = (fmt.get("ext") or "").lower()
        if ext in ("mhtml", "json", "xml", "html"):
            return False

        # Everything else (progressive muxed, HLS, audio-only, and progressive
        # video-only adaptive streams) is kept. Video-only is flagged downstream
        # so the UI can label it; it still plays (silently) and is downloadable.
        return True

    @staticmethod
    def _normalize_protocol(fmt: dict) -> str:
        protocol = (fmt.get("protocol") or "").lower()
        ext = (fmt.get("ext") or "").lower()
        url = (fmt.get("url") or "").lower()
        if "m3u8" in protocol or ext == "m3u8" or ".m3u8" in url:
            return "m3u8_native"
        return "https"

    @classmethod
    def _to_format(cls, fmt: dict) -> VideoFormat:
        protocol = cls._normalize_protocol(fmt)
        ext = fmt.get("ext") or ("m3u8" if protocol == "m3u8_native" else "mp4")

        vcodec = (fmt.get("vcodec") or "").lower()
        acodec = (fmt.get("acodec") or "").lower()
        has_video = vcodec not in ("", "none")
        has_audio = acodec not in ("", "none")
        # HLS reports no codecs up front but carries audio — never video-only.
        is_hls = protocol == "m3u8_native"
        video_only = has_video and not has_audio and not is_hls

        return VideoFormat(
            url=fmt.get("url"),
            ext=ext,
            tbr=fmt.get("tbr"),
            format_id=str(fmt.get("format_id") or fmt.get("format") or "unknown"),
            protocol=protocol,
            http_headers=fmt.get("http_headers"),
            resolution=fmt.get("height"),
            video_only=video_only,
        )

    async def _scrape(self, url: str) -> VideoInfo:
        limit = self._settings.scrape_max_bytes
        parsed = urlparse(url)
        # Browser-ish headers: a bare httpx request gets 403'd by anti-leech
        # pages. Referer = the site's own origin mimics in-site navigation.
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{parsed.scheme}://{parsed.netloc}/",
        }
        try:
            async with self._client.stream("GET", url, headers=headers) as resp:
                resp.raise_for_status()
                chunks: list[str] = []
                size = 0
                async for chunk in resp.aiter_text(chunk_size=8192):
                    chunks.append(chunk)
                    size += len(chunk)
                    if size >= limit:
                        break
                content = "".join(chunks)
        except httpx.HTTPError as exc:
            raise ExtractionError(f"Scraping failed: {exc}") from exc

        found = self._scrape_media_urls(content, base=url)
        if not found:
            raise ExtractionError("No video URLs found in page")

        formats = [
            VideoFormat(
                url=video_url,
                ext="m3u8" if ".m3u8" in video_url.lower() else "mp4",
                protocol="m3u8_native" if ".m3u8" in video_url.lower() else "https",
                format_id=f"scraped_{i}",
            )
            for i, video_url in enumerate(found)
        ]
        return VideoInfo(
            id=parsed.netloc,
            title=self._scrape_title(content),
            thumbnail=self._scrape_first(content, _OG_IMAGE_PATTERN),
            webpage_url=url,
            formats=formats,
            method="scraped",
        )

    def _scrape_media_urls(self, content: str, *, base: str) -> list[str]:
        """Pull playable media URLs out of raw HTML.

        Order of trust: explicit metadata / ``<source>`` tags first (declared for
        playback), then a broad media-extension sweep over the slash-unescaped
        page so inline-JSON streams (``https:\\/\\/…\\.mp4``) surface too. Deduped,
        capped at ``max_formats``; downstream validation drops any HTML decoys.
        """
        limit = self._settings.max_formats
        found: list[str] = []

        def add(raw: str, *, require_media_ext: bool) -> None:
            cleaned = unescape(raw.replace("\\/", "/")).strip().strip("\"'<>")
            if not cleaned.lower().startswith(("http://", "https://")):
                return
            if require_media_ext and not _MEDIA_EXT_HINT.search(cleaned.split("#")[0]):
                return
            if cleaned not in found:
                found.append(cleaned)

        # 1) Trusted selectors — keep even without a media extension.
        for pattern in (*_META_VIDEO_PATTERNS, _SOURCE_SRC_PATTERN, _JSONLD_URL_PATTERN):
            for match in pattern.findall(content):
                add(match, require_media_ext=False)
                if len(found) >= limit:
                    return found[:limit]

        # 2) Broad sweep over slash-unescaped content — media extension required.
        unescaped = content.replace("\\/", "/")
        for pattern in _SCRAPE_PATTERNS:
            for match in pattern.findall(unescaped):
                add(match, require_media_ext=True)
                if len(found) >= limit:
                    return found[:limit]

        return found[:limit]

    @staticmethod
    def _scrape_first(content: str, pattern: re.Pattern[str]) -> str | None:
        match = pattern.search(content)
        return unescape(match.group(1)).strip() if match else None

    @classmethod
    def _scrape_title(cls, content: str) -> str | None:
        title = cls._scrape_first(content, _OG_TITLE_PATTERN) or cls._scrape_first(
            content, _TITLE_PATTERN
        )
        return title[:200] if title else None
