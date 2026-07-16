# UI / UX redesign — advisor audit & plans

**Scope:** `client/` only (Svelte 5 + Tailwind). Backend contracts stay as-is unless a plan says otherwise.  
**Planned at:** commit `86a449a` (+ current WIP on `improve/all`).  
**Date:** 2026-07-16.

This is an `/improve`-style **UI/UX pass**: findings with evidence, then implementation plans for another session (or executor) to ship.

---

## Product reality (what the UI must optimize for)

1. **Paste URL → get links** is the primary job (video or gallery).
2. **Play / download / proxy / cookies / subtitles** are secondary tools on results.
3. **Settings** must stay approachable; power options should not block first-run.

---

## Findings table (by leverage)

| # | Finding | Category | Impact | Effort | Risk | Evidence |
|---|---------|----------|--------|--------|------|----------|
| U1 | **Preferences section titles never render** | Bug / structure | Users see a wall of toggles with no grouping labels (Interface / Playback / … defined but unused) | S | LOW | `PreferencesDialog.svelte` `sections` has `titleKey`+`icon` but the `{#each sections}` loop only draws the grid — no header |
| U2 | **Content-type mode is invisible in Auto** | UX / discoverability | Default is `auto`, but Auto badge UI is **commented out**; video/gallery toggles only appear in “manual” mode set deep in prefs → users don’t know what will run | S | LOW | `InputUrl.svelte` ~148–154 commented; `contentTypeMode` default `'auto'` in `preferences.svelte.ts` |
| U3 | **Hero value prop commented out** | UX / marketing | First screen is title + input only; subtitle that explains product is disabled | S | LOW | `+page.svelte` hero `<p>` commented ~111–113 |
| U4 | **Settings is one long sheet** | UX / IA | Cookies + 10+ toggles + sort + layout + content-type + destructive clear all in one scroll — hard on mobile (65vh bottom sheet) | M | MED | `PreferencesDialog.svelte` full file; mobile `h-[65vh]` |
| U5 | **Error surface is partial** | UX / errors | Workspace error banner only for `videoExtractError`; many failures are toast-only; no “retry last URL”; advice text is generic | M | LOW | `ErrorAlert.svelte`; `extraction.svelte.ts` toast vs `appStore.videoExtractError` |
| U6 | **Results workspace lacks hierarchy** | UX / layout | Videos + galleries stack with little separation; no sticky “results toolbar” (filter/sort/clear); jump-to-input FAB **hidden on mobile** | M | LOW | `+page.svelte`; FAB `hidden … sm:flex` ~172 |
| U7 | **Card action density** | UX / cognitive load | Proxy, CC/subs, QR, copy, download, quality list compete; first-time users don’t know what proxy does | M | MED | `VideoCard.svelte` |
| U8 | **Batch paste UX is weak** | Workflow | Multi-URL via whitespace split in a **single-line** input; easy to mess up; limited progress UI beyond `done/total` | M | LOW | `InputUrl.svelte` `urlCount`; extract batch |
| U9 | **`enableCompact` almost no-op** | Dead preference | Setting exists and is marketed but only tweaks spacing in a few places | S | LOW | Grep: Instructions spacing + VideoCard title class |
| U10 | **Theme: system hard to restore from header** | UX | Header sun/moon toggles light↔dark only; “system” lives only in prefs (if at all shown) | S | LOW | `toggleMode.svelte` |
| U11 | **Header not sticky; settings only on input** | Workflow | Once scrolled into a long library, gear is off-screen; no library entry in nav | S | LOW | `+layout.svelte` header scrolls away; settings on `InputUrl` |
| U12 | **Cookies onboarding buried** | UX / product | Auth-required sites fail with generic errors; Cookies panel is deep in settings with long guide | M | LOW | `CookiesPanel.svelte` inside prefs sheet |
| U13 | **Empty state vs always-on Instructions** | UX | How-it-works always below empty state → long first paint; should collapse after first success or be progressive | S | LOW | `+page.svelte` empty + `Instructions` always |
| U14 | **A11y gaps in settings** | a11y | Info “buttons” that only set `title` (no real tooltip/popover); dense icon-only controls | S–M | LOW | Prefs Info buttons |
| U15 | **No global “library empty / clear” near results** | Workflow | Clear all is destructive and buried under prefs | S | LOW | `clearAllData` in prefs |

---

## Direction (redesign goals — not bugs)

| # | Direction | Why (repo-grounded) | Trade-off |
|---|-----------|---------------------|-----------|
| D1 | **Command-first shell**: sticky mini-bar (URL + Extract + Settings) when results exist | Input disappears under long lists; FAB is desktop-only | Slightly less “marketing hero” once active |
| D2 | **Settings IA**: tabs or accordion — General / Playback / Library / Cookies / Advanced | Prefs sheet is the densest UI in the app | One-time restructure of `PreferencesDialog` |
| D3 | **Result chrome**: section headers (“Videos”, “Galleries”) + count + sort/filter chips outside prefs | Sort/layout only in prefs today | More chrome on results page |
| D4 | **Error recovery**: structured errors with Retry / Open cookies / Switch to gallery | Extract errors already classified on server; client underuses them | Needs careful i18n for codes |
| D5 | **Mobile card simplification**: primary Play/Download; overflow menu for QR/export/proxy | Touch targets and density | One extra tap for power actions |

---

## Recommended plan order

```
019  Fix prefs section headers + compact/dead toggles cleanup     (U1, U9, U14 partial)
020  Extract bar: content-type always visible + hero copy        (U2, U3, U8 partial)
021  Settings IA redesign (tabs/sections) + cookies prominence   (U4, U12, D2)
022  Workspace chrome: results headers, mobile FAB, sticky bar   (U6, U11, U13, D1, D3)
023  Errors & recovery UX                                        (U5, D4)
024  Result card simplification (mobile-first)                   (U7, D5)
```

**Dependency:** 019 before 021 (021 rebuilds the same sheet).  
020 is independent and high leverage for first-run clarity.  
022 can land after 020.  
023–024 after core chrome is stable.

---

## Out of scope for this UI pass

- Backend API redesign
- New sites / extract engines
- Full visual brand system rewrite (keep existing tokens / aurora / glass)
- Server-side zip (already multi-file download)

---

## Status

| Plan | Status |
|------|--------|
| [019-prefs-structure-fix](../019-prefs-structure-fix.md) | DONE (headers; compact/info deferred to 021) |
| [020-extract-bar-clarity](../020-extract-bar-clarity.md) | DONE |
| [021-settings-ia-redesign](../021-settings-ia-redesign.md) | DONE |
| [022-workspace-results-chrome](../022-workspace-results-chrome.md) | DONE (headers, mobile jump, collapse; sticky bar deferred) |
| [023-error-recovery-ux](../023-error-recovery-ux.md) | DONE |
| [024-result-card-mobile](../024-result-card-mobile.md) | DONE |

Update status here when executing.
