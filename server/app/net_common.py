"""Shared network helpers: cookie normalization and browser impersonation.

Used by both `Extractor` (yt-dlp) and `GalleryExtractor` (gallery-dl) so the
two extraction engines share one cookie/anti-bot implementation instead of
diverging.
"""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
import threading
import time
from urllib.parse import urlparse

from .config import Settings

logger = logging.getLogger("mediapull.net_common")


class CookiePool:
    """Round-robin over the server-side cookie files (``COOKIE_FILE`` may
    hold several comma-separated paths, e.g. two Instagram accounts).

    Requests spread across the accounts, and when a site answers one of them
    with a rate-limit / bot-flag / login-wall the caller reports it here --
    that file goes on cooldown while the others keep serving, then rejoins
    the rotation automatically. Mirrors the Groq key pool's behavior, but
    thread-safe (both extraction engines run in thread pools, not the event
    loop) and time-based only: a cookie account recovers, a revoked API key
    doesn't.
    """

    # How long a rate-limited / bot-flagged account sits out (5 min). Kept in
    # code (not env) — short enough to recover, long enough to stop thrashing.
    _COOLDOWN_SECONDS = 300.0

    def __init__(self, paths: list[str]) -> None:
        self._paths = [p for p in paths if p]
        self._cooldown_until: dict[str, float] = {}
        self._rr = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._paths)

    def pick(self) -> str | None:
        """Next cookie file to use, skipping ones on cooldown. When every
        file is cooling, returns the one that frees up soonest -- stale
        cookies still beat no cookies on login-gated sites."""
        with self._lock:
            if not self._paths:
                return None
            now = time.monotonic()
            available = [p for p in self._paths if self._cooldown_until.get(p, 0.0) <= now]
            if not available:
                return min(self._paths, key=lambda p: self._cooldown_until.get(p, 0.0))
            self._rr += 1
            return available[self._rr % len(available)]

    def report_block(self, path: str) -> None:
        """A site rejected this file's session (429/403/401) -- rest it."""
        with self._lock:
            if path not in self._paths:
                return
            self._cooldown_until[path] = time.monotonic() + self._COOLDOWN_SECONDS
        logger.warning(
            "cookie file %s hit a block, cooling it down %.0fs and rotating",
            os.path.basename(path),
            self._COOLDOWN_SECONDS,
        )


# One pool per COOKIE_FILE value, shared by yt-dlp and gallery-dl so a
# cooldown earned through either engine protects the account from both.
_cookie_pools: dict[str, CookiePool] = {}
_cookie_pools_lock = threading.Lock()


def get_cookie_pool(settings: Settings) -> CookiePool:
    with _cookie_pools_lock:
        pool = _cookie_pools.get(settings.cookie_file)
        if pool is None:
            pool = _cookie_pools[settings.cookie_file] = CookiePool(settings.cookie_files)
        return pool


@contextlib.contextmanager
def cookie_tempfile(cookie_text: str | None):
    """Write ``cookie_text`` to a throwaway Netscape cookies.txt file for the
    duration of one extractor call, and remove it afterward.

    Shared by ``Extractor`` and ``GalleryExtractor`` so the write/cleanup dance
    (and any fix to it, e.g. logging a failed unlink) only has to be made once.
    Yields ``None`` when there's no cookie text, so callers can always use
    ``with cookie_tempfile(text) as path:`` regardless of whether cookies were
    supplied.
    """
    if not cookie_text:
        yield None
        return

    handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
    try:
        handle.write(cookie_text)
    finally:
        handle.close()
    path = handle.name
    try:
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError as exc:
            # Leftover cookie files hold session tokens, so a failed cleanup is
            # worth knowing about even though it isn't fatal to the request.
            logger.warning("failed to remove cookie temp file %s: %s", path, exc)


def impersonate_kwarg(settings: Settings) -> dict:
    """``{"impersonate": <client>}`` when browser impersonation is enabled and
    configured, else ``{}`` -- the curl_cffi kwarg shared by the extractor's
    format-probe session, the media proxy, and the transcription pipeline's
    audio download."""
    if settings.enable_impersonation and settings.impersonate_client:
        return {"impersonate": settings.impersonate_client}
    return {}


def build_impersonate(client: str):
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


def normalize_cookies(raw: str, url: str) -> str | None:
    """Coerce user-pasted cookies into Netscape cookies.txt text.

    Accepts either the Netscape/Mozilla export (tab-separated rows, what the
    "Get cookies.txt LOCALLY" extension produces) or a single
    ``Cookie: a=b; c=d`` header line, which we convert to Netscape rows
    scoped to the URL's host. Returns None when there's nothing usable.

    Shared by yt-dlp (``--cookies``/``cookiefile``) and gallery-dl
    (``--cookies``) — both consume the identical Netscape format.
    """
    text = (raw or "").strip()
    if not text:
        return None

    # Netscape/Mozilla format already (rows are tab-separated). Ensure the
    # magic header line is present — MozillaCookieJar refuses files without it.
    # Also guarantee it's on its own line: some exports concat the header
    # directly onto the first row without a separating newline.
    if "\t" in text:
        if not text.lstrip().startswith("#"):
            text = "# Netscape HTTP Cookie File\n" + text
        elif not text.startswith("#"):
            # Header exists but is preceded by whitespace — re-normalize.
            text = "# Netscape HTTP Cookie File\n" + text
        return text

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
