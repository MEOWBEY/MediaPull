# Plan 019: Fix preferences structure (missing section headers + dead compact)

> **Executor:** Follow step by step. Verify after each step. Do not improvise past STOP conditions.  
> **Drift check:** `git diff --stat 86a449a..HEAD -- client/src/lib/components/PreferencesDialog.svelte client/src/lib/components/VideoCard.svelte client/src/lib/components/Instructions.svelte client/src/lib/i18n/dictionaries.ts`

## Status

- **Priority:** P1  
- **Effort:** S  
- **Risk:** LOW  
- **Depends on:** none  
- **Category:** bug / ux  
- **Planned at:** `86a449a`, 2026-07-16  

## Why this matters

The preferences sheet defines four groups (Interface, Playback, Proxy, Captions) with titles and icons, but the template **never renders those titles**. Users only see an unlabeled grid of toggles. Also `enableCompact` barely changes anything, which makes the setting feel broken.

## Current state

- `PreferencesDialog.svelte` ~39–124: `sections` array with `titleKey`, `icon`, `color`, `settings`.
- Loop ~182–221: only inner setting cards — **no** section header using `section.titleKey`.
- Later sections (subtitle panel, cookies, view mode, sorting) **do** have headers — inconsistent.
- `enableCompact`: only Instructions spacing + VideoCard title size.

## Scope

**In scope:**

- `client/src/lib/components/PreferencesDialog.svelte`
- Optionally `VideoCard.svelte` / `Instructions.svelte` if you expand compact slightly
- i18n only if a key is missing (keys already exist as `prefs.section.*`)

**Out of scope:** Full tabs redesign (plan 021); cookies rewrite.

## Steps

### Step 1: Render section headers

For each item in `sections`, mirror the pattern used by “View mode” / “Sorting”:

```svelte
<section class="bg-card rounded-lg border">
  <div class="border-border/60 border-b p-3">
    <h4 class="flex items-center gap-2 text-base font-semibold">
      <section.icon class="h-4 w-4 {section.color}" />
      {t(section.titleKey)}
    </h4>
  </div>
  <div class="p-3 sm:p-4">
    <!-- existing settings grid -->
  </div>
</section>
```

**Verify:** Open Settings in UI (or read file) — each group shows a titled header.

### Step 2: Remove redundant Info button noise (optional but recommended)

Each setting already shows `descKey` as body text under the label. The tiny Info button only repeats `title={desc}`. Remove the Info button to reduce clutter, **or** keep one of: body text XOR tooltip — not both.

**Verify:** No duplicate description UI.

### Step 3: Make Compact meaningful or remove

Pick one:

- **A (preferred):** Apply `enableCompact` to result grids (tighter gaps, smaller quality chips, less padding on `SourceGroupCard` / extract lists) via a single class on workspace root from `+page.svelte` e.g. `data-compact={preferences.enableCompact}`.
- **B:** Remove the toggle and related i18n if product doesn’t want compact.

Document choice in NOTES.

**Verify:** Toggling Compact visibly changes result density, or toggle is gone.

### Step 4: Lint / check

```bash
cd client && npm run check && npm run lint
```

## Done criteria

1. All four `sections` show visible titles + icons.  
2. No unlabeled toggle wall.  
3. Compact is real or removed.  
4. `npm run check` clean.

## STOP conditions

- If i18n keys `prefs.section.interface` etc. are missing for FA locale — add FA strings before finishing, don’t leave EN-only keys.

## Test plan

Manual: open Settings on desktop + mobile width; screenshot sections. No automated component tests required unless harness already covers prefs.
