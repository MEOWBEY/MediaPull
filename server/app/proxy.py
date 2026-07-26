"""Streaming reverse-proxy for media URLs.

It:
  * forwards the Range header so the player can seek (passes 206 through),
  * rewrites HLS playlists so nested playlists/segments keep flowing through
    this proxy (carrying the same UA/Referer/Cookie),
  * otherwise streams bytes through with the source's content headers,
  * injects Referer/Cookie/User-Agent the player can't set itself.

Requests go out through **curl_cffi with browser impersonation** so anti-bot
CDNs that gate on the TLS/HTTP fingerprint actually serve the bytes.
Falls back to plain requests if curl_cffi/impersonation is unavailable.

Byte streams are marked ``Content-Encoding: identity`` so the app's global
GZip middleware leaves them (and their Content-Length/Range) untouched.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import socket
import time
import uuid
from urllib.parse import quote, urlencode, urljoin, urlparse

from curl_cffi.requests import AsyncSession
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .config import Settings
from .net_common import impersonate_kwarg
from .ssrf import is_blocked_ip

logger = logging.getLogger("mediapull.proxy")

# Upstream response headers worth forwarding to the player.
_FORWARD_RESP_HEADERS = (
    "content-type",
    "content-length",
    "content-range",
    "accept-ranges",
    "content-disposition",
    "content-encoding",
)
_HLS_CONTENT_TYPE = "application/vnd.apple.mpegurl"
# Real HLS playlists are a few KB. The cap only exists so a crafted
# protocol=m3u8_native request pointing at a huge file can't buffer it
# all into memory (playlists must be read fully to be rewritten).
_MAX_PLAYLIST_BYTES = 5 * 1024 * 1024
_URI_ATTR = re.compile(r'URI="([^"]+)"')
_IS_PLAYLIST = re.compile(r"\.m3u8(\?|$)", re.IGNORECASE)
# Strip control chars and quotes (header injection), path separators (save-name
# spoofing into another directory), ';' (Content-Disposition parameter
# smuggling), and '%' (pre-encoded sequences in the RFC 5987 filename* value)
# from a client-supplied filename.
_UNSAFE_FILENAME = re.compile(r'[\x00-\x1f"\\/;%]+')


def _safe_header_value(value: str) -> str:
    """Strip CR/LF/NUL so query/token-derived values cannot smuggle headers."""
    return value.replace("\r", "").replace("\n", "").replace("\0", "")[:4096]


def _download_filename(q) -> str:
    """Sanitized filename for the forced-download ``Content-Disposition``, from
    the ``?filename=`` query param (falls back to a generic name)."""
    raw = (q.get("filename") or "video").strip()
    cleaned = _UNSAFE_FILENAME.sub("", raw)[:200]
    return cleaned or "video"


class ProxyService:
    # Cap on redirects we follow by hand (each hop re-runs the SSRF guard).
    _MAX_REDIRECTS = 5

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._default_ua = settings.user_agent
        self._impersonate_kw = impersonate_kwarg(settings)
        self._proxy = settings.proxy_url or None
        self._session = AsyncSession(
            timeout=15,
            max_clients=50,
            proxies={"http": self._proxy, "https": self._proxy} if self._proxy else None,
        )
        self._allowed_hosts = settings.proxy_allowed_hosts
        self._enabled = settings.proxy_enabled
        # Ephemeral token -> (cookie_blob, expiry_monotonic). Keeps a source's
        # auth cookies OUT of the proxy URL (URLs get copied / QR'd / shared);
        # the token is opaque and short-lived (~1h). Cap size with
        # PROXY_COOKIE_TOKEN_MAX. Single-worker only — tokens live in this
        # process dict (same constraint as JobStore / TTLCache).
        self._cookie_tokens: dict[str, tuple[str, float]] = {}
        self._token_ttl = 3600.0
        # Short-lived cache of the *DNS* verdict (hostname -> (allowed, expiry)).
        # An HLS stream fans out into one proxied request per segment, all on the
        # same CDN host, so without this every segment re-runs a blocking
        # getaddrinfo for a name the OS resolver already has cached. Only the
        # resolve-and-judge step is cached; the allow-list / IP-literal guard
        # (_check_host) still runs live on every call. The TTL is deliberately
        # short so a rebind can't be exploited for longer than one window.
        self._dns_verdict_cache: dict[str, tuple[bool, float]] = {}
        self._dns_ttl = 30.0
        self._dns_cache_max = 512

    async def aclose(self) -> None:
        await self._session.close()

    # ----- ephemeral cookie tokens -------------------------------------

    def create_cookie_token(self, cookies: str) -> str:
        """Store *cookies* under a fresh opaque token and return the token."""
        self._sweep_tokens()
        max_tokens = self._settings.proxy_cookie_token_max
        if len(self._cookie_tokens) >= max_tokens:
            # Evict soonest-expiring entries until there is room.
            by_exp = sorted(self._cookie_tokens.items(), key=lambda kv: kv[1][1])
            overflow = len(self._cookie_tokens) - max_tokens + 1
            for tok, _ in by_exp[:overflow]:
                self._cookie_tokens.pop(tok, None)
        token = uuid.uuid4().hex
        self._cookie_tokens[token] = (cookies, time.monotonic() + self._token_ttl)
        return token

    def resolve_cookie_token(self, token: str) -> str:
        """Public resolve for transcription unwrap and other server-side paths."""
        return self._resolve_cookie_token(token)

    def _resolve_cookie_token(self, token: str) -> str:
        entry = self._cookie_tokens.get(token)
        if entry is None:
            return ""
        cookies, expiry = entry
        if time.monotonic() > expiry:
            self._cookie_tokens.pop(token, None)
            return ""
        return cookies

    def _sweep_tokens(self) -> None:
        now = time.monotonic()
        for tok in [t for t, (_, exp) in self._cookie_tokens.items() if now > exp]:
            self._cookie_tokens.pop(tok, None)

    # ----- SSRF guards --------------------------------------------------

    def _check_host(self, url: str) -> bool:
        """True if this destination's *hostname* is allowed. String-level guard
        only — IP-literal ranges and the config allow-list. DNS names are
        resolved and re-checked in ``_resolve_and_check``."""
        try:
            hostname = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        if not hostname:
            return False
        if hostname == "localhost" or is_blocked_ip(hostname):
            return False
        if self._allowed_hosts:
            # Suffix match: "googlevideo.com" matches "r1---sn-abc.googlevideo.com"
            return any(
                hostname == allowed or hostname.endswith("." + allowed)
                for allowed in self._allowed_hosts
            )
        return True

    async def _resolve_and_check(self, url: str) -> bool:
        """Re-run ``_check_host``, then resolve the hostname and reject if ANY
        resolved address is a blocked (internal) IP — kills DNS rebinding. The
        DNS lookup is blocking, so it runs in the default executor.

        The allow-list / IP-literal guard (``_check_host``) is evaluated live on
        every call; only the *resolution* verdict is cached (short TTL), so the
        repeated per-HLS-segment lookups of one CDN host collapse to one."""
        if not self._check_host(url):
            return False
        hostname = (urlparse(url).hostname or "").lower()
        # An IP literal was already fully judged by _check_host.
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            pass

        now = time.monotonic()
        cached = self._dns_verdict_cache.get(hostname)
        if cached is not None and cached[1] > now:
            return cached[0]

        loop = asyncio.get_running_loop()
        try:
            infos = await loop.run_in_executor(None, socket.getaddrinfo, hostname, None)
            verdict = not any(is_blocked_ip(str(info[4][0])) for info in infos)
        except socket.gaierror:
            # Can't resolve -> reject rather than silently allow. Not cached: a
            # transient resolver failure shouldn't pin a host to "blocked".
            return False
        self._remember_dns_verdict(hostname, verdict, now)
        return verdict

    def _remember_dns_verdict(self, hostname: str, verdict: bool, now: float) -> None:
        """Store a resolution verdict with a short expiry, evicting the oldest
        entry when the cache is full (simple FIFO — entries are short-lived and
        the working set is tiny, so LRU bookkeeping isn't worth it)."""
        if len(self._dns_verdict_cache) >= self._dns_cache_max:
            # Drop everything already expired; if none are, drop the oldest.
            expired = [h for h, (_, exp) in self._dns_verdict_cache.items() if exp <= now]
            for h in expired:
                self._dns_verdict_cache.pop(h, None)
            if len(self._dns_verdict_cache) >= self._dns_cache_max:
                oldest = min(self._dns_verdict_cache, key=lambda h: self._dns_verdict_cache[h][1])
                self._dns_verdict_cache.pop(oldest, None)
        self._dns_verdict_cache[hostname] = (verdict, now + self._dns_ttl)

    async def _get_checked(self, url: str, *, stream: bool, headers: dict[str, str]):
        """Like ``session.get(..., allow_redirects=True)`` but follows redirects
        by hand and re-runs the SSRF guard on EVERY hop. Returns the final
        curl_cffi response, or raises ``PermissionError`` if a hop targets a
        disallowed host / the redirect chain is malformed or too long."""
        current = url
        for _ in range(self._MAX_REDIRECTS):
            if not await self._resolve_and_check(current):
                raise PermissionError(current)
            resp = await self._session.get(
                current,
                headers=headers,
                allow_redirects=False,
                stream=stream,
                **self._impersonate_kw,
            )
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                await resp.aclose()
                if not location:
                    raise PermissionError(current)
                current = urljoin(current, location)
                continue
            return resp
        raise PermissionError(current)

    async def handle(self, request: Request) -> Response:
        if not self._enabled:
            return JSONResponse(
                {"error": "Proxy is disabled on this server (PROXY_ENABLED=false)"},
                status_code=503,
            )
        q = request.query_params
        source = q.get("url")
        protocol = q.get("protocol") or ""

        if not source or not protocol:
            return JSONResponse({"error": "Missing url or protocol"}, status_code=400)

        try:
            source_scheme = (urlparse(source).scheme or "").lower()
        except ValueError:
            source_scheme = ""
        if source_scheme not in ("http", "https"):
            return JSONResponse(
                {"error": "Only http and https URLs can be proxied"},
                status_code=400,
            )

        if not self._check_host(source):
            return JSONResponse(
                {"error": "Proxying to this host is not allowed"},
                status_code=403,
            )

        referer = q.get("referer") or ""
        # Cookies never travel in the URL — the client exchanges them for an
        # opaque token via POST /proxy-token and passes the token here.
        ctok = q.get("ctok") or ""
        cookies = self._resolve_cookie_token(ctok) if ctok else ""

        upstream_headers: dict[str, str] = {}
        # When impersonating, let curl_cffi set the User-Agent that matches the
        # TLS fingerprint — a UA that disagrees re-triggers the 403 we're dodging.
        if not self._impersonate_kw:
            upstream_headers["User-Agent"] = _safe_header_value(
                q.get("userAgent") or self._default_ua
            )
        if referer:
            upstream_headers["Referer"] = _safe_header_value(referer)
        if cookies:
            upstream_headers["Cookie"] = _safe_header_value(cookies)
        range_header = request.headers.get("range")
        if range_header:
            upstream_headers["Range"] = _safe_header_value(range_header)

        if protocol == "m3u8_native":
            return await self._handle_playlist(request, source, upstream_headers, q)

        # ?download=1 turns the response into a forced file save (attachment)
        # instead of something the browser plays inline. Without this, a
        # cross-origin proxied URL makes the download link just navigate to and
        # stream the video in a tab — `download` is ignored cross-origin but
        # Content-Disposition is honored everywhere.
        download_name = _download_filename(q) if q.get("download") else None
        return await self._handle_stream(
            request, source, upstream_headers, download_name=download_name
        )

    # ----- HLS playlist -------------------------------------------------

    async def _handle_playlist(
        self, request: Request, source: str, headers: dict[str, str], q
    ) -> Response:
        try:
            resp = await self._get_checked(source, stream=True, headers=headers)
        except PermissionError:
            logger.warning("playlist proxy blocked a disallowed redirect target")
            return JSONResponse(
                {"error": "Proxying to this host is not allowed"}, status_code=403
            )
        except Exception as exc:  # noqa: BLE001 - keep transport details out of the response
            logger.warning("playlist proxy request failed for %s: %s", source, exc)
            return JSONResponse({"error": "Upstream request failed"}, status_code=502)

        if resp.status_code >= 400:
            status = resp.status_code
            logger.warning("playlist proxy upstream %s returned %s", source, status)
            await resp.aclose()
            return JSONResponse({"error": f"Upstream error: {status}"}, status_code=status)

        # Read the playlist with a hard size cap -- it must be fully buffered
        # to be rewritten, and nothing stops a request from pointing
        # protocol=m3u8_native at an arbitrarily large file.
        body = bytearray()
        try:
            async for chunk in resp.aiter_content(chunk_size=65536):
                body.extend(chunk)
                if len(body) > _MAX_PLAYLIST_BYTES:
                    logger.warning("playlist from %s exceeded the size cap", source)
                    return JSONResponse(
                        {"error": "Playlist is too large to proxy"}, status_code=502
                    )
        except Exception as exc:  # noqa: BLE001 - keep transport details out of the response
            logger.warning("playlist proxy read failed for %s: %s", source, exc)
            return JSONResponse({"error": "Upstream request failed"}, status_code=502)
        finally:
            await resp.aclose()

        passthrough: dict[str, str] = {}
        if q.get("userAgent"):
            passthrough["userAgent"] = q["userAgent"]
        if q.get("referer"):
            passthrough["referer"] = q["referer"]
        # Carry the opaque cookie token (never the raw cookies) into every
        # rewritten segment/playlist URL.
        if q.get("ctok"):
            passthrough["ctok"] = q["ctok"]

        self_base = f"{request.url.scheme}://{request.url.netloc}{request.url.path}"
        playlist = _rewrite_hls(
            body.decode("utf-8", errors="replace"), source, self_base, passthrough
        )

        return Response(
            content=playlist,
            status_code=200,
            headers={
                "Content-Type": _HLS_CONTENT_TYPE,
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache",
            },
        )

    # ----- byte stream (segments + progressive files) ------------------

    async def _handle_stream(
        self,
        request: Request,
        source: str,
        headers: dict[str, str],
        *,
        download_name: str | None = None,
    ) -> Response:
        try:
            upstream = await self._get_checked(source, stream=True, headers=headers)
        except PermissionError:
            logger.warning("stream proxy blocked a disallowed redirect target")
            return JSONResponse(
                {"error": "Proxying to this host is not allowed"}, status_code=403
            )
        except Exception as exc:  # noqa: BLE001 - keep transport details out of the response
            logger.warning("stream proxy request failed for %s: %s", source, exc)
            return JSONResponse({"error": "Upstream request failed"}, status_code=502)

        if upstream.status_code >= 400:
            status = upstream.status_code
            logger.warning("stream proxy upstream %s returned %s", source, status)
            await upstream.aclose()
            return JSONResponse({"error": f"Upstream error: {status}"}, status_code=status)

        # curl_cffi transparently decompresses the body, so `aiter_content()`
        # below yields DECODED bytes. That makes the upstream Content-Encoding
        # and (compressed) Content-Length lies about what we actually stream --
        # forwarding them would make the browser try to gunzip already-plain
        # text (YouTube/Vimeo gzip their timedtext captions), fail with a
        # decode error, and show an empty track. So never forward the upstream
        # transfer encoding: drop it here and re-assert identity below. When the
        # upstream was compressed, its Content-Length is the compressed size and
        # is now wrong too, so drop that as well and let the response stream
        # unsized (chunked). Uncompressed responses keep their real length so
        # Range/seek stays intact for video.
        upstream_encoded = (
            upstream.headers.get("content-encoding", "").lower() not in ("", "identity")
        )
        drop = {"content-encoding"}
        if upstream_encoded:
            drop.add("content-length")
        out_headers = {
            k: v
            for k, v in upstream.headers.items()
            if k.lower() in _FORWARD_RESP_HEADERS and k.lower() not in drop
        }
        out_headers["Access-Control-Allow-Origin"] = "*"
        out_headers.setdefault("Accept-Ranges", "bytes")
        # Body is always identity by the time it reaches the browser (see above);
        # this also keeps the app's GZip middleware off media.
        out_headers["Content-Encoding"] = "identity"
        if download_name:
            ascii_name = download_name.encode("ascii", "ignore").decode() or "video"
            out_headers["Content-Disposition"] = (
                f'attachment; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(download_name)}"
            )

        async def body():
            # Stop pulling from the origin the instant the browser disconnects.
            # A 64 KiB read granularity keeps per-chunk overhead (and the
            # disconnect check below) low relative to the bytes moved.
            try:
                async for chunk in upstream.aiter_content(chunk_size=65536):
                    if await request.is_disconnected():
                        break
                    yield chunk
            finally:
                await upstream.aclose()

        return StreamingResponse(
            body(), status_code=upstream.status_code, headers=out_headers
        )


def _rewrite_hls(
    playlist: str, source_url: str, self_base: str, passthrough: dict[str, str]
) -> str:
    """Rewrite playlist URIs so nested playlists/segments route back here.

    Nested ``.m3u8`` references stay playlists (rewritten in turn); everything
    else (segments, keys) streams as bytes.
    """

    def to_proxied(raw_uri: str) -> str | None:
        try:
            abs_url = urljoin(source_url, raw_uri)
        except ValueError:
            return None
        is_playlist = bool(_IS_PLAYLIST.search(abs_url.split("#")[0]))
        params = dict(passthrough)
        params["protocol"] = "m3u8_native" if is_playlist else "segment"
        params["url"] = abs_url
        return f"{self_base}?{urlencode(params)}"

    out: list[str] = []
    for line in playlist.replace("\r\n", "\n").split("\n"):
        trimmed = line.strip()
        if not trimmed:
            out.append(line)
            continue

        if trimmed.startswith("#") and "URI=" in line:
            proxied = None
            m = _URI_ATTR.search(line)
            if m:
                proxied = to_proxied(m.group(1))
            if proxied:
                out.append(_URI_ATTR.sub(f'URI="{proxied}"', line))
            else:
                out.append(line)
        elif not trimmed.startswith("#"):
            out.append(to_proxied(trimmed) or line)
        else:
            out.append(line)

    return "\n".join(out)