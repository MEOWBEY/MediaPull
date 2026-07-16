# Plan 014: Gallery error classification, image cap, cookies via ctok, warnings

> **Drift check**: `git diff --stat 86a449a..HEAD -- server/app/gallery.py server/app/models.py server/app/serializers.py server/app/config.py client/src/lib/ client/src/lib/components/GalleryExtractList.svelte server/tests/`

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: 011 preferred first (strip Cookie on wire) but can land together
- **Category**: bug / perf / product
- **Planned at**: commit `86a449a`, 2026-07-16

## Why this matters

Gallery failures with partial stdout look like “no images”. Large albums
unbounded. Images only get Referer headers so session CDNs fail. Quality
degradation never reaches the UI (`KNOWN_ISSUES.md`).

## Current state

- `gallery.py:123-135` fails only when `returncode != 0 and not stdout.strip()`
- No max images; full list returned
- Headers forced to `{"Referer": url}` only
- Client `resolveGalleryCookieTokens` needs Cookie in httpHeaders to mint

## Scope

**In scope**:
- `server/app/gallery.py`
- `server/app/models.py` — warnings field, truncated flag, max images config
- `server/app/config.py` — `gallery_max_images` default e.g. 200
- `server/app/serializers.py`
- `client/src/lib/types.ts`, `transform.ts`, `extraction.svelte.ts`,
  `GalleryExtractList.svelte`, dictionaries if needed
- `server/tests/test_gallery.py` (create)

**Out of scope**: bulk zip download (plan 018), full architecture split

## Steps

### Step 1: Error classification

If `returncode != 0` OR (zero images after parse):
- Prefer `classify_extraction_error` / gallery-specific needles on stderr
- Use `_GENERIC_GALLERY_MESSAGE` when generic
- Only raise “No images found” when returncode == 0 and valid empty/successful dump

### Step 2: Cap images

After parse, if len(images) > max: truncate, set `truncated=True` /
`omitted_count=N` on GalleryInfo. Surface in client toast.

### Step 3: Attach cookies for CDN

When extract used `cookie_text` or pool cookie file contents, set Cookie on
each image’s http_headers **before** serialize. Plan 011 will strip Cookie
from the JSON — **order matters**:

**Better approach** (compatible with 011):
- Mint is client-side today. So either:
  A) Keep Cookie in headers only long enough for client mint then strip — but
     011 strips on server before response, so mint dies.
  B) **Preferred**: server returns `needs_cookies: true` or attaches cookies
     only as a **separate** field the client already has (user Settings cookies
     for that host). Client already has cookies in `cookies.svelte` — on
     gallery transform, call `resolveGalleryCookieTokens` using **Settings
     cookies for the gallery host**, not extract response Cookie.

Implement **B**: in client gallery transform path, for each image, if user has
cookies for that host, mint ctok and put on proxied URL (same as video).
Server gallery continues Referer-only; document that CDN auth uses Settings cookies.

If Settings cookies empty but server used COOKIE_FILE pool, server-side
operator cookies still won't reach the browser (correct for multi-tenant).
Optional: mint server-side `ctok` for pool cookies and return `ctok` per
image or gallery-level — more invasive. **Minimum for this plan is client
Settings cookies → ctok for gallery images** + better errors + cap + warnings.

### Step 4: Warnings

Parse stderr for phrases like `login`, `rate`, `403`, `watermark`, `lower`
(case-insensitive). Return `warnings: list[{code, message}]` on gallery
response. Client toast + banner in GalleryExtractList.

### Step 5: Tests

- Nonzero returncode + stdout → classified error not “no images”
- Truncation at max
- Warning extraction from sample stderr string

## Done criteria

1. Gallery errors more accurate
2. Max images enforced + client informed
3. Gallery images use Settings cookies → ctok when available
4. Warnings surface in UI
5. Tests pass

## STOP conditions

- Do not re-introduce raw cookies into shareable image proxy URLs.
