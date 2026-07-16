# Plan 022: Results workspace chrome (hierarchy + mobile nav)

> **Drift check:** `+page.svelte`, `VideoExtractList.svelte`, `GalleryExtractList.svelte`, `+layout.svelte`

## Status

- **Priority:** P2  
- **Effort:** M  
- **Risk:** LOW–MED  
- **Depends on:** 020 nice-to-have  
- **Category:** ux / layout  
- **Planned at:** `86a449a`, 2026-07-16  

## Why this matters

After extract, users live in a long scroll of cards. There is little section hierarchy, sort/filter lives only in Settings, and the jump-to-input control is **desktop-only**. Hero input scrolls away; no sticky command bar.

## Scope

**In scope:**

- `client/src/routes/+page.svelte`
- Extract list headers inside `VideoExtractList` / `GalleryExtractList` (or shared wrapper)
- FAB / sticky bar behavior
- Optional: collapse Instructions after first result

**Out of scope:** Redesigning VideoPlayer internals (plan 024).

## Steps

### Step 1: Section headers for results

When videos exist, show a sticky-ish section header:

- Title: `t('extract.heading')` or existing key  
- Count badge  
- Optional: quick sort chips that call `updatePreferences` (same keys as prefs)

Same for galleries.

### Step 2: Mobile jump control

Change FAB from `hidden sm:flex` to always visible when `hasResults` (maybe smaller on mobile). Ensure it doesn’t cover bottom sheet handles — use `bottom-20` on small screens if needed.

### Step 3: Sticky extract mini-bar (when results exist)

When `hasResults`, shrink hero padding and pin a compact bar under the header:

- URL field (compact height)  
- Extract button  
- Settings gear  

Implementation options (pick simplest that works):

- CSS `sticky top-0 z-30` on the InputUrl wrapper when results exist, **or**
- Conditionally render a second compact InputUrl in sticky position.

Avoid two independent input states — one `inputUrl` source of truth (lift state to `+page` if needed).

### Step 4: Instructions progressive disclosure

- Empty library: show full Instructions.  
- Has results: collapse to a “How it works” disclosure (`<details>`) or hide entirely.

### Step 5: Check + manual mobile pass

`npm run check`. Manual: phone width, 5+ cards, jump button + sticky extract.

## Done criteria

1. Clear Videos / Galleries sections with counts.  
2. Mobile can return to input without scrolling to top by hand.  
3. Instructions don’t dominate post-success layout.  
4. Typecheck clean.

## STOP conditions

- Sticky bar must not break RTL or cover the video player controls permanently.
