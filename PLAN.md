# DirectStream — Improvement Plan & Progress

> Working doc so any session can resume cleanly. Update the STATUS column as chunks finish.
> Rule: small chunks, save edits immediately, one logical change per edit.

## Project rename
- **New name: `DirectStream`** (chosen). Apply everywhere: package.json `name`,
  page `<title>`, headings, README, any visible branding.
- Old names to replace: `svelte-video-extractor`, `Direct-Linker`, `Video Extractor`.

## What the app ACTUALLY does (ground truth for copy)
- SvelteKit client + Python FastAPI server.
- Extracts direct video URLs from any webpage via: yt-dlp → generic yt-dlp extractor
  → HTML regex scraping (fallback chain). Also handles direct video file URLs.
- Lets users preview (HLS via hls.js + Plyr), download, or stream through a proxy
  ("OVC proxy" acceleration mode) routed via SvelteKit `/api/*` endpoints.
- Stores results + preferences in localStorage. Dark/light/system theme,
  high-contrast, compact, animations toggles.
- NO geo-unblocking, NO real "anonymity/privacy protection" — copy must NOT claim these.

## Chunks (ordered)

| # | Chunk | Files | STATUS |
|---|-------|-------|--------|
| 0 | Plan file | PLAN.md | DONE |
| 1 | Branding + page title/meta | package.json, +page.svelte, app.html, +layout, +error, app.py | DONE |
| 2 | README rewrite | README.md (root + client) | DONE |
| 3 | Instructions.svelte copy (fix typo + invented claims) | Instructions.svelte | DONE |
| 4 | DRY +page.svelte run* fns + TS types | +page.svelte | DONE (also fixed ovc error routed to wrong field) |
| 5 | app-state.svelte.ts types + sort bug (suggestion a) | app-state.svelte.ts | DONE (Preferences/IncomingVideo types, sort now uses title/filesize/resolution) |
| 6 | Server app.py: DRY fallbacks, tighten errors, normalize sentinels (c,d) | server/app.py | DONE (build_format helper, strategy loop, except Exception, raise..from, py_compile OK) |
| 7 | UX: ErrorAlert, empty states, copy-to-clipboard, cancel flow | several | DONE (fixed literal-varname UI strings, async clipboard, empty state, error copy, OVC casing) |
| 8 | Modern UI pass (input, status bar, lists) | several | DONE (gradient bg, accent card icons, matched OVC card hover, fixed meaningless hitRate stat -> real counts, copy) |
| 9 | VideoPlayer: MOBILE-FIRST controls, HLS, quality, fullscreen, shortcuts, states | VideoPlayer.svelte | DONE (removed magic-px CSS + 800px cap, default responsive bar, touch-size vars, loading+error overlay w/ retry, keyboard, quality-menu guard for OVC) |

## Bug/perf fixes I OWN (user gave full control)
- (a) sortResults reads wrong fields (filename/fileSize/quality) — actual data has
  title/qualities/resolution. Sorting is a no-op/buggy. FIX in chunk 5.
- (b) getStats() hitRate is meaningless — simplify/remove. (optional, chunk 5)
- (c) server returns string 'unknown' for tbr/resolution → breaks Number() client-side.
  Normalize to null/0. FIX in chunk 6.
- (d) handle_direct_video uses 'unknown' sentinels too. FIX in chunk 6.
- (e) VideoPlayer hardcodes max-width:800px — fights responsive. FIX in chunk 9.
- (f) proxy endpoints: no host allow-list (SSRF risk). Note in README; guards optional.

## VideoPlayer mobile priority (user emphasis)
- Current Plyr setup is desktop-oriented: absolutely-positioned control bar + time
  hacks with magic left:Npx values that break on mobile.
- Goal: controls that work on small screens — larger touch targets, no fixed px
  offsets, progress bar usable by thumb, tap-to-play/pause, double-tap seek if
  feasible, fullscreen that works on iOS, loading spinner + error overlay.
- Keep hls.js. Consider simplifying the custom Plyr CSS overrides that cause the
  desktop-only layout.

## Package updates (2026-06-18)
- Client `package.json`: bumped ALL deps to latest incl. majors (vite 8, typescript 6,
  eslint 10, vite-plugin-svelte 7, adapter-auto 7, tailwind-variants 3, bits-ui 2.18,
  svelte 5.56, etc.). RISKY majors may need fixes after `npm install` (can't build now).
- Migrated icons `lucide-svelte` (deprecated) -> `@lucide/svelte@^1.21` across 12 files.
- Removed unused deps: `media-icons`, `@types/video.js` (not imported; media-icons
  "latest" was a downgrade). `@lucide/svelte` moved to dependencies.
- Server `requirements.txt`: bumped all to latest (yt-dlp 2026.6.9, fastapi 0.137.2,
  uvicorn 0.49.0, pydantic 2.13.4, requests 2.34.2, etc.).
- TODO after connectivity: `cd client && npm install && npm run check && npm run build`.

## Notes
- Tailwind 4 conventions already in repo — keep them.
- No behavior changes to extraction logic without confirming; UI/UX/refactor/bugfix OK.
