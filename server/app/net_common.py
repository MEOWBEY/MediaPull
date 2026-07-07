"""Shared network helpers: cookie normalization and browser impersonation.

Used by both `Extractor` (yt-dlp) and `GalleryExtractor` (gallery-dl) so the
two extraction engines share one cookie/anti-bot implementation instead of
diverging.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

logger = logging.getLogger("directstream.net_common")


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
