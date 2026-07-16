# Plan 008: Accessibility fixes for the subtitle panel (visible close, announced progress, cue contrast)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan in
> `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: written against the **working tree** at commit
> `a225b1c` with uncommitted changes applied to
> `client/src/lib/components/SubtitlePanel.svelte`. `git diff a225b1c..HEAD`
> shows nothing — do NOT trust it. Open the file and compare against the
> "Current state" excerpts. On any mismatch, STOP.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-test-baseline.md (for the client test harness; the
  three source edits themselves are independent and could land without tests if
  001 is deferred — see Test plan)
- **Category**: dx / accessibility
- **Planned at**: commit `a225b1c` (+ uncommitted working-tree changes), 2026-07-13

## Why this matters

The subtitle panel (`SubtitlePanel.svelte`) is a primary surface of this app,
and it has three concrete accessibility gaps:

1. **No visible/keyboard-reachable close.** `Sheet.Content` is rendered with
   `hideClose` (`SubtitlePanel.svelte:129`), so the built-in close button is
   suppressed. On the desktop side-sheet there is no visible dismiss affordance
   at all — dismissal relies on Escape or an outside click, which is not
   discoverable and fails users who navigate by visible controls. A
   `closeLabel` is passed but `hideClose` cancels it.
2. **Progress is not announced.** While a subtitle job runs, the progress bar +
   `stepLabel` + percentage (`SubtitlePanel.svelte:215-229`) update visually but
   sit in a plain `<div>` with no `role="status"` / `aria-live`, so screen-reader
   users get no feedback that anything is happening for a minutes-long operation.
3. **Active-cue highlight has weak contrast.** The current line uses
   `data-[active=true]:bg-primary/10` (`SubtitlePanel.svelte:192`) — a 10%-opacity
   tint that is hard to perceive, and the only other cue for "which line is
   playing" is `text-primary`. Low-vision users can lose the playhead line.

All three are small, self-contained edits in one file.

## Current state

`SubtitlePanel.svelte:124-132` (the sheet — `hideClose` is the problem):
```svelte
<Sheet.Root bind:open>
	<Sheet.Content
		side={desktop.matches ? 'right' : 'bottom'}
		closeLabel={t('common.close')}
		hideClose
		class="bg-background z-999999! flex w-full flex-col gap-0 overflow-hidden p-4 sm:max-w-md sm:p-6 {desktop.matches
			? ''
			: 'h-[65vh] rounded-t-3xl'}"
	>
```

`SubtitlePanel.svelte:213-229` (progress region — no live region):
```svelte
						<!-- Progress is status, not a button: a bar + percentage + the
						     pipeline stage, with cancel as its own explicit action. -->
						<div class="w-full max-w-xs space-y-2">
							<div class="bg-muted h-1.5 w-full overflow-hidden rounded-full">
								<div
									class="bg-primary h-full rounded-full transition-[width] duration-300"
									style="width: {Math.round(progress * 100)}%"
								></div>
							</div>
							<div class="text-muted-foreground flex items-center justify-between gap-2 text-xs">
								<span class="inline-flex min-w-0 items-center gap-1.5">
									<Loader2 class="h-3.5 w-3.5 shrink-0 animate-spin" />
									<span class="truncate">{stepLabel || t('subtitles.generating')}</span>
								</span>
								<span class="shrink-0 tabular-nums">{Math.round(progress * 100)}%</span>
							</div>
						</div>
```

`SubtitlePanel.svelte:188-199` (cue rows — weak active highlight):
```svelte
					{#each filteredSegments as seg (seg)}
						<button
							type="button"
							data-active={seg === activeSeg}
							class="hover:bg-muted data-[active=true]:bg-primary/10 data-[active=true]:text-primary flex w-full items-start gap-3 rounded-lg px-3 py-2 text-start transition-colors"
							onclick={() => onSeek(seg.start)}
						>
```

**Repo conventions**:
- Svelte 5 runes (`$props`, `$state`, `$derived`), tabs for indentation, single
  quotes in `<script>`, Tailwind utility classes with logical properties
  (`ps-`, `pe-`, `inset-s-`, `text-start`). Match exactly.
- All user-facing strings go through `t('...')` from `$lib/i18n/index.svelte`;
  the panel already uses keys under `subtitles.panel.*` and `common.close`. Any
  new visible label MUST use an existing key or add one to the dictionary (see
  `client/src/lib/i18n/dictionaries.ts`) — do NOT hardcode English.
- The `ui/sheet` component wraps `bits-ui`; `hideClose` and `closeLabel` are its
  props. Removing `hideClose` restores the library's built-in close button
  (which already has an accessible label via `closeLabel`).
- Buttons already pattern: `variant="outline" size="icon"` + `title` +
  `aria-label` (see the scroll-to-active and download buttons, `:139-161`).

## Commands you will need

| Purpose        | Command                        | Expected on success |
|----------------|--------------------------------|---------------------|
| Frontend tests | `cd client && npm test`        | exit 0, all pass    |
| Typecheck      | `cd client && npm run check`   | exit 0, no errors   |
| Lint           | `cd client && npm run lint`    | exit 0              |

## Scope

**In scope**:
- `client/src/lib/components/SubtitlePanel.svelte` — the three edits below.
- `client/src/lib/i18n/dictionaries.ts` — only if a new string key is needed
  (Step 1 may reuse `common.close`; check first).
- `client/tests/subtitle-panel.test.ts` (create) — optional, see Test plan.
- `plans/README.md`.

**Out of scope**:
- The scroll/filter/search behavior, `activeSeg`/`visibleSegments` logic — leave
  untouched.
- The `ui/sheet` component internals (`client/src/lib/components/ui/sheet/*`) —
  fix at the usage site, not the shared primitive.
- The video element's own caption rendering — the panel is a separate list.
- Color-token definitions in `app.css` / Tailwind config — Step 3 changes only
  the utility classes on the row, not the design tokens.

## Git workflow

- Branch: `improve/008-subtitle-panel-a11y`
- Commit message: `a11y: visible close, announced progress, stronger active-cue highlight in subtitle panel`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Restore a visible, labelled close control

Remove the `hideClose` attribute from `Sheet.Content` (`SubtitlePanel.svelte:129`)
so the library's built-in close button renders. Keep `closeLabel={t('common.close')}`.

If, after removing it, the built-in close visually collides with the
header buttons (scroll-to-active / download at `:137-162`), do NOT re-add
`hideClose`; instead confirm the close sits in the sheet's corner (bits-ui
default) and leave the header row as-is. Verify visually is not possible in CI,
so the automated gate is just typecheck+lint; note in the PR that a human should
confirm the close button appears on both the desktop (`right`) and mobile
(`bottom`) sides.

**Verify**: `grep -n "hideClose" client/src/lib/components/SubtitlePanel.svelte` → returns nothing. `cd client && npm run check` → exit 0.

### Step 2: Make the progress region a polite live region

On the progress container `<div class="w-full max-w-xs space-y-2">`
(`SubtitlePanel.svelte:215`), add `role="status"` and `aria-live="polite"` so
the changing `stepLabel`/percentage are announced without interrupting:

```svelte
						<div class="w-full max-w-xs space-y-2" role="status" aria-live="polite">
```

That is the only change in this step. `aria-live="polite"` batches
announcements, appropriate for a value that ticks frequently.

**Verify**: `grep -n "aria-live" client/src/lib/components/SubtitlePanel.svelte` → shows the new attribute. `cd client && npm run check && npm run lint` → exit 0.

### Step 3: Strengthen the active-cue highlight

On the cue `<button>` (`SubtitlePanel.svelte:189-194`), raise the active-state
contrast: bump the background tint and add a leading accent border so the
current line is distinguishable without relying on color alone. Replace the
class string's active-state utilities:

- from: `data-[active=true]:bg-primary/10 data-[active=true]:text-primary`
- to:   `data-[active=true]:bg-primary/20 data-[active=true]:text-primary data-[active=true]:font-medium data-[active=true]:border-s-2 data-[active=true]:border-primary`

Keep the rest of the class list (`hover:bg-muted`, layout, `transition-colors`)
intact. The `border-s-2` adds a non-color-dependent indicator (weight/shape),
which is the WCAG-recommended way to not encode state in hue alone.

**Verify**: `grep -n "bg-primary/20" client/src/lib/components/SubtitlePanel.svelte` → shows the change. `cd client && npm run check && npm run lint` → exit 0.

### Step 4: (Optional) component test

If plan 001's vitest + `@testing-library/svelte` harness is in place (check
`client/vitest.config.ts` exists and `client/package.json` has a `test`
script), add `client/tests/subtitle-panel.test.ts` per the Test plan. If the
harness is absent (plan 001 not yet done), skip this step and note it — do NOT
scaffold vitest here (that's plan 001's job).

**Verify**: if added, `cd client && npm test` → exit 0 including the new test.

### Step 5: Update `plans/README.md`

Set this plan's row to `DONE`.

## Test plan

- **If** the plan-001 harness exists, create `client/tests/subtitle-panel.test.ts`,
  modelled after `client/tests/proxy-url.test.ts` for structure but rendering the
  component with `@testing-library/svelte`:
  - Renders with `generating=true` and asserts an element with
    `role="status"` / `aria-live="polite"` is present.
  - Renders with `segments` and asserts the active row (`data-active="true"`)
    carries the strengthened classes (`bg-primary/20`, `border-primary`).
  - Asserts no element has the `hideClose`-suppressed state (i.e. a close
    control is queryable) — if bits-ui's close is hard to query in jsdom, assert
    on `closeLabel` text instead and note the limitation.
- **If** the harness is absent, the verification gate is `npm run check` +
  `npm run lint` only, plus a PR note that a human confirms the close button and
  highlight visually on both sheet sides. State this explicitly in the PR.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `cd client && npm run check` exits 0
- [ ] `cd client && npm run lint` exits 0
- [ ] `grep -n "hideClose" client/src/lib/components/SubtitlePanel.svelte` returns nothing
- [ ] `grep -n "aria-live" client/src/lib/components/SubtitlePanel.svelte` returns the progress region
- [ ] `grep -n "bg-primary/20" client/src/lib/components/SubtitlePanel.svelte` returns the active-cue row
- [ ] `cd client && npm test` exits 0 (if plan 001 harness present; otherwise N/A and noted)
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated to `DONE`

## STOP conditions

Stop and report back (do not improvise) if:
- `SubtitlePanel.svelte` doesn't match the "Current state" excerpts (working
  tree drift).
- Removing `hideClose` produces a TypeScript/svelte-check error (the `ui/sheet`
  component may require it) — report the error; do not force it with a cast.
- `common.close` is not a real i18n key (check `dictionaries.ts`) — add the key
  in the same style rather than hardcoding a string, then continue.
- The Tailwind utilities `border-s-2` / `data-[active=true]:border-primary`
  don't compile (older Tailwind logical-property support) — fall back to
  `border-l-2` only if the rest of the file uses physical properties; otherwise
  report.

## Maintenance notes

- A reviewer should visually confirm the close button on **both** the desktop
  `right` sheet and the mobile `bottom` sheet, and that active-cue contrast is
  clearly perceptible in both light and dark themes (this repo has a
  `dark-mode` component — check both).
- If a future redesign re-hides the close for a custom affordance, ensure the
  replacement is keyboard-focusable and labelled.
- `aria-live="polite"` on a fast-updating percentage can get chatty with some
  screen readers; if user feedback says so, move the live region to wrap only
  `stepLabel` (stage changes) and drop the percentage out of the announced node.
- Deferred: a broader a11y sweep of the other dialogs (`QrDialog`,
  `PreferencesDialog`, `CookiesPanel`) — out of scope here; worth its own pass.
