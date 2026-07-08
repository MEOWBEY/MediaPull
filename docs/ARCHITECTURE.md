# Architecture

A technical map of how DirectStream is put together — for engineers picking
up the codebase. If you just want to run or deploy the app, see the root
[`README.md`](../README.md) instead; this doc assumes you've read that.

## The big picture

```
┌─────────────────┐      HTTP (JSON)       ┌──────────────────────┐
│  client/         │ ─────────────────────> │  server/              │
│  SvelteKit SPA   │ <───────────────────── │  FastAPI              │
│  (static build)  │      GET /proxy-video   │                       │
└─────────────────┘      (media bytes)      └──────────────────────┘
                                                       │
                                        ┌──────────────┼──────────────┐
                                        │              │              │
                                   yt-dlp          gallery-dl      Groq API
                                (video sites)    (image galleries) (Whisper
                                                                  speech-to-text)
```

The client never talks to yt-dlp/gallery-dl/Groq directly — everything goes
through the FastAPI server, which is the only thing that needs Python,
ffmpeg, or API keys. The client is a fully static SPA; it can be hosted
anywhere that serves files, including the same process as the server (see
`CLIENT_DIR` in the README).

## Server (`server/app/`)

### Request flow for a video URL

1. `POST /extract-videos` (`main.py`) checks the result cache
   (`cache.py`, keyed by URL + a cookie hash if cookies were sent).
2. On a miss, `Extractor.extract()` (`extractor.py`) runs a **fallback
   chain**, first match wins:
   - a direct file URL (`.mp4`, `.webm`, …) short-circuits with a HEAD probe
   - yt-dlp's native extractor for the site
   - yt-dlp's generic extractor (`force_generic_extractor`)
   - a regex scrape of the raw page HTML
3. Each strategy's formats are (optionally) validated — `_probe_ok()` drops
   only *confirmed*-dead links (404/410, or a 200 that serves an HTML error
   page instead of media). Anything uncertain (timeout, blocked probe) is
   kept, since hiding a working link is worse than showing a maybe-dead one.
4. `serializers.to_client_video()` maps the internal `VideoInfo`/`VideoFormat`
   shape to the camelCase wire shape (`ClientVideo`/`ClientFormat`) the
   client expects.

### Request flow for a gallery/image URL

`POST /extract-gallery` (`gallery.py`) shells out to `gallery-dl -j` (JSON
dump, no download) as a subprocess — never imported, to keep this app's
license independent of gallery-dl's GPL-3.0. Each entry in gallery-dl's dump
is parsed defensively (`_entry_to_image`): entries gallery-dl reports as
errors, or whose URL is an unrecognized `ytdl:` pseudo-URL, are counted in
`skippedCount` rather than silently dropped. Images get a `Referer` header
attached so the client's proxy can actually fetch Instagram/X CDN URLs that
gate on it.

### The media proxy (`proxy.py`)

`GET /proxy-video` exists because a `<video>`/`<img>` element can't set
custom headers, but the source often requires a specific Referer/Cookie/
User-Agent to serve bytes. The proxy re-issues the request server-side with
those headers (plus curl_cffi browser impersonation, so anti-bot CDNs that
gate on the TLS fingerprint don't 403 the proxy either), and streams the
response back. For HLS, it also rewrites the playlist so nested segment/
sub-playlist URLs route back through the proxy with the same headers.

The client decides per-format whether to use the proxy or hit the source
directly (`proxy-url.ts` builds the proxied URL from a format's
`sourceVideoUrl` + `httpHeaders`) — this is a deliberate design choice so
the backend stays ignorant of its own public URL and "skip the proxy" is
just a client-side toggle.

### Shared extraction infrastructure (`net_common.py`)

Both `Extractor` (yt-dlp) and `GalleryExtractor` (gallery-dl) share:
- `normalize_cookies()` — coerces user-pasted cookies (Netscape format or a
  raw `Cookie:` header line) into Netscape `cookies.txt` text.
- `cookie_tempfile()` — a context manager that writes cookie text to a
  throwaway temp file for one extraction call and removes it afterward.
- `build_impersonate()` / `impersonate_kwarg()` — curl_cffi browser
  impersonation setup, degrading gracefully if curl_cffi isn't installed.

### Auto-subtitles pipeline (`jobs.py`, `audio.py`, `waveform.py`, `subtitles.py`, `transcribe/`)

This is the **only** part of the app that downloads media bytes to disk —
everything else only resolves/streams URLs. `POST /transcribe` creates a
`TranscriptionJob` (in-memory, no persistence — a server restart loses
in-flight jobs) and runs it as a background `asyncio` task:

1. `acquire_audio()` picks the best format to pull audio from (progressive
   over HLS, audio-bearing over video-only, smaller bitrate first) and
   either downloads it or has ffmpeg read an HLS URL directly.
2. `extract_audio_track()` strips it to mono/16kHz/opus via ffmpeg.
3. `chunk_if_needed()` splits it if it's longer than Groq's per-request
   limit allows.
4. Each chunk goes through `transcribe/groq_engine.py` (Groq's Whisper API).
5. `subtitles.py` merges the per-chunk segments (adjusting timestamps by
   each chunk's offset) and renders `.vtt`/`.srt`.
6. `waveform.py` decodes the same audio track to raw PCM once and
   downsamples it to a small peaks array for the player's seek bar —
   non-fatal if it fails; subtitles still work without a waveform.

The client subscribes to `GET /transcribe/{jobId}/events` (SSE — the server
pushes an update the instant `JobStore.update()` changes the job, via a
per-job `asyncio.Queue` fanned out to every subscriber) and shows a progress
bar that blends that real, pushed progress with a client-side "trickle"
animation so the still-genuinely-flat single-step stages (e.g. audio
download/transcode) don't look frozen between real updates (see
`transcribe.svelte.ts`). `GET /transcribe/{jobId}` (plain, one-shot) still
exists alongside it for a quick manual check or a client that can't hold a
streaming connection open.

### Configuration (`config.py`)

One `Settings` (pydantic-settings) class, loaded once from `server/.env`.
Every tunable in the app — timeouts, worker pool sizes, cookie/proxy/
impersonation knobs, gallery-dl and ffmpeg binary paths, transcription
limits — lives here. See the README's environment variable tables for the
full list.

### Logging (`logging_context.py`)

A single `RequestContextFilter` attached to the root logger's one handler
means every `logging.getLogger("directstream.*")` call anywhere in the app
automatically gets the requesting client's IP/user-agent in its output, with
no per-call-site plumbing. This only works because nothing else attaches its
own handler or sets `propagate = False` — keep it that way if you add a new
module.

## Client (`client/src/lib/`)

### State: `.svelte.ts` controller classes

Stateful logic lives in plain classes using Svelte 5 runes (`$state`,
`$derived`), not in component files — this keeps `.svelte` files focused on
markup/wiring and makes the logic itself testable without mounting a
component. The three main ones:

- `extraction.svelte.ts` — `ExtractionController`: the single entry point
  for running extraction. Owns cancellation, the elapsed-time counter,
  client-side result caching, and the auto-mode fallback (`extractAuto()`
  tries video, then silently retries as gallery on failure/empty result).
- `transcribe.svelte.ts` — `TranscriptionController`: the SSE subscription +
  trickle-progress animation described above.
- `subtitle-resolver.svelte.ts` — `SubtitleResolver`: resolves either an
  existing source caption track or a freshly-generated one into one shape
  the player renders, and persists the result on the video card so a page
  refresh doesn't lose it.

### Stores (`stores/`)

`app-state.svelte.ts` is a thin facade composing `PreferencesStore` (user
settings, persisted to `localStorage`), `LibraryStore` (extracted video/
gallery results, also persisted), and `CookieStore` (per-site auth cookies,
browser-only, never sent anywhere but the matching site's extraction call).

### Data transforms (`transform.ts`)

Pure functions mapping the server's raw wire shapes (`IncomingVideo`,
`IncomingGallery`) into the client's normalized, render-ready shapes
(`GroupedVideo`, `GroupedGallery`) — grouping a video's formats into tabs by
media kind, building each format's proxied URL, normalizing gallery images.
No side effects, so these are the easiest place to unit-test extraction
logic changes.

### Components (`components/`)

`VideoExtractList.svelte`/`GalleryExtractList.svelte` own grouping/filtering
of the whole result list; `VideoCard.svelte` owns one video's player +
metadata + quality list; `VideoPlayer.svelte` wraps Video.js v10
(`@videojs/html`) and is itself media-kind-agnostic (video vs. audio-only
skin chosen at render time). `QualityMenu.svelte` is a separate component
specifically so it can be slotted directly into the video.js skin's light
DOM (letting the app's own CSS tokens style it, instead of fighting a
shadow-DOM boundary).

### i18n (`i18n/`)

A hand-rolled runes store (`index.svelte.ts`) with two flat dictionaries
(`dictionaries.ts`, English + Farsi) — deliberately no dependency, since the
app only ever needs two locales. Farsi is RTL; the CSS uses logical
properties (`ps-`/`pe-`/`inset-s-`/`inset-e-` instead of `pl-`/`pr-`/`left-`/
`right-`) so the layout mirrors automatically instead of needing a parallel
RTL stylesheet.

## Removed features

`archive/OVC.md` — a headless-browser resolver mode, removed in favor of the
impersonating proxy but kept as design notes in case a class of sites turns
up that needs it again.
