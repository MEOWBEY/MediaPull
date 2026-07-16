# Plan 024: Result card simplification (mobile-first)

> **Drift check:** `VideoCard.svelte`, `SourceGroupCard.svelte`, `GalleryExtractList.svelte`, `app.css` quality styles

## Status

- **Priority:** P3  
- **Effort:** M  
- **Risk:** MED  
- **Depends on:** 022 optional  
- **Category:** ux / design  
- **Planned at:** `86a449a`, 2026-07-16  

## Why this matters

Video cards pack proxy toggle, subtitles, QR, copy, download, quality rails. On small screens this is noisy; first-time users don’t understand Proxy vs direct. Gallery cards improved with download-all but still dense.

## Design target

**Desktop (≥640px):** keep roughly current power layout.  
**Mobile:**  

1. Player  
2. Title + duration  
3. Primary row: **Download best** + **Copy**  
4. Overflow menu (⋯): Proxy on/off, QR, export, remove (if not on group), open subtitles  

Subtitles can stay as a secondary pill if space allows; otherwise put in overflow + keep panel entry.

Proxy: when off, show a subtle warning if playback fails (link to toggle) — don’t force education wall.

## Scope

**In scope:**

- `VideoCard.svelte`  
- Possibly small helpers in `SourceGroupCard`  
- Gallery: collapse per-image action chrome into long-press or single overflow (optional if time)

**Out of scope:** Rewriting VideoPlayer media engine.

## Steps

### Step 1: Introduce overflow menu component

Use existing bits-ui / dropdown if already in project; else a simple disclosure with buttons. Prefer existing `Button` + absolute menu pattern from `QualityMenu` for consistency.

### Step 2: Responsive action layout

```svelte
<!-- sm+: full action row -->
<!-- default: primary + overflow -->
```

Use Tailwind `hidden sm:flex` / `sm:hidden` carefully with RTL.

### Step 3: “Download best” helper

Pick highest resolution non-video-only quality (respect `showVideoOnlyFormats`). Reuse existing download logic.

### Step 4: Proxy label clarity

Rename visible label to short help: “Stream via server” / FA equivalent when space allows; keep icon.

### Step 5: Check + manual mobile

`npm run check`. Thumb-zone test on real phone if available.

## Done criteria

1. Mobile card has fewer than ~4 always-visible actions.  
2. No lost capability (everything still reachable).  
3. Desktop not regressed.  
4. i18n for new strings.

## STOP conditions

- Don’t remove proxy — only re-home the control.  
- Don’t break subtitle generation entry path.
