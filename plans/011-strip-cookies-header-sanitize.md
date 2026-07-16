# Plan 011: Strip Cookie from wire responses + sanitize header values

> **Drift check**: `git diff --stat 86a449a..HEAD -- server/app/serializers.py server/app/extractor.py server/app/audio.py server/app/proxy.py server/app/models.py server/tests/`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `86a449a`, 2026-07-16

## Why this matters

Extract JSON can include `http_headers.Cookie` from yt-dlp (including server
`COOKIE_FILE` sessions). Multi-user deploys leak sessions to every browser.
Also, client-controlled header values reach ffmpeg `-headers` and proxy
upstream without CR/LF filtering (header injection).

## Current state

- `serializers.py` `to_client_video` / `to_client_gallery` pass
  `http_headers=fmt.http_headers` unchanged.
- Client strips Cookie only after `/proxy-token` mint in `proxy-token.ts`.
- `audio.py` `_url_input_args` builds `-headers` as `f"{k}: {v}\r\n"`.
- Proxy copies `referer` / `userAgent` query into upstream headers.

## Scope

**In scope**:
- `server/app/serializers.py`
- `server/app/audio.py` (sanitize)
- `server/app/proxy.py` (sanitize query-derived headers)
- `server/tests/test_serializers.py` (create) and/or extend tests

**Out of scope**: ctok minting changes, client strip (leave as defense in depth)

## Steps

### Step 1: Strip Cookie server-side

In serializers (or a small helper):

```python
def _public_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {k: v for k, v in headers.items() if k.lower() != "cookie"}
```

Apply to every format and gallery image on the way out.

**Verify**: unit test: headers with Cookie → client model has no cookie key.

### Step 2: Sanitize header values

Add:

```python
def _safe_header_value(value: str) -> str:
    return value.replace("\r", "").replace("\n", "").replace("\0", "")[:4096]
```

Use on all header values written into ffmpeg `-headers` and proxy upstream
headers (Referer, User-Agent, Cookie from token). Optionally reject header
**names** that are not in an allow-list for ffmpeg path: Referer, User-Agent,
Cookie, Range (case-insensitive).

**Verify**: test that value with `\r\nX-Injected: 1` is stripped of CR/LF.

## Done criteria

1. No Cookie key in serialized extract/gallery responses
2. CR/LF/NUL stripped from outbound header values on audio + proxy paths
3. Tests green

## STOP conditions

- If some client depends on receiving Cookie in JSON to mint tokens — it must
  use the cookies the user pasted (Settings store), not extract response.
  Do not re-add Cookie to JSON.
