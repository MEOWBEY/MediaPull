# Plan 002: Fix silent CORS `*` + `allow_credentials=True` collision

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a225b1c..HEAD -- server/app/main.py server/app/config.py`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-test-baseline.md
- **Category**: security
- **Planned at**: commit `a225b1c`, 2026-07-13

## Why this matters

`main.py:142–148` registers `CORSMiddleware(allow_origins=settings.cors_origins, allow_credentials=True, …)`. When `CORS_ORIGINS` is unset (the default — `"*"` per `config.py:21,203-205`) the effective origin list is `["*"]`. **Browsers reject `Access-Control-Allow-Origin: *` together with credentials by spec** — they drop the response entirely. Starlette emits no warning, FastAPI returns no error; the user sees "auth keeps failing." In split-host deploys (where the SPA is on a different origin than the API, e.g. `app.example.com` → `api.example.com`) every credentialed request fails silently. The fix is small and well-bounded: drop credentials when the list contains `*`, and document the contract.

## Current state

**Relevant code** (verified excerpts):

`server/app/main.py:142-148`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
```

`server/app/config.py:21`:
```python
cors_origins_raw: str = Field(default="*", alias="CORS_ORIGINS")
```

`server/app/config.py:203-205`:
```python
@property
def cors_origins(self) -> list[str]:
    return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()] or ["*"]
```

References:
- Plan 001 created `server/tests/test_cors_settings.py::test_cors_does_not_silently_combine_wildcard_with_credentials` which ASSERTS the post-fix behavior — it currently fails with `AssertionError: Wildcard origin + credentials is invalid...` and will turn green as a regression screen.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Tests | `cd server && python -m pytest -q` | exit 0; the locked-in CORS test flips green |
| Lint  | `ruff check app/`        | exit 0 |
| Smoke | `python -c "from app.config import Settings; from app.main import create_app; from fastapi.testclient import TestClient; c = TestClient(create_app()); mws = [(m.cls.__name__, m.options) for m in c.app.user_middleware if m.cls.__name__=='CORSMiddleware']; print(mws)"` | prints `('CORSMiddleware', {...'allow_credentials': False, 'allow_origins': ['*']...})` when CORS_ORIGINS unset |

## Scope

**In scope**:
- `server/app/main.py` (the `add_middleware` block only)
- `server/tests/test_cors_settings.py` (test written by plan 001)
- `server/.env.example` — add a clarifying comment
- `server/README.md` — add the same clarifying note if it documents CORS (read first)

**Out of scope**:
- The `cors_origins` property itself — leave the default behaviour unchanged.
- Other middlewares (GZip, LogContext).
- Client-side — this is a server-only fix.

## Git workflow

- Branch: `improve/002-cors-credentials-collision`
- Commit message: `Security: drop credentials when CORS_ORIGINS is wildcard`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Compute credentials=flag from the resolved origin list

In `server/app/main.py`'s `create_app()`, compute `allow_credentials_effective` and pass it to the middleware:

```python
origins = settings.cors_origins
wildcard = "*" in origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    # Browsers reject `Access-Control-Allow-Origin: *` with credentials; only
    # allow credentials when the operator pinned an explicit origin list.
    allow_credentials=not wildcard and len(origins) > 0,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)
```

Module-level reasoning: previously `settings.cors_origins` was inlined into the call; lifting it into a local var keeps the conditional readable.

### Step 2: Verify the locked-in test flips green

```
cd server && python -m pytest tests/test_cors_settings.py -v
```

Expected: `1 passed` (the prior `AssertionError` is gone) and **0 failures** across the rest of the suite.

### Step 3: Add one explicit happy-path test

Append to `server/tests/test_cors_settings.py`:

```python
def test_credentials_enabled_when_origin_pinned(monkeypatch):
    """When CORS_ORIGINS pins a specific origin, allow_credentials must stay True."""
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    # Bust lru_cache on get_settings to pick the env up:
    from app import config as cfg
    cfg.get_settings.cache_clear()
    from fastapi.testclient import TestClient
    client = TestClient(create_app())
    found = False
    for mw in client.app.user_middleware:
        if mw.cls.__name__ == "CORSMiddleware":
            found = True
            assert mw.options.get("allow_credentials") is True
            assert mw.options.get("allow_origins") == ["https://app.example.com"]
    assert found, "CORSMiddleware not registered"
```

Run: `python -m pytest tests/test_cors_settings.py -v` → `2 passed`.

### Step 4: Update `server/.env.example`

Find the `CORS_ORIGINS` line and add:
```
# Comma-separated list, e.g. "https://app.example.com,https://other.example.com"
# Wildcard ("*") disables credentials automatically (browsers reject
# Access-Control-Allow-Origin: * with credentials, so any cross-origin
# credentialed request fails silently). Pin explicit origins for auth.
```

Run `python -m pytest -q` once more to confirm nothing regressed.

### Step 5: Update `plans/README.md`

Set this plan's row to `DONE`.

## Test plan

- `tests/test_cors_settings.py::test_cors_does_not_silently_combine_wildcard_with_credentials` flips green.
- New `test_credentials_enabled_when_origin_pinned` passes.
- All other tests unchanged.

## Done criteria

- [ ] `cd server && python -m pytest -q` exits 0, all 8 test files green (including the new one)
- [ ] `ruff check app/` exits 0
- [ ] The smoke command in the verification table prints `allow_credentials: False` for wildcard and `True` for pinned origin
- [ ] `grep -n "CORS_ORIGINS" server/.env.example` shows the new clarifying comment
- [ ] `git status` shows only `server/app/main.py`, `server/tests/test_cors_settings.py`, `server/.env.example`, `plans/README.md` modified
- [ ] `plans/README.md` updated

## STOP conditions

Stop and report back (do not improvise) if:
- The new pinned-origin test fails after plan 002 lands — the change broke a different code path than intended.
- A locked-in test from plan 001 (other than CORS) starts failing — your edit leaked into unrelated code.
- The repo has additional middleware order assumptions (e.g. CORSMiddleware is registered twice) that this change broke.

## Maintenance notes

- Operators who want `credentials: true` MUST pin an explicit origin; the silent failure mode is now impossible from configuration. Document in `README.md`/`server/README.md` whenever deployment docs are touched.
- If a future change re-introduces a wildcard default (e.g. for local-develop convenience), keep the `allow_credentials=not wildcard` guard intact.
- A reviewer landing this PR should specifically check the diff does NOT touch GZipMiddleware or LogContextMiddleware.
