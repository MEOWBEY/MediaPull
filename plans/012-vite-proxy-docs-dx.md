# Plan 012: Fix Vite `/proxy-token` proxy + onboarding docs + ruff pin

> **Drift check**: `git diff --stat 86a449a..HEAD -- client/vite.config.ts README.md client/README.md CLAUDE.md Claude.md server/README.md server/requirements.txt server/.env.example`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dx / docs
- **Planned at**: commit `86a449a`, 2026-07-16

## Why this matters

Default dev loop breaks cookie playback (token mint never reaches FastAPI).
Root README invents `SECRET_KEY` and `python -m app`. Client README documents
`API_ENDPOINT` instead of `VITE_API_BASE_URL`. Ruff is required by docs but
not in requirements.

## Current state

- `client/vite.config.ts` line 10: proxied routes omit `/proxy-token`
- `README.md`: SECRET_KEY, `python -m app`
- `client/README.md`: API_ENDPOINT
- `Claude.md` / structure claims `docs/` which does not exist
- `server/requirements.txt` has no ruff

## Scope

**In scope**:
- `client/vite.config.ts`
- `README.md`
- `client/README.md`
- `Claude.md` and/or `CLAUDE.md` if present at root
- `server/README.md` (align start/test commands)
- `server/requirements.txt` (add ruff)
- Optional: `server/app/__main__.py` only if you choose to make `python -m app`
  work — **prefer documenting uvicorn/run.py** over adding __main__ unless trivial

**Out of scope**: CI workflow (plan 017)

## Steps

### Step 1: Vite proxy

Add `'/proxy-token'` to the `proxied` array in `vite.config.ts`.

**Verify**: file contains `/proxy-token`.

### Step 2: Root README

- Replace SECRET_KEY guidance with: copy `.env.example`, set `CORS_ORIGINS` for
  production, optional `GROQ_API_KEY` for subtitles.
- Start command: `uvicorn app.main:app --reload` or `python run.py` from
  `server/` (match `Claude.md`).
- Add short Testing section: `pytest`, `npm test`, `npm run check`, `ruff check app/`.

### Step 3: Client README

Document `VITE_API_BASE_URL` (empty in dev for Vite proxy; set for static split deploys).

### Step 4: Claude.md structure

Remove or fix the phantom `docs/` tree; point to root / server / client / deploy READMEs.
Add `pytest` and `npm test` to commands and release checklist.

### Step 5: Pin ruff

Add `ruff` to `server/requirements.txt` (pin a recent stable version, e.g. ruff>=0.8).

## Done criteria

1. `/proxy-token` in vite proxy list
2. No SECRET_KEY / API_ENDPOINT / python -m app falsehoods in primary READMEs
3. ruff listed in requirements
4. Claude structure matches repo

## STOP conditions

- Do not invent a SECRET_KEY feature that does not exist in config.py.
