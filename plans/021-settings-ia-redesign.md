# Plan 021: Settings information architecture redesign

> **Drift check:** open `PreferencesDialog.svelte` + `CookiesPanel.svelte` fully before editing.  
> Prefer landing **after** plan 019 (headers exist) so you restructure a corrected base.

## Status

- **Priority:** P1  
- **Effort:** M  
- **Risk:** MED  
- **Depends on:** 019 recommended  
- **Category:** ux / design  
- **Planned at:** `86a449a`, 2026-07-16  

## Why this matters

Settings is the densest UI: playback, proxy, captions, cookies, layout, sort, content type, reset, wipe library — all in one scrolling sheet. On mobile height is ~65vh. Cookies (critical for Instagram/etc.) compete with “preload metadata”. Users miss important controls.

## Design target

Use **horizontal tabs** (desktop) / **segmented control** (mobile) with 4 panels:

| Tab | Contents |
|-----|----------|
| **General** | Language, theme (system/light/dark), animations, compact, content type mode |
| **Library** | Layout grid/list, sort field/order, clear library (with confirm) |
| **Playback** | Mute, preload, video-only formats, HLS download button, proxy default, captions auto-open, min words |
| **Cookies** | Existing `CookiesPanel` only (+ short tip linking failed extract → cookies) |

Destructive actions (reset prefs / clear all) go at the bottom of **Library** or a fifth **Danger** footer, always behind confirm.

## Scope

**In scope:**

- `PreferencesDialog.svelte` (major restructure)
- `CookiesPanel.svelte` (only if props/layout need tweak)
- i18n keys for tab labels EN+FA

**Out of scope:** Changing cookie storage format; server cookie files.

## Steps

### Step 1: Tab state

```ts
type PrefsTab = 'general' | 'library' | 'playback' | 'cookies';
let tab = $state<PrefsTab>('general');
```

Render tab list with `role="tablist"` / `role="tab"` / `aria-selected`.

### Step 2: Move existing controls into tabs

Do **not** invent new preference keys. Only regroup existing ones. Ensure `contentTypeMode` lives in General (and stays synced with InputUrl from plan 020).

### Step 3: Confirm before clear

`clearAllData` currently wipes immediately. Add a confirm step (inline “Are you sure?” or `window.confirm` is acceptable; prefer in-sheet two-step).

### Step 4: Mobile height

Increase bottom sheet to `h-[85vh]` or `max-h-[90dvh]` so Cookies is usable.

### Step 5: Verify

- Every previous setting still exists and still persists via `appStore.updatePreferences`.
- `npm run check`.

## Done criteria

1. Settings has ≤4 primary tabs.  
2. Cookies is its own tab, one click from Settings open.  
3. Clear library requires confirmation.  
4. No preference key regressions.

## STOP conditions

- Don’t split Cookies into a separate route unless product asks — stay sheet-based.
- Don’t remove EN/FA strings for settings you still show.
