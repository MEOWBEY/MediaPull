"""Per-request context (client IP, user agent) attached to every log line.

Set once per request by the middleware in ``main.py``; read back by
``RequestContextFilter`` so every logger under the root — extractor, proxy,
main — gets it for free, with no per-call-site changes.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

_client_ip: ContextVar[str] = ContextVar("client_ip", default="-")
_user_agent: ContextVar[str] = ContextVar("user_agent", default="-")


def set_request_context(client_ip: str, user_agent: str) -> None:
    _client_ip.set(client_ip or "-")
    _user_agent.set(user_agent or "-")


def client_ip_from_headers(headers, client_host: str | None) -> str:
    """Real client IP behind a reverse proxy (see deploy/) falls back to the
    socket peer when there's no proxy in front (e.g. local dev)."""
    forwarded = headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return client_host or "-"


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.client_ip = _client_ip.get()
        record.user_agent = _user_agent.get()
        return True


class LogContextMiddleware:
    """Pure-ASGI middleware that stamps the per-request log context.

    Deliberately NOT a ``@app.middleware("http")`` / ``BaseHTTPMiddleware``:
    that flavour relays the response through an internal memory stream and
    swallows the ASGI ``http.disconnect`` event, so a ``StreamingResponse``
    (our media proxy) keeps running -- and keeps pulling bytes from the origin
    -- long after the browser cancelled the download or navigated away. A
    plain ASGI middleware forwards ``receive``/``send`` untouched, so disconnect
    propagates and the proxy stream is cancelled the moment the client leaves.
    Context vars set here propagate down to the endpoint (same task/context).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        client_host = scope["client"][0] if scope.get("client") else None
        set_request_context(
            client_ip_from_headers(headers, client_host),
            headers.get("user-agent", "-"),
        )
        await self.app(scope, receive, send)
