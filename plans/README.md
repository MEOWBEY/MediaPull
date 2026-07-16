# Implementation Plans

## History

- Plans **001–008**: DONE historically on `improve/all`.
- Plans **009–018**: Production-readiness batch — **implemented in working tree** (2026-07-16).

## Execution order & status

| # | Plan | Priority | Status |
|---|------|----------|--------|
| 001–008 | Prior security/tests/a11y | — | DONE |
| 009 | Transcription `ctok` auth unwrap | P1 | DONE |
| 010 | Shared SSRF (extract/gallery/audio) | P1 | DONE |
| 011 | Strip Cookie on wire + header sanitize | P1 | DONE |
| 012 | Vite `/proxy-token` + docs + ruff | P1 | DONE |
| 013 | Durable subtitle VTT/SRT blobs | P1 | DONE |
| 014 | Gallery errors, cap, cookies, warnings | P1 | DONE |
| 015 | Admission control | P2 | DONE |
| 016 | Client storage + extract perf + remint + auto heuristics | P2 | DONE |
| 017 | CI + characterization / ASGI / gallery tests | P2 | DONE |
| 018 | Dialogue map rename+UI, bulk download, pin player | P3 | DONE |

## What 018 delivered

- `server/app/waveform.py` → `dialogue_map.py` (`DialogueMapError`, wire field `dialogueMap`)
- CSS `.ds-waveform*` → `.ds-dialogue-map*`
- Client `DialogueMapBar.svelte` seek overlay in `VideoPlayer`
- Gallery **Download all** (sequential blob saves; no zip dep)
- `@videojs/html` exact pin (no `^`)

## Deferred (optional later)

- Full server router split (`main.py` modules)
- True client-side zip archive (currently multi-file download)
- DNS rebind re-check on audio redirect hops (proxy already re-checks)
- Encrypt cookies at rest / multi-worker JobStore

## UI / UX redesign (client)

See **[ui-ux/README.md](ui-ux/README.md)** — audit + plans **019–024**, all
**DONE** (implemented on `improve/all`, 2026-07-16):

| # | Plan | Status |
|---|------|--------|
| 019 | Preferences section headers | DONE |
| 020 | Extract bar: Auto/Video/Gallery always visible + hero copy | DONE |
| 021 | Settings IA — tabs (General / Library / Playback / Sign-in) | DONE |
| 022 | Workspace chrome: mobile jump button + collapse how-it-works | DONE |
| 023 | Error recovery: Retry / Add cookies / Try-as-other-type | DONE |
| 024 | Mobile-first result card: primary Download/Copy + collapsible qualities | DONE |

All six passed `npm run check` + `lint`; still pending a manual click-through
(see [KNOWN_ISSUES.md](../KNOWN_ISSUES.md)).

## Verify

```bash
cd server && pytest -q && ruff check app/
cd client && npm test && npm run check && npm run lint
```
