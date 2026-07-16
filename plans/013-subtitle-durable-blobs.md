# Plan 013: Durable VTT/SRT blob URLs for generated subtitles

> **Drift check**: `git diff --stat 86a449a..HEAD -- client/src/lib/subtitle-utils.ts client/src/lib/subtitle-resolver.svelte.ts client/src/lib/transcribe.svelte.ts client/src/lib/components/VideoPlayer.svelte client/tests/`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `86a449a`, 2026-07-16

## Why this matters

Server `/transcribe/{id}/subtitle.*` dies with job TTL. Restore rebuilds VTT
from segments but leaves `srtUrl` pointing at a dead server URL. Download .srt
breaks after expiry/refresh.

## Current state

- `segmentsToVttUrl` in `subtitle-utils.ts`
- `subtitle-resolver.svelte.ts` `restore` only rewrites `vttUrl`
- `transcribe.svelte.ts` keeps server URLs on done
- VideoPlayer uses `srtUrl` for download

## Scope

**In scope**:
- `client/src/lib/subtitle-utils.ts` — add `segmentsToSrt` / `segmentsToSrtUrl`
- `client/src/lib/subtitle-resolver.svelte.ts`
- `client/src/lib/transcribe.svelte.ts`
- `client/tests/subtitle-utils.test.ts` (create)
- Optionally `VideoPlayer.svelte` if download gate needs `segments.length`

**Out of scope**: server job TTL changes, waveform/dialogue-map UI

## Steps

### Step 1: SRT serialization

Mirror VTT helpers. SRT uses comma for millis and `-->` lines:

```
1
00:00:01,000 --> 00:00:02,000
Hello
```

`segmentsToSrtUrl(segments)` → blob URL with `text/srt` or `application/x-subrip`.

### Step 2: On generate complete and restore

When a track has segments, set:
- `vttUrl: segmentsToVttUrl(segments)`
- `srtUrl: segmentsToSrtUrl(segments)`

Do this in `restore` and when transcription marks done (in
`transcribe.svelte.ts` after segments are available).

### Step 3: Tests

Round-trip: segments → srt text contains expected cues.

## Done criteria

1. restore + generate both produce durable blob SRT and VTT
2. Download works offline of server job
3. vitest for new helpers passes

## STOP conditions

- If segments are empty on done path, keep server URLs as fallback — document in NOTES.
