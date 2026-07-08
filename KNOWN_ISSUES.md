# Known issues / things still worth doing

Plain-language list of what's broken, half-finished, or worth a second look —
for anyone picking this project up, technical or not. If something here
doesn't make sense, that's a documentation bug too; feel free to reword it.

## Not yet manually tested end-to-end

Everything in this pass was verified with automated checks — `npm run
check`/`lint`/`build` on the client, `ruff check` + a Python byte-compile on
the server — but **nobody has clicked through the actual running app** since
these changes landed (extract a video, extract a gallery, play a video,
generate subtitles, switch qualities, try auto vs. manual mode). The
automated checks catch type errors and lint issues, not "does this actually
work when you click it." Before treating this as fully done, run both dev
servers and walk through those flows once by hand.

## gallery-dl / image extraction

- **No warning when image quality is degraded.** Instagram (and some other
  sites) will hand back lower-resolution or watermarked images if you don't
  have fresh cookies logged in — `gallery-dl` itself notices this and logs a
  warning, but that warning never reaches the app or the user. If your
  images look worse than expected, try adding your cookies in **Settings →
  Cookies** even though nothing on screen tells you to.
- **Error messages for failed gallery extraction are generic.** The
  "why did this fail" messages (rate-limited, blocked, etc.) were written for
  yt-dlp's wording, which gallery-dl doesn't use. Most gallery-dl failures
  currently just say "extraction failed" instead of a specific reason.

## Backend cleanup still worth doing (low priority, not urgent)

- A handful of hardcoded numbers (timeouts, retry backoff caps, connection
  limits) live directly in the code instead of being configurable through
  `server/.env` the way most other timeouts already are
  (`server/app/extractor.py`, `server/app/proxy.py`,
  `server/app/transcribe/groq_engine.py`). Not broken, just less flexible
  than it could be for someone tuning a specific deployment.
- `server/app/proxy.py` builds its own "should we impersonate a browser"
  logic slightly differently than the shared helper used by extraction and
  the transcription pipeline (`server/app/net_common.py`). Works fine today,
  just two implementations of the same idea instead of one.

## Client, minor

- The video player always loads both the "audio" and "video" skin bundles
  up front, even for a source that will only ever show one kind. It's
  already lazy-loaded (not in the main bundle), so this only means a
  slightly bigger first-load download for the player, not a real problem.
- Opening several quality-picker menus at once (across many result cards on
  one page) attaches one extra document-level click listener per open menu.
  Not an issue at normal list sizes (tens of results), only worth revisiting
  if result lists ever grow to hundreds.

## Deploy / VPS installer

- The installer assumes a Debian/Ubuntu-family server (`apt-get`,
  `python3.12`, `ufw`). Other distros (Fedora, Arch, Alpine, …) aren't
  supported by the script — you'd need to follow the "Manual install, step
  by step" section in `deploy/server/vps/README.md` and adapt the package
  manager commands yourself.
- Piping the installer through `curl | bash` skips all the interactive
  questions (there's no keyboard attached to answer them) and silently uses
  the defaults. Download/clone the script and run it directly if you want to
  be asked about domain/port/client setup — this is explained in the deploy
  README, but easy to miss.
