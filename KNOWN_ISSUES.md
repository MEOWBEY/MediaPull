# Known issues

Bug-tracker style — status, severity, workaround. Add new items at the bottom.

---

## Needs manual testing

**Status:** Open | **Severity:** High
Everything has passed automated checks (`npm run check`/`lint`/`test`,
`ruff check`, `pytest`) but **nobody has clicked through the running app**
since these changes landed. Before release, run both dev servers and walk
through: extract a video, extract a gallery, play a video, generate subtitles,
switch qualities, try auto vs manual mode. Pay extra attention to the areas
touched most recently:

- **Cookie'd playback** (plan 007): with cookies set for a site, play/download
  an authenticated source — confirm it still streams, and that the copied
  link / QR code contains `ctok=` (a token) and **no** raw `cookies=`.
- **Subtitle panel a11y** (plan 008): confirm the sheet has a visible close
  button on both desktop (right) and mobile (bottom), and that the active cue
  is clearly highlighted in light *and* dark themes.
- **Subtitle timeout** (plan 006): a wedged transcription job should end in an
  error after `TRANSCRIBE_JOB_TIMEOUT`, not hang forever.

---

## Recently fixed

**Status:** Fixed (needs the manual pass above)
- **CORS `*` + credentials silently failed** — credentials are now disabled
  automatically under the wildcard default; pin `CORS_ORIGINS` to enable them.
- **Proxy SSRF** — `GET /proxy-video` now blocks internal targets, re-checks the
  host on every redirect hop, and rejects hostnames that resolve to private IPs.
- **Auth cookies in proxy URLs** — cookies are swapped for a short-lived token
  (`POST /proxy-token`) so shared/copied links no longer leak sessions.
- **Runaway transcription jobs** — `TRANSCRIBE_JOB_TIMEOUT` is now enforced (it
  was defined but never applied).
- **Leaked in-flight extraction fetch** — re-pasting/retrying now aborts the
  prior request instead of letting it run to the server timeout.

---

## gallery-dl / image extraction

**No warning when image quality is degraded**
**Status:** Open | **Severity:** Medium
Instagram and some sites serve lower-res or watermarked images without fresh
cookies. `gallery-dl` logs a warning internally but it never reaches the user.
Workaround: add your cookies in Settings → Cookies.

**Generic error messages on gallery extraction failure**
**Status:** Open | **Severity:** Medium
Gallery-dl's error messages differ from yt-dlp's. Most gallery failures show
"extraction failed" instead of a specific reason (rate-limited, blocked, etc.).

---

## YouTube

**Stale yt-dlp breaks YouTube extraction**
**Status:** Ongoing | **Severity:** Medium
YouTube changes frequently. Keep yt-dlp updated (`pip install -U yt-dlp`).
The app does not auto-update dependencies.

**PO token unusable for manual config**
**Status:** Won't fix | **Severity:** Low
`YOUTUBE_PO_TOKEN` in `.env` is ineffective — YouTube binds tokens to a
single video ID. Manual token pasting doesn't work for multi-video use.

---

# Backend cleanup (low priority)

- Hardcoded numbers in `server/app/extractor.py`, `server/app/proxy.py`,
  `server/app/transcribe/groq_engine.py` (timeouts, retry caps, connection
  limits). Not broken, just not configurable via `.env`.

---

## Client, minor

- Video player loads both audio and video skin bundles upfront even for
  single-type sources. Already lazy-loaded outside main bundle — only minor
  first-load size impact.
- Opening many quality-picker menus simultaneously (across many result cards)
  attaches one extra click listener per menu. Harmless at normal list sizes
  (tens of results); revisit if lists grow to hundreds.