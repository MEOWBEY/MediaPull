# Plan 018: Dialogue map (rename waveform), bulk gallery zip, pin player

> **Drift check**: `git diff --stat 86a449a..HEAD -- server/app/waveform.py server/app/jobs.py server/app/models.py client/src/ client/package.json`

## Status

- **Priority**: P3
- **Effort**: L
- **Risk**: MED
- **Depends on**: 013 helpful for subtitle panel; 014 helpful for gallery zip
- **Category**: direction / product
- **Planned at**: commit `86a449a`, 2026-07-16

## Why this matters

Server already builds audio peaks for a seek UI; client never shows them.
Filename `waveform` is vague — product language is a **dialogue map** (speech
energy over time for seek). Gallery users need bulk download. Player is on a
beta package — pin exact version for production.

## Rename vocabulary (mandatory)

| Old | New |
|-----|-----|
| `waveform.py` | `dialogue_map.py` |
| `WaveformError` | `DialogueMapError` |
| `extract_peaks_chunks` | keep name or `extract_dialogue_peaks` |
| JSON field `waveform` | `dialogue_map` (wire) with pydantic alias if needed for compat |
| CSS `.ds-waveform*` | `.ds-dialogue-map*` |
| i18n `subtitles.stage.waveform` | `subtitles.stage.dialogueMap` / “Building dialogue map…” |
| job detail `waveform` | `dialogue_map` |

Prefer **breaking rename** with one release note in KNOWN_ISSUES or README —
client and server ship together. If keeping wire compat: accept old key as
alias for one version.

## Scope

**In scope**:
- Rename `server/app/waveform.py` → `dialogue_map.py` and all imports
- Wire client UI: canvas seek overlay using existing CSS (update class names)
- Persist peaks on `SubtitleTrackResult` as `dialogueMap: number[] | null`
- `GalleryExtractList.svelte` — “Download all” client-side zip via fetching
  proxied image URLs (use a small dependency only if necessary; prefer
  dynamic import of `fflate` or native approach — if adding dep, pin it)
- `client/package.json` — pin `@videojs/html` to exact version (drop `^`)

**Out of scope**: architecture split of main.py routers; server-side zip

## Steps

### Step 1: Rename server module + API field

Update jobs, models, main, config comments. Client types + stage labels.

### Step 2: Client dialogue map UI

On track with `dialogueMap` peaks + known duration, render canvas in player
controls area using renamed CSS. Click seeks `currentTime =
(x/width)*duration`. Hide when no peaks.

### Step 3: Bulk zip

Button on gallery results: fetch each visible (or all) image via proxied URL
as blob, zip, download `gallery.zip`. Show progress. Cap concurrent fetches
(e.g. 4). On failure skip + count.

### Step 4: Pin player

`"@videojs/html": "10.0.0-beta.24"` exact (no caret) or whatever current
resolved version is — use exact from package-lock.

## Done criteria

1. No remaining `waveform.py`; dialogue map naming consistent
2. UI shows seekable dialogue map after transcription when peaks exist
3. Gallery bulk zip works for small galleries in manual test notes
4. Player dep exact-pinned
5. check/lint/test pass

## STOP conditions

- If video.js skin DOM cannot host the canvas without breaking a11y — place
  map above the player and document.
- If zip library is heavy, implement sequential single-file download fallback
  only and NOTES it — do not add large unused deps.

## Rejected for this plan

- Full server folder restructure (ARCH-01) — separate future plan; too risky
  to combine with product renames.
