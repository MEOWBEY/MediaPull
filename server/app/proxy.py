"""Streaming reverse-proxy for media URLs.

It:
  * forwards the Range header so the player can seek (passes 206 through),
  * rewrites HLS playlists so nested playlists/segments keep flowing through
    this proxy (carrying the same UA/Referer/Cookie),
  * otherwise streams bytes through with the source's content headers,
  * injects Referer/Cookie/User-Agent the player can't set itself.

Requests go out through **curl_cffi with browser impersonation** so anti-bot
CDNs (pornhub, spankbang, …) that gate on the TLS/HTTP fingerprint actually
serve the bytes — extraction succeeding doesn't help if playback then 403s.
Falls back to plain requests if curl_cffi/impersonation is unavailable.

Byte streams are marked `Content-Encoding: identity` so the app's global GZip
middleware leaves them (and their Content-Length/Range) untouched.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlencode, urljoin

from curl_cffi.requests import AsyncSession
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .config import Settings

logger = logging.getLogger("directstream.proxy")

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


class ProxyService:
    def __init__(self, settings: Settings) -> None:
        self._default_ua = settings.user_agent
        # Browser fingerprint to impersonate (e.g. "chrome"); empty disables it.
        self._impersonate = (
            settings.impersonate_client if settings.enable_impersonation else ""
        )
        # Same outbound proxy as extraction, so media leaves the box from the
        # same egress IP that resolved the link (avoids signed-URL/IP mismatches).
        self._proxy = settings.proxy_url or None
        # No read timeout: media streams stay open for the whole download.
        self._session = AsyncSession(
            timeout=15,
            max_clients=50,
            proxies={"http": self._proxy, "https": self._proxy} if self._proxy else None,
        )

    async def aclose(self) -> None:
        await self._session.close()

    def _request_kwargs(self, headers: dict[str, str]) -> dict:
        kwargs: dict = {"headers": headers, "allow_redirects": True}
        if self._impersonate:
            kwargs["impersonate"] = self._impersonate
        return kwargs

    async def handle(self, request: Request) -> Response:
        q = request.query_params
        source = q.get("url")
        protocol = q.get("protocol") or ""

        if not source or not protocol:
            return JSONResponse({"error": "Missing url or protocol"}, status_code=400)

        referer = q.get("referer") or ""
        cookies = q.get("cookies") or ""

        upstream_headers: dict[str, str] = {}
        # When impersonating, let curl_cffi set the User-Agent that matches the
        # TLS fingerprint — a UA that disagrees re-triggers the 403 we're dodging.
        if not self._impersonate:
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

        return await self._handle_stream(source, upstream_headers)

    # ----- HLS playlist -------------------------------------------------

    async def _handle_playlist(
        self, request: Request, source: str, headers: dict[str, str], q
    ) -> Response:
        try:
            resp = await self._session.get(source, **self._request_kwargs(headers))
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
        if q.get("cookies"):
            passthrough["cookies"] = q["cookies"]

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

    async def _handle_stream(self, source: str, headers: dict[str, str]) -> Response:
        try:
            upstream = await self._session.get(
                source, stream=True, **self._request_kwargs(headers)
            )
        except Exception as exc:  # noqa: BLE001 - surface any transport error
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

        async def body():
            try:
                async for chunk in upstream.aiter_content():
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
    else (segments, keys) is streamed as bytes.
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
    for line in playlist.split("\n"):
        trimmed = line.strip()
        if not trimmed:
            out.append(line)
            continue

        # Rewrite URI="..." attributes inside tags (#EXT-X-KEY, media renditions).
        if trimmed.startswith("#"):
            def repl(m: re.Match[str]) -> str:
                proxied = to_proxied(m.group(1))
                return f'URI="{proxied}"' if proxied else m.group(0)

            out.append(_URI_ATTR.sub(repl, line))
        else:
            out.append(to_proxied(trimmed) or line)

    return "\n".join(out)
