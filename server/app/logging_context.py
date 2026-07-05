"""Per-request context (client IP, user agent) attached to every log line.

Set once per request by the middleware in ``main.py``; read back by
``RequestContextFilter`` so every logger under the root — extractor, proxy,
main — gets it for free, with no per-call-site changes.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

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
