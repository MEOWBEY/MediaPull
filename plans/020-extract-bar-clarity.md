# Plan 020: Extract bar clarity (content type + hero + batch)

> **Drift check:** `git diff --stat 86a449a..HEAD -- client/src/lib/components/InputUrl.svelte client/src/routes/+page.svelte client/src/lib/i18n/dictionaries.ts`

## Status

- **Priority:** P1  
- **Effort:** S–M  
- **Risk:** LOW  
- **Depends on:** none  
- **Category:** ux  
- **Planned at:** `86a449a`, 2026-07-16  

## Why this matters

Default extraction is **auto**, but the UI that explained auto is commented out, and video/gallery switches only appear after the user finds “manual” mode in Settings. First-run users don’t know whether they’re extracting video or images. Hero subtitle is also commented out, so the page lacks a one-line product explanation.

## Current state

- `InputUrl.svelte`: Auto badge block commented (~148–154); manual toggles only if `contentTypeMode !== 'auto'`.
- Content type mode is also set in Preferences (~376+).
- `+page.svelte`: hero subtitle commented.
- Batch: single-line input + `urlCount` hint.

## Scope

**In scope:**

- `InputUrl.svelte`
- `+page.svelte` (hero only)
- `dictionaries.ts` (EN + FA) if new strings needed

**Out of scope:** Changing auto extract algorithm (already done server/client).

## Steps

### Step 1: Always show content-type control on the extract bar

Three-way control on the action row (not only in prefs):

- **Auto** | **Video** | **Gallery**

Selecting one calls `appStore.updatePreferences({ contentTypeMode })`.

Keep prefs control in sync (same store) — do not invent a second state.

Visual: pill group like current video/gallery, add Auto with Sparkles icon (import already commented).

**Verify:** Default load shows Auto selected; switching to Gallery changes placeholder to gallery copy.

### Step 2: Un-comment / restore hero subtitle

Restore the hero `<p>` with `t('hero.subtitle')` under the title. If copy is stale, update EN+FA to match current product (video **and** galleries + optional subtitles).

**Verify:** Subtitle visible on first paint.

### Step 3: Batch paste affordance

- Change input to `textarea` with `rows={1}` that expands (or keep input but add “Paste multiple URLs” helper that opens a small multiline field).
- Prefer: single-line default; when paste contains newlines, expand to 3-row textarea and keep batch hint.

**Verify:** Pasting two URLs on two lines shows batch count ≥ 2 and extract runs both.

### Step 4: Check

`cd client && npm run check && npm run lint`

## Done criteria

1. Content type always visible and stored in preferences.  
2. Hero explains product.  
3. Multi-URL paste is obvious.  
4. Typecheck clean.

## STOP conditions

- Don’t break RTL: use logical properties (`ps`/`pe`/`ms`/`me`) already used in the file.
