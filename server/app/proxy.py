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

logger = logging.getLogger("pullbox.proxy")

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
_URI_ATTR = re.compile(r'URI="([^"]+)"')
_IS_PLAYLIST = re.compile(r"\.m3u8(\?|$)", re.IGNORECASE)
# Strip CR/LF/quotes so a client-supplied filename can't inject response headers.
_UNSAFE_FILENAME = re.compile(r'[\r\n"]+')


def _download_filename(q) -> str:
    """Sanitized filename for the forced-download ``Content-Disposition``, from
    the ``?filename=`` query param (falls back to a generic name)."""
    raw = (q.get("filename") or "video").strip()
    cleaned = _UNSAFE_FILENAME.sub("", raw)[:200]
    return cleaned or "video"


# ---- private-IP guards -------------------------------------------------


def _is_blocked_ip(host: str) -> bool:
    """True when *host* is an IP literal in a range the proxy must never reach.

    Covers loopback, RFC-1918 private, link-local, unique-local (fc00::/7),
    unspecified (0.0.0.0/::), reserved, multicast, and IPv4-mapped IPv6
    (``::ffff:10.0.0.1``). Returns False when *host* is not an IP literal (a
    DNS name) — those are resolved and re-checked in ``_resolve_and_check``.
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    # Unwrap IPv4-mapped IPv6 so ::ffff:127.0.0.1 is judged as 127.0.0.1.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )


class ProxyService:
    # Cap on redirects we follow by hand (each hop re-runs the SSRF guard).
    _MAX_REDIRECTS = 5

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._default_ua = settings.user_agent
        # Use shared impersonation helper (checks enable_impersonation +
        # impersonate_client) instead of duplicating logic locally.
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
        # the token is opaque and short-lived. Single-worker deploy assumed
        # (see the note in main.py's transcribe section).
        self._cookie_tokens: dict[str, tuple[str, float]] = {}
        self._token_ttl = 3600.0

    async def aclose(self) -> None:
        await self._session.close()

    # ----- ephemeral cookie tokens -------------------------------------

    def create_cookie_token(self, cookies: str) -> str:
        """Store *cookies* under a fresh opaque token and return the token."""
        self._sweep_tokens()
        token = uuid.uuid4().hex
        self._cookie_tokens[token] = (cookies, time.monotonic() + self._token_ttl)
        return token

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
        if hostname == "localhost" or _is_blocked_ip(hostname):
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
        DNS lookup is blocking, so it runs in the default executor."""
        if not self._check_host(url):
            return False
        hostname = (urlparse(url).hostname or "").lower()
        # An IP literal was already fully judged by _check_host.
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            pass
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.run_in_executor(None, socket.getaddrinfo, hostname, None)
        except socket.gaierror:
            # Can't resolve -> reject rather than silently allow.
            return False
        return not any(_is_blocked_ip(str(info[4][0])) for info in infos)

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
            upstream_headers["User-Agent"] = q.get("userAgent") or self._default_ua
        if referer:
            upstream_headers["Referer"] = referer
        if cookies:
            upstream_headers["Cookie"] = cookies
        range_header = request.headers.get("range")
        if range_header:
            upstream_headers["Range"] = range_header

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
            resp = await self._get_checked(source, stream=False, headers=headers)
        except PermissionError:
            logger.warning("playlist proxy blocked a disallowed redirect target")
            return JSONResponse(
                {"error": "Proxying to this host is not allowed"}, status_code=403
            )
        except Exception as exc:  # noqa: BLE001 - surface any transport error
            logger.warning("playlist proxy request failed for %s: %s", source, exc)
            return JSONResponse({"error": f"Upstream error: {exc}"}, status_code=502)

        if resp.status_code >= 400:
            logger.warning("playlist proxy upstream %s returned %s", source, resp.status_code)
            return JSONResponse(
                {"error": f"Upstream error: {resp.status_code}"},
                status_code=resp.status_code,
            )

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
        playlist = _rewrite_hls(resp.text, source, self_base, passthrough)

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
        except Exception as exc:
            logger.warning("stream proxy request failed for %s: %s", source, exc)
            return JSONResponse({"error": f"Upstream error: {exc}"}, status_code=502)

        if upstream.status_code >= 400:
            status = upstream.status_code
            logger.warning("stream proxy upstream %s returned %s", source, status)
            await upstream.aclose()
            return JSONResponse({"error": f"Upstream error: {status}"}, status_code=status)

        out_headers = {
            k: v for k, v in upstream.headers.items() if k.lower() in _FORWARD_RESP_HEADERS
        }
        out_headers["Access-Control-Allow-Origin"] = "*"
        out_headers.setdefault("Accept-Ranges", "bytes")
        # Keep GZip middleware off media so Content-Length/Range stay intact.
        out_headers.setdefault("Content-Encoding", "identity")
        if download_name:
            ascii_name = download_name.encode("ascii", "ignore").decode() or "video"
            out_headers["Content-Disposition"] = (
                f'attachment; filename="{ascii_name}"; '
                f"filename*=UTF-8''{quote(download_name)}"
            )

        async def body():
            # Stop pulling from the origin the instant the browser disconnects.
            try:
                async for chunk in upstream.aiter_content():
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