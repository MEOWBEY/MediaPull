# Plan 017: CI workflow + characterization tests for hot paths

> **Drift check**: `git diff --stat 86a449a..HEAD -- .github/ server/tests/ client/tests/ server/requirements.txt`

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: prefer after 009–015 land so tests lock new behavior; can land earlier with baseline only
- **Category**: tests / dx
- **Planned at**: commit `86a449a`, 2026-07-16

## Why this matters

No CI. Hot paths (gallery parse, ASGI routes, transform, serializers) lack tests.

## Scope

**In scope**:
- `.github/workflows/ci.yml`
- `server/tests/` — ASGI health, proxy-token, gallery parse, serializers cookie strip
- `client/tests/` — transform + subtitle-utils if not already
- pin ruff if not done in 012

**Out of scope**: E2E Playwright full browser suite

## Steps

### Step 1: GitHub Actions

On push/PR:
- Python 3.12: install requirements, ruff check app/, pytest
- Node 22: npm ci, check, lint, test, build in client/

### Step 2: Server tests

- `TestClient`/`httpx.ASGITransport` for `/health`
- Gallery `_parse_dump_json` fixture
- Serializer strips Cookie
- Proxy handle scheme/disabled if easy with mocks

### Step 3: Client tests

- `transform` builds proxied URL structure from fixture
- Existing tests remain green

## Done criteria

CI file present; new tests pass locally; full suites green.

## STOP conditions

- Do not require secrets in CI for Groq.
