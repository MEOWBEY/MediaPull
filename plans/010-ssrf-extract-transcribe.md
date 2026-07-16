# Plan 010: Shared SSRF guards for extract, gallery, and transcription fetches

> **Executor instructions**: Follow this plan step by step. Run every
> verification. On STOP conditions, stop and report. Reviewer maintains
> `plans/README.md` if you were dispatched by a reviewer.
>
> **Drift check**: `git diff --stat 86a449a..HEAD -- server/app/proxy.py server/app/net_common.py server/app/extractor.py server/app/gallery.py server/app/audio.py server/app/main.py server/app/config.py server/tests/`

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none (can land with or after 009; touch audio carefully if 009 lands first)
- **Category**: security
- **Planned at**: commit `86a449a`, 2026-07-16

## Why this matters

`/proxy-video` re-checks hosts, private IPs, and redirect hops. Extract,
gallery, and transcription media fetch do not. On a public deploy that is an
SSRF path past the hardened proxy.

## Current state

- SSRF helpers live on `ProxyService` in `proxy.py`: `_is_blocked_ip`,
  `_check_host`, `_resolve_and_check`, `_get_checked`.
- `extractor.py` `is_valid_url` only checks http(s) + netloc.
- `audio.py` downloads format URLs after unwrap with no host guard.
- `config.py`: `proxy_allowed_hosts` empty means allow all public hosts (proxy only).

## Commands

| Purpose | Command | Expected |
|---------|---------|----------|
| Tests | `cd server; python -m pytest -q` | all pass |

## Scope

**In scope**:
- `server/app/net_common.py` or new `server/app/ssrf.py` — shared pure helpers
- `server/app/proxy.py` — use shared helpers (thin wrappers OK)
- `server/app/extractor.py` — reject private/blocked targets before network
- `server/app/gallery.py` — same on input URL
- `server/app/audio.py` — check final origin URL after unwrap before fetch
- `server/app/config.py` / `.env.example` — optional `EXTRACT_BLOCK_PRIVATE=true` default True; document `PROXY_ALLOWED_HOSTS` production advice
- `server/tests/test_ssrf.py` or extend `test_proxy.py`

**Out of scope**: rate limiting (plan 014), cookie strip (011)

## Steps

### Step 1: Extract shared SSRF module

Move or re-export:
- `is_blocked_ip(host: str) -> bool` (current `_is_blocked_ip`)
- `hostname_allowed(url, allowed_hosts: list[str]) -> bool` (string-level, same rules as proxy including localhost block)
- `async def resolve_hostname_allowed(url, allowed_hosts) -> bool` (DNS check)
- `def assert_public_http_url(url: str) -> None` raises ValueError if scheme not http(s) or host blocked as IP literal / localhost

Proxy continues to use allow-list from settings; extract/gallery/audio use
**block private + require http(s)** by default, and if `PROXY_ALLOWED_HOSTS` is
set, transcription downloads should also respect it (same as proxy) so
allow-list is consistent for media fetch.

### Step 2: Gate extract + gallery entrypoints

At start of `Extractor.extract` and `GalleryExtractor.extract` (after
`is_valid_url`), call `assert_public_http_url`. On failure raise
`ValueError` or `ExtractionError(..., status=400)`.

### Step 3: Gate audio acquisition URLs

After `_unwrap_proxied`, before ffmpeg/curl fetch, await
`resolve_hostname_allowed` (or sync assert for IP literals + reject private).
On failure raise `AudioError` with a clear message.

Also reject non-http(s) schemes on proxy handle source URL (defense in depth).

### Step 4: Production default documentation

In `server/.env.example` and `server/README.md` (and root README if needed):
state that public deploys should set `PROXY_ALLOWED_HOSTS` to known CDNs.
Do **not** break local dev by hard-requiring allow-list unless a new
`PROXY_REQUIRE_ALLOWLIST` flag defaults false — prefer docs + optional fail-closed flag defaulting false for backward compat. If adding
`PROXY_REQUIRE_ALLOWLIST=true` support, when true and allow-list empty and
proxy enabled → refuse proxy starts or return 503 on proxy.

### Step 5: Tests

- Private IP URL rejected by extract assert
- localhost rejected
- public host allowed
- proxy scheme `file://` rejected if you add scheme check on handle
- DNS rebind tests still pass for proxy

## Done criteria

1. Shared helpers used by proxy + extract + gallery + audio
2. Private/localhost targets cannot be extracted or transcribed
3. Tests cover reject paths
4. pytest green

## STOP conditions

- Breaking legitimate `http://127.0.0.1` lab workflows without a documented
  escape hatch (e.g. `ALLOW_PRIVATE_TARGETS=true` for dev) — add the flag if
  needed rather than hardcoding forever-block without config.

## Maintenance note

New outbound fetch paths must call the shared helpers.
