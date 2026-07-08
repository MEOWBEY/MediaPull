# OVC proxy mode (removed — design notes for a future re-implementation)

> Moved here from `docs/OVC.md` — this describes a removed feature, not
> active documentation, so it lives in `archive/` instead of alongside the
> real project docs in `docs/`. See [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md)
> for how the current system actually works.

OVC ("online-video-cutter") mode was **removed** in favor of the impersonating
media proxy, which now covers most of what OVC was needed for. These notes
capture the goal and the working design so it can be brought back if a class of
sites turns up that the proxy + yt-dlp can't handle.

## Goal

Some streams can't be resolved by yt-dlp or scraping — they only materialize
after a **real browser** runs the page's JS (DRM-lite token dances, blob URLs,
player SDKs that compute the media URL client-side). OVC outsourced that to a
third-party tool, `https://online-video-cutter.com/`, which accepts a URL, loads
it in its own player, and exposes a resolved `<video>` source. We drove that
site headlessly and handed the resolved URL to our media proxy for playback.

It was a **fallback resolver**, not a primary path: brittle (third-party
selectors), slow (headless browser boot + network idle), and heavy (shipped a
whole Chromium).

## Server design (was `server/app/ovc.py`, Playwright)

- `OvcService(settings).process(url)` wrapped `_run` in
  `asyncio.wait_for(ovc_total_timeout)`; `OvcError(message, status)` carried an
  HTTP status for the API.
- `_run(url)` with `async_playwright`:
  1. `chromium.launch(headless, args=_LAUNCH_ARGS, executable_path=ovc_chromium_path or bundled)`.
     `_LAUNCH_ARGS` = `--no-sandbox --disable-setuid-sandbox --disable-dev-shm-usage
     --disable-gpu --disable-blink-features=AutomationControlled`.
  2. `new_context(user_agent, viewport 1920x1080, Accept-Language en)`.
  3. Route-block noise: abort requests for `ads/analytics/tracking/facebook/
     google-analytics`, `stylesheet`/`font` types, and images whose URL lacks
     `video`.
  4. `page.on("dialog")` → accept the JS `prompt()` with the target URL (the site
     submits the URL via a prompt); resolve an `asyncio.Future` when accepted.
  5. `goto(OVC_URL, wait_until="networkidle")`.
  6. Click `.el-dropdown__icon.el-icon-arrow-down`, then `.el-dropdown-menu__item.url`
     (Element-UI dropdown → "open by URL").
  7. Await the dialog future (`ovc_dialog_timeout`).
  8. `wait_for_selector('video[src^="https://"], video[src^="blob:"]')`, then
     `eval_on_selector("video", "el => el.src")`.
  9. Read `context.cookies()` → `Cookie` header. Return
     `{ ovc_video_url: src, http_headers: { Referer: OVC_URL, User-Agent, Cookie? } }`.
- Config knobs: `OVC_ENABLED`, `OVC_HEADLESS`, `OVC_CHROMIUM_PATH`,
  `OVC_TOTAL_TIMEOUT` (120), `OVC_NAV_TIMEOUT` (60), `OVC_SELECTOR_TIMEOUT` (60),
  `OVC_DIALOG_TIMEOUT` (60).
- Endpoint: `POST /ovc-proxy-video` → `OvcResponse { success, video: { id,
  sourceVideoUrl, ovcVideoUrl, httpHeaders } }`. The client built the proxied URL
  from `ovcVideoUrl` + `httpHeaders` (same as an extracted format).
- Deps: `playwright` (+ `playwright install chromium`).

## Client design (was)

- `extraction.svelte.ts`: `proxyStream(pageUrl)` (smart: page → extract → OVC the
  best format's direct link) and `proxyStreamDirect(directUrl)` (per-quality bot
  icon). OVC `onSuccess` built `OvcProxyResult { id, sourceVideoUrl, ovcVideoUrl,
  proxiedVideoUrl }` and stored it.
- UI: an "OVC proxy" button in `InputUrl.svelte`, a per-quality bot icon in
  `VideoExtractList.svelte`, and a separate results section `OvcProxyList.svelte`.
- State: `isOVCProxyRunning`, `ovcProxyError`, `proxyResults` in the stores;
  types `OvcProxyResult`, `IncomingOvcVideo`.

## If reviving

Prefer driving the **source page itself** in Playwright (sniff network for the
media request / read the `<video>.src` / `currentSrc`) instead of depending on a
third-party site's selectors. Keep it strictly a last-resort fallback after
yt-dlp, scrape, and the impersonating proxy. Consider sharing the same
`impersonate` posture as the extractor/proxy.
