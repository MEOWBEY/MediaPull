# Plan 009: Resolve `ctok` when unwrapping proxied URLs for transcription

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 86a449a..HEAD -- server/app/audio.py server/app/main.py server/app/jobs.py server/app/proxy.py client/src/lib/api/transcribe.ts server/tests/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none (001–008 already DONE)
- **Category**: bug
- **Planned at**: commit `86a449a`, 2026-07-16

## Why this matters

After plan 007, auth cookies live only as opaque `ctok` tokens on proxy URLs.
The browser player resolves them via `/proxy-video`. Transcription audio
acquisition unwraps `/proxy-video?...` and fetches the origin **directly**, but
only promotes the legacy `cookies=` query param — never `ctok`. Cookie-gated
videos therefore fail subtitle generation. This closes the auth contract for
auto-subtitles.

## Current state

- `server/app/audio.py` `_unwrap_proxied` (approx lines 197–228) recovers
  `url`, `referer`, `userAgent`, and legacy `cookies` from query string. No `ctok`.
- `server/app/proxy.py` `ProxyService._resolve_cookie_token(token)` returns the
  cookie blob or `""`.
- Client `client/src/lib/api/transcribe.ts` sends only `proxiedVideoUrl` (with
  `ctok` when tokens were minted). Comment incorrectly claims the proxy is reused.
- `main.py` `start_transcribe` never passes `ProxyService` into the job.
- `run_transcription_job` in `jobs.py` calls audio helpers that use `_unwrap_proxied`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Server tests | `cd server; python -m pytest -q` | all pass |
| Lint | `cd server; ruff check app/` (if ruff installed) | exit 0 or skip if missing |

## Scope

**In scope**:
- `server/app/audio.py`
- `server/app/jobs.py`
- `server/app/main.py`
- `server/app/proxy.py` (only if needed to expose a public resolve helper)
- `client/src/lib/api/transcribe.ts` (fix stale comment)
- `server/tests/test_unwrap_proxied.py` (create) or extend existing audio tests

**Out of scope**:
- SSRF hardening (plan 010)
- Gallery cookies (plan 013)
- Client token minting changes

## Git workflow

- Branch: worktree default / current
- Commit message style: imperative, e.g. `Fix transcription auth: resolve ctok when unwrapping proxy URLs`
- Do NOT push.

## Steps

### Step 1: Allow cookie-token resolution from unwrap

Make `_unwrap_proxied` accept an optional resolver:

```python
def _unwrap_proxied(
    url: str,
    *,
    resolve_cookie_token: Callable[[str], str] | None = None,
) -> tuple[str, dict[str, str]]:
    ...
    ctok = (qs.get("ctok") or [None])[0]
    if ctok and resolve_cookie_token is not None:
        cookies = resolve_cookie_token(ctok)
        if cookies:
            headers["Cookie"] = cookies
    elif qs.get("cookies"):
        headers["Cookie"] = qs["cookies"][0]
    return real, headers
```

Thread `resolve_cookie_token=proxy._resolve_cookie_token` from `main.py` →
`run_transcription_job` → every call path that unwraps URLs in `audio.py`
(`plan_acquisition` / acquire helpers). Prefer passing a bound method rather
than importing ProxyService into audio (keep layering clean).

**Verify**: grep shows `ctok` handled in `audio.py` and a resolver parameter reaches acquire.

### Step 2: Wire from main/jobs

- `run_transcription_job(..., resolve_cookie_token=None)`
- `main.py` passes `app.state.proxy._resolve_cookie_token` (or a thin public
  method `resolve_cookie_token` if you prefer not to use a private method —
  adding `def resolve_cookie_token(self, token: str) -> str: return self._resolve_cookie_token(token)` is fine).

**Verify**: app still imports; no circular import.

### Step 3: Tests

Add unit tests that construct a fake proxy-video URL with `ctok=abc` and a
resolver returning `"session=1"`, assert Cookie header is set. Also assert
legacy `cookies=` still works. Also assert missing/expired token yields no Cookie.

**Verify**: `python -m pytest -q server/tests/test_unwrap_proxied.py` (or wherever tests live) passes.

### Step 4: Fix client comment

Update the comment in `transcribe.ts` to say the server unwraps the proxy URL
and resolves `ctok` server-side for direct origin fetch.

**Verify**: comment accurate.

## Test plan

- Unit: unwrap with ctok + resolver
- Unit: unwrap without ctok, with cookies=
- Unit: unwrap non-proxy URL unchanged
- Existing job/proxy tests still pass

## Done criteria

1. `_unwrap_proxied` resolves `ctok` via injectable resolver
2. `POST /transcribe` path wires ProxyService resolver into jobs/audio
3. New tests pass; full `pytest -q` green
4. No raw cookies re-added to client-visible URLs

## STOP conditions

- If audio acquisition no longer unwraps and always hits the proxy instead —
  that is an alternate design; STOP and report rather than half-implement both.
- If ProxyService is not available on app.state at job start — STOP.

## Maintenance note

Any future change that moves cookies off `ctok` must update unwrap + this test.
"""
