# Plan 016: Single durable storage + extract performance

> **Drift check**: `git diff --stat 86a449a..HEAD -- client/src/lib/cache.ts client/src/lib/stores/library.svelte.ts client/src/lib/extraction.svelte.ts server/app/extractor.py client/src/lib/api/client.ts`

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: perf
- **Planned at**: commit `86a449a`, 2026-07-16

## Why this matters

Extract results are dual-persisted (extract cache + library). Format validation
probes every URL. Auto mode runs full video extract then full gallery.

## Scope

**In scope**:
- `client/src/lib/cache.ts` / `extraction.svelte.ts` — memory-only extract cache
  OR stop `persistKey` for gallery/video extract (library remains durable)
- `client/src/lib/stores/library.svelte.ts` — on load, re-mint ctok for hosts
  with cookies when proxied URLs present (UX-02 partial)
- `server/app/extractor.py` — validate only top N formats (e.g. 8) by preference
  score / resolution; setting `validate_max_formats`
- `client/src/lib/extraction.svelte.ts` — auto mode: heuristic host/path for
  gallery-first OR race video+gallery with AbortController (prefer: try
  lightweight host heuristics for known gallery sites; else keep sequential but
  shorten by skipping validation on failed video path if already failing early)

**Out of scope**: server auto endpoint redesign

## Steps

### Step 1: Stop double localStorage

Remove `persistKey` from extract caches so only `library` persists results.
Clear old keys `cache:extract` / `cache:extract-gallery` once on load.

### Step 2: Library token refresh

When hydrating library items, for each video/gallery with cookies for host,
re-call token mint and rebuild proxied URLs (reuse existing proxy-token helpers).
If mint fails, set a soft flag / toast “links may need refresh”.

### Step 3: Cap format validation

In `_validate_formats`, sort preferred formats first, probe only first N unique
URLs (config default 8). Unprobed formats stay included (same as uncertain probe).

### Step 4: Auto-mode heuristic

If URL path/host matches common gallery patterns (instagram.com/p/, /reel/ only
if you know video is preferred — be careful: reels are video). Safer heuristic:
`pinterest.`, `imgur.com/a/`, `flickr.com`, path contains `/gallery` → gallery
first. Otherwise video first as today.

## Done criteria

1. One durable store for results
2. validate_max_formats wired
3. Some gallery hosts skip failed video path
4. Library re-mints tokens when cookies exist
5. Client check/tests pass where applicable

## STOP conditions

- Do not delete library persistence entirely.
