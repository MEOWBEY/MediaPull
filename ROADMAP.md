# DirectStream — Roadmap

> Forward-looking plan. Historical/done work lives in `PLAN.md`.
> Rule (unchanged): small chunks, save edits immediately, one logical change per edit.
> i18n: any new UI string needs en + fa dictionary entries; backend/extractor errors stay English.

Three phases, in order: **(1) simple client features → (2) server fixes/perf/bugs → (3) Android app.**

---

## Phase 1 — Simple client features

Pure frontend, reuse existing stores/transform. Suggested build order top-to-bottom.

- [x] **Per-item delete** — done. `removeExtractResult(target)` (reference-based) on the store; per-card removal lives in a ⋮ kebab menu → Remove (two intentional steps, can't misclick) instead of a bare ✕.
- [x] **localStorage history** — done. Library already persisted + loads on start; fixed the cap bug (newest were dropped at 50 instead of oldest) and hardened `load()` with `Array.isArray` guards.
- [x] **Audio support + format organization** *(user priority)* — done.
  - `VideoPlayer.svelte` is audio-aware: uses the video.js v10 **audio skin** (`<audio-player>` + `<audio-minimal-skin>`) — same control styling as video, no video frame — with a "🎵 Audio" label + quality picker.
  - Fixed the proxy-button bug → `isAudio(video.type)` (`startsWith('audio/')`).
  - Cards ordered video-first then audio; clearer `shortType` labels ("MP3 Audio", "MP4 Video", "HLS").
- [x] **Copy all / export** — done. `lib/export.ts` (txt/m3u builders); "Copy all" button + "Export" dropdown (.txt/.m3u) in the section header.
- [x] **Desktop → phone QR handoff** — done. `QrDialog.svelte` (`qrcode-generator` dep), QR button per quality, shown on `sm+` only (desktop→phone).
- [x] **Per-media proxy toggle** — done. Global header switch removed; per-card proxy lives in each card's kebab menu (defaults to the global preference). `VideoPlayer` takes a `useProxy` prop; copy/download/QR/export all read each card's choice via a reactive `SvelteMap`.
- [x] **Batch / queue extraction** — done. `extraction.extract()` splits whitespace-separated URLs; `extractMany()` processes them sequentially (dedup, cancellable). Input shows count `(N)` + `done/total` progress, no flicker between items.
- [x] **Search / filter within results** — done. Filter input (shown when >1 card) matching title/type/resolution/ext, with a "no matches" state.

---

## Phase 2 — Server consolidation, fixes, performance & bugs

Stabilize the server before porting it to Android (Android will reuse this logic locally).

**Architecture consolidation (done):** collapsed the two-server setup into one.
The SvelteKit Node layer (`/api/*` + `$lib/server/*`, puppeteer + chromium) is
gone; the client is now a pure static SPA (`adapter-static`) that calls the
Python backend directly and builds proxied URLs itself. The Python service now
owns extract + proxy.

- [x] **OVC removed** — the headless-browser resolver (`ovc.py`, Playwright,
  `POST /ovc-proxy-video`) was dropped in favor of the impersonating proxy, which
  covers most of what it was for. Design preserved in `docs/OVC.md` for a future
  revival (see Android note below).
- [x] **Anti-bot bypass** — extraction **and** the proxy now use curl_cffi
  **browser impersonation**, so sites/CDNs that gate on TLS fingerprint
  (pornhub, spankbang, erome, tiktok, …) stop returning 403/410 and play through
  the proxy. Don't force a UA when impersonating.
- [x] **Link validation** — extracted URLs are probed and only *confirmed*-dead
  ones (404/410 or HTML error page) are dropped; uncertain probes keep the link.
- [x] **Proxying** — `server/app/proxy.py` (`GET /proxy-video`): HLS playlist
  rewriting, Range/seek, header passthrough (Referer/Cookie/User-Agent),
  impersonation, upstream error surfacing, GZip-safe streaming. SSRF allow-list
  still noted as optional/documented.
- [x] **yt-dlp errors** — `classify_extraction_error` maps 403/410/geo/unsupported/
  private/age/no-formats to readable English messages with proper HTTP status,
  surfaced to the client (which reads FastAPI `detail`).
- [x] **More qualities** — stopped dropping video-only/adaptive formats (YouTube
  >720p now appears, flagged `videoOnly`); no `player_client` pin (it collapsed
  YouTube to 360p).
- [ ] **General perf/bugs** — caching, timeouts, concurrency (ongoing).

> Goal: a clean, well-defined extractor + proxy contract (`{metadata, formats}` /
> `ApiEnvelope`) — that contract is exactly what the Android local engine must reproduce.

---

## Phase 3 — Android app

Same UI/UX, same core ability, **extraction runs locally on-device**; external server only as an optional, removable fallback.

### Shell
- [ ] **Wrap existing Svelte UI in Capacitor** — reuse ~100% of the UI. Needs `adapter-static`; already `ssr=false`. iOS is out of scope for local extraction (App Store blocks yt-dlp) → iOS, if ever, is server-only.

### Local extraction engine
- [ ] **On-device yt-dlp via `yausername/youtubedl-android`** (bundles yt-dlp + Python + ffmpeg → same engine/output as the server).
- [ ] **Native plugin (Kotlin)** that returns JSON mapped to the existing `IncomingFormat` shape → `transform.ts` + all components work unchanged.
- [ ] **Server fallback** — `extract(url)`: try local → on error/timeout/unsupported → call existing `/api/extract-videos`. Works because downstream only cares about the format shape. **Must be fully removable** (local-only build).

### OVC on Android (only if revived)
- [ ] OVC was removed on web (see `docs/OVC.md`). If a class of sites needs a
  real-browser resolver again, the Android equivalent is **WebView
  `shouldInterceptRequest`** (hidden WebView, intercept the media request +
  headers) — prefer driving the source page directly over a third-party site.

### Player & proxy
- [ ] **Native player (ExoPlayer) likely needed** — handles HLS + **custom request headers natively**.
- [ ] **Drop the proxy on Android** *(conditional)* — CORS isn't enforced like on web ✅. The proxy also injects Referer/Cookie/User-Agent and rewrites HLS; a native player attaching those headers makes the proxy unnecessary. (If we stay on hls.js-in-webview instead of ExoPlayer, header handling is still required.)

### De-risking order
1. Capacitor shell pointing at the existing server (a real mobile app in days, near-zero risk).
2. Add the native yt-dlp engine + fallback.
3. Native player + drop proxy.

---

### Dropped
- ~~PWA~~ — explicitly rejected; going native (Capacitor) instead.
