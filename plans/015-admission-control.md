# Plan 015: Admission control for extract, jobs, and cookie tokens

> **Drift check**: `git diff --stat 86a449a..HEAD -- server/app/main.py server/app/jobs.py server/app/proxy.py server/app/config.py server/app/models.py server/tests/`

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: security / perf
- **Planned at**: commit `86a449a`, 2026-07-16

## Why this matters

Public endpoints admit unbounded work: extract thread pools queue forever,
`JobStore.create` always accepts, cookie token map grows without max size.
DoS / Groq burn / OOM risk.

## Scope

**In scope**:
- `server/app/config.py` — new settings with safe defaults
- `server/app/main.py` — extract admission semaphore; transcribe format list max
- `server/app/jobs.py` — max jobs in memory; reject create when full
- `server/app/proxy.py` — max cookie tokens; reject/evict oldest
- `server/app/models.py` — max_length on TranscribeRequest.formats
- tests

**Out of scope**: full API key auth system, reverse-proxy config files (mention in README only)

## Steps

### Step 1: Settings

```python
extract_max_in_flight: int = 8  # total extract+gallery concurrent admissions
transcribe_max_jobs_stored: int = 64
proxy_cookie_token_max: int = 2048
```

Document in `.env.example`.

### Step 2: Extract admission

Async semaphore on `/extract-videos` and `/extract-gallery`. If cannot acquire
immediately (or within short timeout 0), return 503 JSON
`{"success": false, "error": "Server busy, try again"}`.

### Step 3: Job store cap

Before create, if len(jobs) >= max after sweep, raise/return error → main maps to 503.

### Step 4: Token map cap

After sweep, if len >= max, evict soonest-expiring entries until room, or reject
create with error if still full.

### Step 5: TranscribeRequest validation

`formats: list[VideoFormat] = Field(..., max_length=40)` (or settings.max_formats)
`url` max_length=4096 on VideoFormat.

### Step 6: Tests

- Job create rejects when full (set max=1 in test settings)
- Token max eviction
- Format list over max → 422

## Done criteria

Caps enforced; tests pass; defaults generous enough for single-user VPS.

## STOP conditions

- Do not add multi-worker Redis — stay in-memory single-worker design.
