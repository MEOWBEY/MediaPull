"""Admin panel backend: auth, log viewer, moderation, env editor, jobs.

All /admin/* routes are gated by a single session cookie (see login()). The
admin account is configured via env (ADMIN_USERNAME + ADMIN_PASSWORD_HASH),
so setup is exactly one extra paragraph in install.sh -- no user table, no
database.

ponytail: everything here is in-process state (sessions, login limiter, log
ring). Single-worker + restart-loses-admin-sessions is the documented app
model, see the WORKERS=1 comments in config.py.
"""

from __future__ import annotations

import asyncio
import collections
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import Settings, settings

logger = logging.getLogger("mediapull.admin")

router = APIRouter(prefix="/admin", tags=["admin"])

# ---------------------------------------------------------------------------
# Password hashing (stdlib PBKDF2 -- no new dependency, bcrypt-class strength)
# ---------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 600_000
_HASH_RE = re.compile(r"^pbkdf2_sha256\$(\d+)\$([0-9a-f]+)\$([0-9a-f]+)$")


def hash_password(password: str, iterations: int = _PBKDF2_ITERATIONS) -> str:
    """Hash a password into the ``pbkdf2_sha256$iterations$salt$digest`` shape
    stored in ADMIN_PASSWORD_HASH. deploy/install.sh uses this same function to
    bake an admin in during install."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    m = _HASH_RE.match(stored or "")
    if not m:
        return False
    iterations = int(m.group(1))
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), m.group(2).encode(), iterations
    )
    return hmac.compare_digest(digest.hex(), m.group(3))


# ---------------------------------------------------------------------------
# Sessions + login rate limiting (in-memory; single process)
# ---------------------------------------------------------------------------

COOKIE_NAME = "mediapull_admin"
_WINDOW_SECONDS = 900  # login attempt window (fixed)

_sessions: dict[str, float] = {}  # token -> expiry (monotonic)
_login_attempts: dict[str, list[float]] = collections.defaultdict(list)

# ponytail: plain-dict limiter; bounded by _SESSIONS_MAX eviction below.
_SESSIONS_MAX = 512


def _request_is_secure(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto", "")
    return request.url.scheme == "https" or "https" in proto.split(",")


def require_admin(request: Request) -> None:
    """FastAPI dependency: 401 unless the request holds a valid admin session."""
    token = request.cookies.get(COOKIE_NAME, "")
    expiry = _sessions.get(token)
    if expiry is None or time.monotonic() > expiry:
        raise HTTPException(status_code=401, detail="Admin session expired or invalid")
    if len(_sessions) > _SESSIONS_MAX:
        now = time.monotonic()
        for tok, exp in [(t, e) for t, e in _sessions.items() if now > e]:
            _sessions.pop(tok, None)


def _login_rate_limit_hit(request: Request) -> bool:
    ip = _client_ip(request)
    now = time.monotonic()
    attempts = [t for t in _login_attempts[ip] if now - t < _WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    return len(attempts) >= max(settings.admin_login_rate_limit, 1)


def record_login_attempt(ip: str, success: bool) -> None:
    if success:
        _login_attempts.pop(ip, None)
        return
    now = time.monotonic()
    attempts = [t for t in _login_attempts[ip] if now - t < _WINDOW_SECONDS]
    attempts.append(now)
    _login_attempts[ip] = attempts


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
async def admin_login(payload: LoginRequest, request: Request) -> dict:
    if not settings.admin_username or not settings.admin_password_hash:
        raise HTTPException(status_code=404, detail="Admin panel is not configured")
    if _login_rate_limit_hit(request):
        raise HTTPException(status_code=429, detail="Too many login attempts, try again later")

    ok = hmac.compare_digest(payload.username, settings.admin_username) and verify_password(
        payload.password, settings.admin_password_hash
    )
    record_login_attempt(_client_ip(request), ok)
    if not ok:
        logger.warning("admin login failed for %r from %s", payload.username, _client_ip(request))
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = secrets.token_urlsafe(32)
    _sessions[token] = time.monotonic() + settings.admin_session_ttl_min * 60
    logger.info("admin login: %s from %s", settings.admin_username, _client_ip(request))

    resp = JSONResponse({"ok": True, "username": settings.admin_username})
    resp.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.admin_session_ttl_min * 60,
        httponly=True,
        samesite="strict",
        secure=_request_is_secure(request),
        path="/",
    )
    return resp


@router.post("/logout")
async def admin_logout(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME, "")
    _sessions.pop(token, None)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@router.get("/me")
async def admin_me(request: Request, _: None = Depends(require_admin)) -> dict:
    return {"ok": True, "username": settings.admin_username, "configured": True}


# ---------------------------------------------------------------------------
# Log ring buffer
# ---------------------------------------------------------------------------


class LogBuffer(logging.Handler):
    """Bounded in-memory log capture; feeds both the filtered viewer and the
    SSE tail. Attached alongside the stream handler in main._configure_logging,
    also to the access/error loggers so request lines appear too."""

    def __init__(self, maxlen: int = 2000) -> None:
        super().__init__()
        self._records: collections.deque[dict] = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._version = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "level": record.levelname,
                "name": record.name,
                "message": record.getMessage(),
                "ip": getattr(record, "client_ip", "-"),
                "req": getattr(record, "request_id", "-"),
            }
            with self._lock:
                self._records.append(entry)
                self._version += 1
        except Exception:  # noqa: BLE001 - a logging handler must never raise
            pass

    @property
    def version(self) -> int:
        return self._version

    def recent(
        self,
        *,
        level: str | None = None,
        q: str | None = None,
        source: str | None = None,
        limit: int = 200,
        before: int | None = None,
    ) -> list[dict]:
        with self._lock:
            items = list(self._records)
        levels = {lvl.strip().upper() for lvl in level.split(",")} if level else set()
        out = []
        for entry in reversed(items):
            if before is not None and entry["ts"] >= before:
                continue
            if levels and entry["level"].upper() not in levels:
                continue
            if source and source not in entry["name"]:
                continue
            if q and q.lower() not in entry["message"].lower():
                continue
            out.append(entry)
            if len(out) >= limit:
                break
        return out


LOG_BUFFER = LogBuffer()


def attach_log_buffer() -> None:
    """Attach the ring buffer to root and the framework access loggers. Called
    from main._configure_logging; idempotent per process."""
    root = logging.getLogger()
    if LOG_BUFFER not in root.handlers:
        root.addHandler(LOG_BUFFER)
    for name in ("uvicorn.access", "uvicorn.error", "gunicorn.access"):
        lg = logging.getLogger(name)
        if LOG_BUFFER not in lg.handlers:
            lg.addHandler(LOG_BUFFER)


# ---------------------------------------------------------------------------
# Moderation: IP ban + blocked domains (JSON state file) + per-IP usage stats
# ---------------------------------------------------------------------------


def _state_path() -> Path:
    path = Path(settings.admin_state_path).expanduser()
    if not path.is_absolute() and not path.exists():
        alt = Path(__file__).resolve().parents[1] / path
        if alt.parent.exists():
            return alt
    return path


def _load_state() -> dict:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _save_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


def banned_ips() -> list[str]:
    return _load_state().get("banned_ips", [])


def blocked_domains() -> list[str]:
    return _load_state().get("blocked_domains", [])


def is_ip_banned(ip: str) -> bool:
    return ip in banned_ips()


def check_url_allowed(url: str) -> str | None:
    """Return a block reason if the URL's host is blocked, else None. Suffix
    match, so blocking ``youtube.com`` also blocks ``m.youtube.com``."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None
    for domain in blocked_domains():
        if host == domain or host.endswith("." + domain):
            return f"This domain is blocked by the server administrator ({domain})"
    return None


class UsageTracker:
    """Bounded in-memory per-IP counters for extract/transcribe starts. Reset
    on restart; used by the admin Overview tab, not for enforcement."""

    def __init__(self, max_ips: int = 4096) -> None:
        self._max_ips = max_ips
        self._hits: dict[str, dict[str, int]] = {}

    def record(self, ip: str, endpoint: str) -> None:
        counts = self._hits.setdefault(ip, {})
        counts[endpoint] = counts.get(endpoint, 0) + 1
        if len(self._hits) > self._max_ips:
            self._hits.pop(next(iter(self._hits)))

    def snapshot(self, limit: int = 20) -> list[dict]:
        rows = [
            {"ip": ip, **counts, "total": sum(counts.values())}
            for ip, counts in self._hits.items()
        ]
        rows.sort(key=lambda r: r["total"], reverse=True)
        return rows[:limit]


USAGE = UsageTracker()


def _client_ip(request: Request) -> str:
    from .logging_context import client_ip_from_headers

    forwarded = request.headers.get("x-forwarded-for", "")
    return client_ip_from_headers(request.headers, None) if forwarded else (request.client.host if request.client else "-")


# ---- per-IP rate limiting for public payload endpoints (rec 1) ------------


class SlidingWindowLimiter:
    """Sliding 60s window per IP. ``max_hits`` 0 disables. In-memory only
    (single-process app); entries evicted when idle."""

    def __init__(self, max_hits: int, window: int = 60, max_ips: int = 8192) -> None:
        self._max_hits = max_hits
        self._window = window
        self._hits: dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
        self._max_ips = max_ips

    def allow(self, ip: str) -> bool:
        if self._max_hits <= 0:
            return True
        now = time.monotonic()
        q = self._hits.setdefault(ip, collections.deque())
        while q and now - q[0] > self._window:
            q.popleft()
        if len(q) >= self._max_hits:
            return False
        q.append(now)
        if len(self._hits) > self._max_ips:
            self._hits.pop(next(iter(self._hits)))
        return True


PAYLOAD_LIMITER = SlidingWindowLimiter(settings.payload_rate_limit)


def payload_rate_guard(request: Request) -> None:
    """FastAPI dependency rate-limiting 429 on /extract-*, /transcribe*,
    /split-audio/* starts and /proxy-token (the cheap path to burn API quota).
    Also feeds the admin Overview usage stats (per-IP attempts)."""
    ip = _client_ip(request)
    USAGE.record(ip, request.url.path.rstrip("/").rsplit("/", 1)[-1] or request.url.path)
    if not PAYLOAD_LIMITER.allow(ip):
        logger.warning("rate limit hit from %s on %s", ip, request.url.path)
        raise HTTPException(status_code=429, detail="Too many requests, slow down")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class AdminGuardMiddleware:
    """Pure-ASGI guard that 403s banned client IPs before any handler runs.
    Owns no response buffering (same rationale as LogContextMiddleware) and
    computes the IP itself, so it doesn't depend on middleware order."""

    def __init__(self, app: object) -> None:
        from starlette.types import ASGIApp

        self.app: ASGIApp = app

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        from starlette.datastructures import Headers

        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        client_host = scope["client"][0] if scope.get("client") else None
        ip = client_ip_from_request(headers.get("x-forwarded-for"), client_host)
        if is_ip_banned(ip):
            response = JSONResponse(
                status_code=403,
                content={"success": False, "error": "Your IP is blocked by the server administrator"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def client_ip_from_request(forwarded: str | None, client_host: str | None = None) -> str:
    """Same resolution as logging_context.client_ip_from_headers, without the
    middleware dependency."""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return client_host or "-"


@router.get("/overview")
async def admin_overview(request: Request, _: None = Depends(require_admin)) -> dict:
    pending = 0
    try:
        pending = env_pending_changes()
    except Exception:  # noqa: BLE001 - never break the overview tab
        pass
    return {
        "version": __import__("app.main", fromlist=["__version__"]).__version__,
        "uptimeSeconds": int(time.monotonic()),
        "pendingEnvChanges": pending,
    }


@router.get("/rules")
async def admin_rules(request: Request, _: None = Depends(require_admin)) -> dict:
    return {"bannedIps": banned_ips(), "blockedDomains": blocked_domains()}


class RuleUpdate(BaseModel):
    value: str = Field(min_length=1, max_length=253)


def _validate_ip(value: str) -> str:
    ip = value.strip().lower()
    if not ip:
        raise HTTPException(status_code=422, detail="Empty value")
    return ip


def _validate_domain(value: str) -> str:
    domain = value.strip().lower().lstrip(".")
    if not domain or any(ch.isspace() for ch in domain):
        raise HTTPException(status_code=422, detail="Invalid domain")
    return domain


@router.post("/rules/ips")
async def add_ip_rule(payload: RuleUpdate, request: Request, _: None = Depends(require_admin)) -> dict:
    ip = _validate_ip(payload.value)
    state = _load_state()
    banned = [i for i in state.get("banned_ips", []) if i != ip]
    banned.append(ip)
    state["banned_ips"] = banned
    _save_state(state)
    logger.warning("admin %s banned IP %s", settings.admin_username, ip)
    return {"bannedIps": banned}


@router.delete("/rules/ips")
async def remove_ip_rule(ip: str, request: Request, _: None = Depends(require_admin)) -> dict:
    state = _load_state()
    state["banned_ips"] = [i for i in state.get("banned_ips", []) if i != ip]
    _save_state(state)
    logger.info("admin %s unbanned IP %s", settings.admin_username, ip)
    return {"bannedIps": state["banned_ips"]}


@router.post("/rules/domains")
async def add_domain_rule(payload: RuleUpdate, request: Request, _: None = Depends(require_admin)) -> dict:
    domain = _validate_domain(payload.value)
    state = _load_state()
    blocked = [d for d in state.get("blocked_domains", []) if d != domain]
    blocked.append(domain)
    state["blocked_domains"] = blocked
    _save_state(state)
    logger.warning("admin %s blocked domain %s", settings.admin_username, domain)
    return {"blockedDomains": blocked}


@router.delete("/rules/domains")
async def remove_domain_rule(domain: str, request: Request, _: None = Depends(require_admin)) -> dict:
    state = _load_state()
    state["blocked_domains"] = [d for d in state.get("blocked_domains", []) if d != domain]
    _save_state(state)
    logger.info("admin %s unblocked domain %s", settings.admin_username, domain)
    return {"blockedDomains": state["blocked_domains"]}


@router.get("/usage")
async def admin_usage(request: Request, _: None = Depends(require_admin)) -> dict:
    return {"topIps": USAGE.snapshot(20)}


@router.get("/logs")
async def admin_logs(
    request: Request,
    level: str | None = None,
    q: str | None = None,
    source: str | None = None,
    limit: int = 200,
    before: str | None = None,
    _: None = Depends(require_admin),
) -> dict:
    limit = max(1, min(limit, 1000))
    return {
        "entries": LOG_BUFFER.recent(
            level=level, q=q, source=source, limit=limit, before=before
        ),
        "version": LOG_BUFFER.version,
    }


@router.get("/logs/stream", include_in_schema=False)
async def admin_logs_stream(request: Request, _: None = Depends(require_admin)) -> StreamingResponse:
    """SSE tail of the ring buffer: full snapshot on connect, then new entries
    as they land (rec 4)."""

    async def stream() -> object:
        last_version = 0
        sent_initial = False
        while True:
            if await request.is_disconnected():
                return
            version = LOG_BUFFER.version
            if not sent_initial or version > last_version:
                entries = LOG_BUFFER.recent(limit=500) if not sent_initial else [
                    e for e in reversed(LOG_BUFFER.recent(limit=2000))
                ]
                yield f"data: {json.dumps({'entries': entries, 'version': version})}\n\n"
                last_version = version
                sent_initial = True
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs")
async def admin_jobs(request: Request, _: None = Depends(require_admin)) -> dict:
    transcribe = [
        {
            "type": "transcribe",
            "id": job.id,
            "status": job.status,
            "progress": job.progress,
            "stepLabel": job.step_label,
            "detail": job.detail,
            "error": job.error,
            "ageSeconds": int(time.monotonic() - job.created_at),
            "ip": getattr(job, "client_ip", "-"),
        }
        for job in (await request.app.state.jobs.all())
    ]
    split = [
        {
            "type": "split-audio",
            "id": job.id,
            "status": job.status,
            "progress": job.progress,
            "stepLabel": job.step_label,
            "error": job.error,
            "ageSeconds": int(time.monotonic() - job.created_at),
            "ip": getattr(job, "client_ip", "-"),
        }
        for job in (await request.app.state.split_audio.all())
    ]
    return {"jobs": transcribe + split}


@router.get("/jobs/stream", include_in_schema=False)
async def admin_jobs_stream(request: Request, _: None = Depends(require_admin)) -> StreamingResponse:
    """SSE snapshot every 2s -- the panel refreshes as jobs complete without
    its own polling loop (rec 5)."""

    async def stream() -> object:
        while True:
            if await request.is_disconnected():
                return
            try:
                jobs = (await request.app.state.jobs.all()) + (await request.app.state.split_audio.all())
                yield f"data: {json.dumps({'count': len(jobs)})}\n\n"
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(2)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/jobs/{job_type}/{job_id}/cancel")
async def admin_cancel_job(job_type: str, job_id: str, request: Request, _: None = Depends(require_admin)) -> dict:
    if job_type == "transcribe":
        ok = await request.app.state.jobs.cancel(job_id)
    elif job_type == "split-audio":
        ok = await request.app.state.split_audio.cancel(job_id)
    else:
        raise HTTPException(status_code=422, detail="Unknown job type")
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown or finished job")
    logger.warning("admin %s cancelled %s job %s", settings.admin_username, job_type, job_id)
    return {"cancelled": True}


@router.post("/cache/purge")
async def admin_cache_purge(request: Request, _: None = Depends(require_admin)) -> dict:
    await request.app.state.cache.clear()
    await request.app.state.gallery_cache.clear()
    logger.info("admin %s purged extract caches", settings.admin_username)
    return {"purged": True}


# ---------------------------------------------------------------------------
# Env editor  (Part 2 + rec 3 backup)
# ---------------------------------------------------------------------------

_SECRET_RE = re.compile(r"(KEY|TOKEN|PASSWORD|SECRET|_HASH|PROXY_URL)", re.I)
# Extra human help for keys whose purpose isn't obvious from the name. The
# pydantic field comments in config.py are the source docs; this is only the
# short teaser for the editor UI. (ponytail: curated, not exhaustive)
ENV_HELP: dict[str, str] = {
    "WORKERS": "Must stay 1 — job/store state is in-process only.",
    "DEBUG": "Enables uvicorn reload + access logs. Leave false in production.",
    "CORS_ORIGINS": "Allowed browser origins; '*' disables credentialed CORS.",
    "CLIENT_DIR": "Path to the built client to serve on this origin (empty = auto-detect).",
    "ADMIN_PASSWORD_HASH": "PBKDF2 hash of the admin password (pbkdf2_sha256$...). Set by install.sh.",
    "GROQ_API_KEY": "Whisper API key(s) for auto-subtitles, comma-separated. Empty disables /transcribe.",
    "COOKIE_FILE_PATHS": "Netscape cookies.txt path(s), comma-separated; used when a request brings no cookies.",
    "TRANSCRIBE_ENABLED": "Master switch for the subtitle endpoints.",
    "MEDIA_MAX_SOURCE_BYTES": "Single cap on every media source the server accepts.",
    "PROXY_ALLOWED_HOSTS": "Destination host allow-list for the media proxy (empty = any public host).",
    "YOUTUBE_POT_BASE_URL": "PO-token provider base URL (auto-detects 127.0.0.1:4416 when blank).",
}


def _env_file_path() -> Path:
    p = Path(settings.model_config.get("env_file", ".env"))
    if p.is_absolute():
        return p
    cwd_cand = Path.cwd() / p
    if cwd_cand.exists():
        return cwd_cand
    repo_cand = Path(__file__).resolve().parents[1] / p
    return repo_cand


def parse_env(text: str) -> list[dict]:
    """Line-preserving parse: comments and blanks survive round-trips."""
    entries: list[dict] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            entries.append({"key": None, "value": None, "line": line})
            continue
        key, _, value = stripped.partition("=")
        entries.append({"key": key.strip(), "value": value.strip(), "line": line})
    return entries


def render_env(entries: list[dict]) -> str:
    return "\n".join(e["line"] for e in entries) + ("\n" if entries else "")


def read_env() -> list[dict]:
    path = _env_file_path()
    if not path.exists():
        return []
    return parse_env(path.read_text(encoding="utf-8"))


def apply_env_updates(updates: dict[str, str | None]) -> dict:
    """Rewrite the .env file with the given key=value set (None = remove).
    Backs up the previous file first (rec 3). Returns {written: {...}}."""
    path = _env_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(f".env.bak-{int(time.time())}")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    entries = read_env() if path.exists() else parse_env("")
    for key, value in updates.items():
        if value is None:
            entries = [e for e in entries if e["key"] != key]
            continue
        found = next((e for e in entries if e["key"] == key), None)
        if found is not None:
            found["line"] = f"{key}={value}"
        else:
            entries.append({"key": key, "value": value, "line": f"{key}={value}"})
    path.write_text(render_env(entries), encoding="utf-8")
    return {"written": {k: v for k, v in updates.items() if v is not None}}


def _schema_for(key: str) -> dict:
    # model_json_schema keys properties by ALIAS in some pydantic versions and
    # by field name in others — probe both before falling back to {}.
    props = Settings.model_json_schema().get("properties", {})
    if key in props:
        return props[key]
    for fname, info in Settings.model_fields.items():
        if (info.alias or fname.upper()) == key:
            return props.get(fname, {})
    return {}


def _coerce(key: str, raw: str, schema: dict) -> tuple[bool, str]:
    stype = schema.get("type")
    if stype == "boolean":
        if str(raw).strip().lower() in ("true", "1", "yes", "on"):
            return True, raw
        if str(raw).strip().lower() in ("false", "0", "no", "off", ""):
            return True, raw
        return False, "must be true/false"
    if stype == "integer":
        try:
            val = int(str(raw).strip())
        except ValueError:
            return False, "must be an integer"
        if "minimum" in schema and val < schema["minimum"]:
            return False, f"must be >= {schema['minimum']}"
        if "maximum" in schema and val > schema["maximum"]:
            return False, f"must be <= {schema['maximum']}"
        return True, str(val)
    if stype == "number":
        try:
            return True, str(float(str(raw).strip()))
        except ValueError:
            return False, "must be a number"
    return True, raw


def env_safety_warnings(updates: dict[str, str | None]) -> list[dict]:
    """Cross-field risk checks (plan: warn BEFORE apply)."""
    warnings: list[dict] = []
    merged = {**{e["key"]: e["value"] for e in read_env() if e["key"]}, **updates}
    for key in ("WORKERS", "DEBUG", "CORS_ORIGINS", "TRANSCRIBE_ENABLED", "GROQ_API_KEY", "PORT", "HOST", "PAYLOAD_RATE_LIMIT"):
        if key not in updates:
            continue
        value = merged.get(key, "")
        w_type = "warn"
        message = ""
        if key == "WORKERS" and value not in ("", "1", "1 ", "1"):
            pass
        if key == "WORKERS" and str(value).strip() != "1" and str(value).strip():
            w_type, message = "warn", "Must stay 1 — job/store state is in-process only; >1 will break jobs."
        elif key == "DEBUG" and str(value).strip().lower() in ("true", "1", "yes", "on"):
            w_type, message = "warn", "Debug mode on a public deploy enables reload/access noise; usually unwanted."
        elif key == "CORS_ORIGINS" and "*" in str(value):
            w_type, message = "warn", "'*' disables credentialed CORS — browser cookie flows (admin panel, per-request cookies) will fail."
        elif key == "TRANSCRIBE_ENABLED" and str(value).strip().lower() in ("true", "1", "yes", "on") and not merged.get("GROQ_API_KEY"):
            w_type, message = "info", "transcribe is enabled but no GROQ_API_KEY is set — /transcribe will 503."
        elif key == "GROQ_API_KEY" and (not value or not str(value).strip()) and str(merged.get("TRANSCRIBE_ENABLED", "true")).lower() in ("true", "1", "yes", "on"):
            w_type, message = "warn", "Removing GROQ_API_KEY disables auto-subtitles."
        elif key == "PORT":
            w_type, message = "info", "The systemd unit (not this file) binds the port on VPS installs — edit it there too."
        elif key == "HOST" and str(value).strip() not in ("", "0.0.0.0"):
            w_type, message = "info", "Host is set via this file; the systemd unit binds 127.0.0.1 explicitly."
        elif key == "PAYLOAD_RATE_LIMIT" and str(value).strip() == "0":
            w_type, message = "info", "0 disables the per-IP payload rate limit."
        if message:
            warnings.append({"key": key, "type": w_type, "message": message})
    return warnings


def env_pending_changes() -> int:
    """Count keys where the file differs from the running process."""
    running: dict[str, str] = {}
    for fname, info in Settings.model_fields.items():
        if info.alias:
            val = getattr(settings, fname)
            running[info.alias] = "" if val is None else str(val)
    try:
        file_vals = {e["key"]: e["value"] or "" for e in read_env() if e["key"]}
    except Exception:  # noqa: BLE001
        return 0
    return sum(1 for k, v in running.items() if k in file_vals and file_vals[k] != v)


@router.get("/env")
async def admin_env(request: Request, _: None = Depends(require_admin)) -> dict:
    file_vals = {e["key"]: e["value"] or "" for e in read_env() if e["key"]}
    running: dict[str, str] = {}
    for fname, info in Settings.model_fields.items():
        if info.alias:
            val = getattr(settings, fname)
            running[info.alias] = "" if val is None else str(val)
    keys = []
    for alias in sorted(set(file_vals) | set(running)):
        schema = _schema_for(alias)
        keys.append(
            {
                "key": alias,
                "value": file_vals.get(alias, ""),
                "running": running.get(alias),
                "secret": bool(_SECRET_RE.search(alias)),
                "type": schema.get("type", "string"),
                "min": schema.get("minimum"),
                "max": schema.get("maximum"),
                "default": schema.get("default"),
                "help": ENV_HELP.get(alias),
                "changed": file_vals.get(alias) != running.get(alias),
            }
        )
    return {"keys": keys}


class EnvPreviewRequest(BaseModel):
    updates: dict[str, str | None]


@router.post("/env/preview")
async def admin_env_preview(payload: EnvPreviewRequest, request: Request, _: None = Depends(require_admin)) -> dict:
    """Validate the candidate values + cross-field warnings. No write."""
    errors: list[dict] = []
    for key, value in payload.updates.items():
        if value is None:
            continue
        schema = _schema_for(key)
        if not schema:
            errors.append({"key": key, "type": "error", "message": "Unknown setting"})
            continue
        ok, msg = _coerce(key, value, schema)
        if not ok:
            errors.append({"key": key, "type": "error", "message": msg})
    warnings = env_safety_warnings(payload.updates)
    return {"errors": errors, "warnings": warnings}


class EnvApplyRequest(BaseModel):
    updates: dict[str, str | None]


@router.post("/env/apply")
async def admin_env_apply(payload: EnvApplyRequest, request: Request, _: None = Depends(require_admin)) -> dict:
    result = apply_env_updates(payload.updates)
    logger.warning(
        "admin %s applied env changes: %s",
        settings.admin_username,
        ", ".join(result["written"]),
    )
    return result


@router.post("/restart")
async def admin_restart(request: Request, _: None = Depends(require_admin)) -> dict:
    """Restart the service so env changes take effect. Requires systemd (VPS
    install provides a polkit rule for the mediapull user; on Windows/dev this
    returns unsupported and the operator restarts manually)."""
    if os.name == "nt":
        return {"restarted": False, "reason": "unsupported", "detail": "Restart MediaPull manually to apply changes."}
    try:
        proc = subprocess.run(
            ["systemctl", "restart", "mediapull"],
            capture_output=True, text=True, timeout=30,
        )
        ok = proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        ok = False
        proc = None
    if ok:
        logger.warning("admin %s restarted the service from the panel", settings.admin_username)
    return {
        "restarted": ok,
        "reason": "systemd" if (ok or proc is not None) else "unsupported",
        "detail": None if ok else (proc.stderr.strip() if proc is not None else "systemctl not available"),
    }


# ---------------------------------------------------------------------------
# System ops: git status, update, uninstall (VPS installs)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_update_lock = threading.Lock()


def _git(args: list[str], timeout: float = 15.0) -> str | None:
    """Run a git command in the repo root; None on any failure (dev boxes
    without git must not crash the panel)."""
    try:
        proc = subprocess.run(
            ["git", *args], capture_output=True, text=True, timeout=timeout,
            cwd=str(_REPO_ROOT),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _deploy_script(name: str) -> Path:
    return _REPO_ROOT / "deploy" / name


@router.get("/system")
async def admin_system(request: Request, _: None = Depends(require_admin)) -> dict:
    """Version-control status used by the overview's System section: which
    branch runs, how many commits behind origin, and whether the install can
    update/uninstall itself."""
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    dirty = False
    behind: int | None = None
    if branch:
        dirty = bool(_git(["status", "--porcelain"]))
        if _git(["fetch", "origin", "--quiet"], timeout=20.0) is not None:
            count = _git(["rev-list", "--count", f"HEAD..origin/{branch}"], timeout=10.0)
            behind = int(count) if count and count.isdigit() else None
    return {
        "branch": branch,
        "behind": behind,
        "dirty": dirty,
        "gitAvailable": branch is not None,
        "updateAvailable": os.name != "nt" and _deploy_script("update.sh").is_file(),
        "uninstallAvailable": os.name != "nt" and _deploy_script("uninstall.sh").is_file(),
    }


def _run_deploy_script(script: Path, label: str) -> None:
    """Stream a deploy script's output into the admin log ring so the Logs tab
    becomes the live progress view. Runs on the service user — systemctl calls
    inside go through the polkit rule installed at setup."""
    try:
        proc = subprocess.Popen(
            ["bash", str(script)],
            cwd=str(_REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        for line in proc.stdout or []:
            logger.info("admin %s: %s", label, line.rstrip())
        proc.wait()
        logger.warning(
            "admin %s: %s finished with exit %s",
            settings.admin_username, label, proc.returncode,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("admin %s: %s failed: %s", settings.admin_username, label, exc)
    finally:
        _update_lock.release()


def _start_deploy(script: Path, label: str) -> dict | None:
    """Common gate for update/uninstall: one deploy op at a time, script must
    exist. Returns the 409 payload when refused."""
    if not script.is_file():
        return {"started": False, "detail": f"deploy/{script.name} is not present on this install"}
    if not _update_lock.acquire(blocking=False):
        return {"started": False, "detail": "Another update/uninstall is already running"}
    try:
        threading.Thread(target=_run_deploy_script, args=(script, label), daemon=True).start()
    except Exception:  # noqa: BLE001
        _update_lock.release()
        raise
    return None


@router.post("/update")
async def admin_update(request: Request, _: None = Depends(require_admin)) -> dict:
    if os.name == "nt":
        return {"started": False, "detail": "Updates run on the Linux VPS install (deploy/update.sh)"}
    refused = _start_deploy(_deploy_script("update.sh"), "update")
    if refused is not None:
        return refused
    logger.warning("admin %s started an update from the panel", settings.admin_username)
    return {"started": True, "detail": "Update running — watch the Logs tab"}


class UninstallRequest(BaseModel):
    confirm: str = Field(min_length=1, max_length=64)


@router.post("/uninstall")
async def admin_uninstall(payload: UninstallRequest, request: Request, _: None = Depends(require_admin)) -> dict:
    if payload.confirm.strip().lower() != "uninstall":
        raise HTTPException(status_code=400, detail='Type "uninstall" to confirm')
    refused = _start_deploy(_deploy_script("uninstall.sh"), "uninstall")
    if refused is not None:
        return refused
    logger.warning("admin %s started an UNINSTALL from the panel", settings.admin_username)
    return {"started": True, "detail": "Uninstall running — this removes the service"}


# ---------------------------------------------------------------------------
# Cookie upload page support (session auth accepted alongside ADMIN_TOKEN)
# ---------------------------------------------------------------------------

def admin_authorized(request: Request) -> bool:
    """Session cookie OR the legacy ADMIN_TOKEN bearer — the pre-panel
    curl workflow keeps working unchanged."""
    token = request.cookies.get(COOKIE_NAME, "")
    if token and time.monotonic() <= _sessions.get(token, 0):
        return True
    expected = settings.admin_token
    if not expected:
        return False
    header = request.headers.get("Authorization", "")
    scheme, _, presented = header.partition(" ")
    return scheme.lower() == "bearer" and secrets.compare_digest(presented, expected)


# ---------------------------------------------------------------------------
# Server-side cookie file manager (Netscape cookies.txt)
# ---------------------------------------------------------------------------

NETSCAPE_HEADER = "# Netscape HTTP Cookie File"


def cookie_file_paths() -> list[str]:
    """Resolve COOKIE_FILE_PATHS; falls back to the repo's default
    server/cookies.txt so the panel has something real to show even when the
    setting is empty and install.sh's default file exists."""
    paths = [p.strip() for p in settings.cookie_file_paths_raw.split(",") if p.strip()]
    if not paths:
        default = Path(__file__).resolve().parents[1] / "cookies.txt"
        paths = [str(default)]
    resolved: list[str] = []
    for p in paths:
        path = Path(p).expanduser()
        if not path.is_absolute():
            candidate = Path.cwd() / p
            repo = Path(__file__).resolve().parents[1] / p
            path = candidate if candidate.exists() else (repo if repo.exists() else candidate)
        resolved.append(str(path))
    return resolved


def parse_cookie_file(text: str) -> list[dict]:
    """Parse a Netscape cookies.txt body into entry dicts. Comment/blank lines
    are skipped; malformed rows are ignored (they keep the file untouched)."""
    entries: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split("\t")
        if len(fields) != 7:
            continue
        domain, include_subdomains, path, secure, expires, name, value = fields
        entries.append(
            {
                "domain": domain,
                "includeSubdomains": include_subdomains == "TRUE",
                "path": path,
                "secure": secure == "TRUE",
                "expires": int(expires) if expires.isdigit() else 0,
                "name": name,
                "value": value,
            }
        )
    return entries


def _entry_to_line(e: dict) -> str:
    return "\t".join(
        [
            e["domain"],
            "TRUE" if e.get("includeSubdomains") else "FALSE",
            e["path"] or "/",
            "TRUE" if e.get("secure") else "FALSE",
            str(int(e.get("expires") or 0)),
            e["name"],
            e["value"],
        ]
    )


def cookie_files() -> list[dict]:
    """All configured cookie files with parsed entries and staleness info,
    newest-data-first order."""
    out: list[dict] = []
    for path in cookie_file_paths():
        file_path = Path(path)
        info = {"path": path, "exists": file_path.is_file(), "entries": [], "expiredCount": 0, "modified": None}
        if file_path.is_file():
            info["modified"] = datetime.fromtimestamp(
                file_path.stat().st_mtime, tz=timezone.utc
            ).isoformat(timespec="seconds")
            entries = parse_cookie_file(file_path.read_text(encoding="utf-8"))
            now = int(time.time())
            info["entries"] = entries
            info["expiredCount"] = sum(
                1
                for e in entries
                if e["expires"] and e["expires"] < now
            )
        out.append(info)
    return out


class CookieEntryUpdate(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    domain: str = Field(min_length=1, max_length=253)
    name: str = Field(min_length=1, max_length=253)
    value: str = Field(max_length=8192)
    cookie_path: str = Field(default="/", max_length=1024, alias="cookiePath")
    secure: bool = False
    include_subdomains: bool = Field(default=True, alias="includeSubdomains")
    # UNIX epoch seconds; 0 or null = session cookie (no expiry).
    expires: int | None = Field(default=None, ge=0, le=4102444800)


def _ensure_cookie_file(path: str) -> Path:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not file_path.exists():
        file_path.write_text(NETSCAPE_HEADER + "\n", encoding="utf-8")
    return file_path


def _read_cookie_lines(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("# Netscape"):
        lines = [NETSCAPE_HEADER, *lines]
    return lines


@router.get("/cookies")
async def admin_cookies_list(request: Request, _: None = Depends(require_admin)) -> dict:
    return {"files": cookie_files()}


@router.put("/cookies/entries")
async def admin_cookie_put_entry(
    payload: CookieEntryUpdate, request: Request, _: None = Depends(require_admin)
) -> dict:
    """Add or replace one cookie entry in the given file (atomic rewrite)."""
    if "\n" in payload.value or "\t" in payload.value:
        raise HTTPException(status_code=422, detail="Cookie value must be a single line")
    file_path = _ensure_cookie_file(payload.path)
    lines = _read_cookie_lines(file_path)
    expires = payload.expires or 0
    new_line = _entry_to_line(
        {
            "domain": payload.domain,
            "includeSubdomains": payload.include_subdomains,
            "path": payload.cookie_path,
            "secure": payload.secure,
            "expires": expires,
            "name": payload.name,
            "value": payload.value,
        }
    )
    target = "\t".join([payload.domain, payload.cookie_path, payload.name])
    kept: list[str] = []
    replaced = False
    for line in lines:
        fields = line.split("\t")
        if len(fields) == 7 and "\t".join([fields[0], fields[2], fields[5]]) == target:
            kept.append(new_line)
            replaced = True
        else:
            kept.append(line)
    if not replaced:
        if not lines or lines[-1] != "":
            kept.append("")
        kept.append(new_line)
    tmp = file_path.with_suffix(file_path.suffix + ".tmp")
    tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
    tmp.replace(file_path)
    logger.warning(
        "admin %s %s cookie %s for %s in %s",
        settings.admin_username,
        "updated" if replaced else "added",
        payload.name,
        payload.domain,
        payload.path,
    )
    return {"replaced": replaced, "file": payload.path}


@router.delete("/cookies/entries")
async def admin_cookie_del_entry(
    request: Request,
    path: str,
    domain: str,
    name: str,
    cookie_path: str = "/",
    _: None = Depends(require_admin),
) -> dict:
    """Delete one cookie entry (matched on domain+name+path)."""
    file_path = Path(path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Cookie file not found")
    lines = _read_cookie_lines(file_path)
    target = "\t".join([domain, cookie_path, name])
    kept = [line for line in lines if not (
        len(line.split("\t")) == 7 and "\t".join([line.split("\t")[0], line.split("\t")[2], line.split("\t")[5]]) == target
    )]
    removed = len(kept) != len(lines)
    if not removed:
        raise HTTPException(status_code=404, detail="Cookie entry not found")
    file_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    logger.warning("admin %s removed cookie %s for %s from %s", settings.admin_username, name, domain, path)
    return {"removed": True}