# Plan 007: Stop putting raw auth cookies in the proxy URL (they leak into copy/QR/share links)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. This plan has a **decision point in Step 1**: read
> it before writing any code. When done, update the status row for this plan in
> `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: written against the **working tree** at commit
> `a225b1c` with uncommitted changes applied to `server/app/proxy.py` and
> `client/src/lib/*`. `git diff a225b1c..HEAD` shows nothing — do NOT trust it.
> Open the files and compare against the "Current state" excerpts. On any
> mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/001-test-baseline.md, plans/002-cors-credentials-collision.md
- **Category**: security
- **Planned at**: commit `a225b1c` (+ uncommitted working-tree changes), 2026-07-13

## Why this matters

Authentication cookies for a source site are placed **in the query string** of
the proxied media URL:

- Client: `proxy-url.ts:59` — `if (cookies) {params.set('cookies', cookies);}`
- Server: `proxy.py:141` reads `cookies = q.get("cookies")`, sends them as the
  upstream `Cookie` header, and `_rewrite_hls` re-embeds them in every rewritten
  segment/playlist URL (`proxy.py:193`).

That same builder (`buildProxiedUrl`) produces `proxiedVideoUrl` for **every**
format (`transform.ts:73`), subtitle track (`transform.ts:93`), and gallery
image (`transform.ts:179`). Those URLs are not just fed to the `<video>` element
— they are the exact strings the app offers for **Copy link**, **QR code**, and
**export** (see `export.ts` and `VideoCard.svelte`). So a user who copies a link
or shares a QR code to play something on their phone is handing out their
logged-in session cookies for Instagram/X/YouTube in plaintext, where they also
land in server access logs, browser history, and any intermediary. A leaked
session cookie is a full account-takeover primitive.

The fix: the client sends cookies to the server **once**, gets back an opaque,
short-lived token, and the proxy URL carries the *token* instead of the raw
cookie blob. Shareable links then contain a token that expires and reveals
nothing.

## Current state

`client/src/lib/proxy-url.ts:40-62` (the builder — full current body):
```typescript
export function buildProxiedUrl(
	sourceUrl: string | undefined,
	httpHeaders: Headers,
	protocol: string | undefined
): string {
	if (!sourceUrl) {return '';}

	const params = new URLSearchParams({
		url: sourceUrl,
		protocol: protocol || 'https'
	});

	const userAgent = pick(httpHeaders, 'User-Agent', 'user-agent');
	const referer = pick(httpHeaders, 'Referer', 'referer');
	const cookies = pick(httpHeaders, 'Cookie', 'cookie');

	if (userAgent) {params.set('userAgent', userAgent);}
	if (referer) {params.set('referer', referer);}
	if (cookies) {params.set('cookies', cookies);}

	return `${proxyOrigin()}/proxy-video?${params.toString()}`;
}
```

`server/app/proxy.py:127-151` (server reads `cookies` from the query):
```python
        q = request.query_params
        source = q.get("url")
        protocol = q.get("protocol") or ""
        ...
        referer = q.get("referer") or ""
        cookies = q.get("cookies") or ""
        ...
        if cookies:
            upstream_headers["Cookie"] = cookies
```

`server/app/proxy.py:187-196` (`_handle_playlist` re-embeds cookies in every
rewritten URL via `passthrough`):
```python
        passthrough: dict[str, str] = {}
        if q.get("userAgent"):
            passthrough["userAgent"] = q["userAgent"]
        if q.get("referer"):
            passthrough["referer"] = q["referer"]
        if q.get("cookies"):
            passthrough["cookies"] = q["cookies"]
```

`buildProxiedUrl` call sites (all in `client/src/lib/transform.ts`):
- `:73` `proxiedVideoUrl: buildProxiedUrl(format.sourceVideoUrl, format.httpHeaders, format.protocol)`
- `:93` subtitle track url
- `:179` gallery image url

**Repo conventions**:
- Server routes live in `main.py`'s `create_app()`; the proxy is a class
  (`ProxyService`) held on `app.state.proxy`. In-memory per-process state on the
  service is already the pattern (`JobStore` is in-memory, single-worker deploy
  is assumed — see the comment at `main.py:243-245`). A token map on
  `ProxyService` fits this.
- Client API calls go through `$lib/api/client.ts` (`post`/`get` helpers);
  reuse them, don't hand-roll `fetch`.
- Tokens/ids in this codebase use `uuid.uuid4().hex` (`jobs.py:84`). Match it.
- No secret values in code or logs. Do NOT log cookie blobs or token→cookie maps.

## Commands you will need

| Purpose         | Command                                        | Expected on success |
|-----------------|------------------------------------------------|---------------------|
| Backend tests   | `cd server && python -m pytest -q`             | exit 0, all pass    |
| Backend lint    | `cd server && ruff check app/`                 | exit 0              |
| Frontend tests  | `cd client && npm test`                        | exit 0, all pass    |
| Typecheck       | `cd client && npm run check`                   | exit 0              |
| Frontend lint   | `cd client && npm run lint`                    | exit 0              |

## Step 1 — DECISION POINT (read before coding)

Two viable approaches. **Recommended: A.** Confirm A is acceptable in your
environment before proceeding; if the single-worker assumption is false, use B
and note it.

- **A — ephemeral in-memory token (recommended).** `POST /proxy-token` with
  `{cookies}` → returns `{token}`; `ProxyService` stores `token → cookies` in a
  TTL'd in-memory dict. The proxy URL carries `?ctok=<token>`; the server looks
  it up and injects the `Cookie` header. Rewritten HLS URLs pass the *token*
  through, never the cookies. Works because the deploy is single-worker
  (`main.py:243-245`). **Blast radius: `proxy.py`, `main.py` (one route),
  `models.py` (one request/response model), `proxy-url.ts`, and `transform.ts`
  (make the builder async or resolve tokens before building).**

- **B — signed token, no server state.** HMAC-sign `{cookies, exp}` with
  `SECRET_KEY` into the token. No dict, survives multiple workers, but the
  ciphertext still travels in the URL (encrypted, not plaintext) and needs a
  `SECRET_KEY` setting. Choose only if multi-worker is required.

If neither is acceptable (e.g. product wants zero server round-trip), STOP and
report — do not silently keep cookies in the URL.

The remaining steps assume **A**.

## Scope

**In scope**:
- `server/app/proxy.py` — token store on `ProxyService`, `create_token`,
  resolve `ctok` in `handle`, pass token (not cookies) in `passthrough`.
- `server/app/main.py` — one new `POST /proxy-token` route.
- `server/app/models.py` — `ProxyTokenRequest` / `ProxyTokenResponse`.
- `client/src/lib/proxy-url.ts` — stop writing `cookies=`; accept a token.
- `client/src/lib/transform.ts` — obtain/attach the token at the 3 call sites.
- `client/src/lib/api/*` — a `createProxyToken` client call.
- Tests: `server/tests/test_proxy_token.py` (create),
  `client/tests/proxy-url.test.ts` (extend — plan 001 created it).
- `plans/README.md`.

**Out of scope**:
- `userAgent` / `referer` params — those are not secret; leave them in the URL.
- The extraction cookie flow (`extraction.svelte.ts:196`, `/extract-videos`
  body) — that already sends cookies in a POST body, which is fine. Do NOT
  touch it.
- `CookiesPanel.svelte` and the client cookie store — unchanged.
- SSRF redirect hardening — that's plan 004; do not merge concerns.

## Git workflow

- Branch: `improve/007-cookies-out-of-proxy-url`
- Commit message: `Security: exchange proxy cookies for an ephemeral token, keep them out of URLs`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 2: Server — token store + `create_token` on `ProxyService`

In `ProxyService.__init__` add an in-memory store with TTL entries:
```python
        # token -> (cookie_blob, expiry_monotonic). Keeps auth cookies out of
        # the proxy URL (URLs get copied/QR'd/shared); the token is opaque and
        # short-lived. Single-worker deploy assumed (see main.py).
        self._cookie_tokens: dict[str, tuple[str, float]] = {}
        self._token_ttl = 3600.0
```
Add methods (use `uuid.uuid4().hex`, `time.monotonic()`; add `import time`,
`import uuid` if absent):
```python
    def create_cookie_token(self, cookies: str) -> str:
        self._sweep_tokens()
        token = uuid.uuid4().hex
        self._cookie_tokens[token] = (cookies, time.monotonic() + self._token_ttl)
        return token

    def _resolve_cookie_token(self, token: str) -> str:
        entry = self._cookie_tokens.get(token)
        if entry is None:
            return ""
        cookies, expiry = entry
        if time.monotonic() > expiry:
            self._cookie_tokens.pop(token, None)
            return ""
        return cookies

    def _sweep_tokens(self) -> None:
        now = time.monotonic()
        for tok in [t for t, (_, exp) in self._cookie_tokens.items() if now > exp]:
            self._cookie_tokens.pop(tok, None)
```

### Step 3: Server — accept `ctok` in `handle`, drop raw `cookies` from passthrough

In `handle` (`proxy.py:140-151`), replace the raw-cookie read with token
resolution, but keep backward-compat OFF (raw `cookies=` must no longer be
honored, or the leak persists via crafted URLs — reject/ignore it):
```python
        referer = q.get("referer") or ""
        ctok = q.get("ctok") or ""
        cookies = self._resolve_cookie_token(ctok) if ctok else ""
```
In `_handle_playlist`'s `passthrough` (`proxy.py:187-193`), pass the **token**,
not the cookies:
```python
        if q.get("ctok"):
            passthrough["ctok"] = q["ctok"]
```
Remove the `if q.get("cookies")` passthrough branch.

### Step 4: Server — `POST /proxy-token` route + models

In `models.py`, add (match the existing pydantic model style in that file):
```python
class ProxyTokenRequest(BaseModel):
    cookies: str

class ProxyTokenResponse(BaseModel):
    token: str
```
In `main.py`, add a route near the other `app.state.proxy` usage:
```python
    @app.post("/proxy-token", response_model=ProxyTokenResponse)
    async def proxy_token(payload: ProxyTokenRequest) -> ProxyTokenResponse:
        return ProxyTokenResponse(token=app.state.proxy.create_cookie_token(payload.cookies))
```
Import the two models in `main.py`'s model import block (`main.py:28-39`).

**Verify**: `cd server && ruff check app/` → 0; `cd server && python -m pytest -q` → passing (existing + new tests below).

### Step 5: Client — builder stops emitting `cookies=`, takes an optional token

Change `buildProxiedUrl` (`proxy-url.ts`) to drop the `cookies` param entirely
and accept an optional pre-fetched token:
```typescript
export function buildProxiedUrl(
	sourceUrl: string | undefined,
	httpHeaders: Headers,
	protocol: string | undefined,
	cookieToken?: string | null
): string {
	if (!sourceUrl) {return '';}
	const params = new URLSearchParams({ url: sourceUrl, protocol: protocol || 'https' });
	const userAgent = pick(httpHeaders, 'User-Agent', 'user-agent');
	const referer = pick(httpHeaders, 'Referer', 'referer');
	if (userAgent) {params.set('userAgent', userAgent);}
	if (referer) {params.set('referer', referer);}
	if (cookieToken) {params.set('ctok', cookieToken);}
	return `${proxyOrigin()}/proxy-video?${params.toString()}`;
}
```
The `cookies` local and the `pick(..., 'Cookie', ...)` line are removed.

### Step 6: Client — mint the token before building URLs

Add `createProxyToken(cookies: string): Promise<string>` to the API layer
(model after existing `post` usage in `$lib/api/client.ts`). In `transform.ts`,
where formats/tracks/images are built (`:73/:93/:179`), when the format carries
a `Cookie` header, exchange it for a token once and thread the token into
`buildProxiedUrl`. Because `transform.ts` currently builds URLs synchronously,
you must either (a) make the relevant transform async and await one
`createProxyToken` per unique cookie blob, or (b) fetch tokens up front in the
caller and pass them in. **Prefer (b)** if the transform is called in a
synchronous reactive context (Svelte `$derived`) — search for its callers first
(`grep -rn "transform" client/src/lib client/src/routes`) and STOP if making it
async would ripple into many `$derived`/`$effect` sites; report the caller shape
so the approach can be confirmed.

### Step 7: Tests

- `server/tests/test_proxy_token.py` (create): create a token, resolve it back
  to the cookie blob; an unknown token resolves to `""`; an expired token
  (monkeypatch `time.monotonic` or set `_token_ttl` to 0 and sweep) resolves to
  `""`. Model after `tests/test_jobstore.py`.
- `client/tests/proxy-url.test.ts` (extend the file plan 001 created): assert
  `buildProxiedUrl(url, {Cookie:'sid=abc'}, 'https')` output **does not contain
  `cookies=` and does not contain `sid=abc`**; assert a passed `cookieToken`
  shows up as `ctok=`. This flips the locked-in "no cookies in URL" assertion
  from plan 001 green.

**Verify**: `cd server && python -m pytest -q` → 0; `cd client && npm test && npm run check && npm run lint` → all 0.

### Step 8: Update `plans/README.md`

Set this plan's row to `DONE`.

## Test plan

- Server: token round-trip, unknown token → empty, expired token → empty.
- Client: `buildProxiedUrl` never emits `cookies=`/raw cookie substrings; emits
  `ctok=` when given a token. This turns plan 001's locked-in
  `proxy-url.test.ts::does not include cookies in URL query` green.
- Manual smoke (note in PR, not automated): play an authenticated source, copy
  its link, confirm the copied URL has `ctok=` and no cookie material.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `cd server && python -m pytest -q` exits 0
- [ ] `cd server && ruff check app/` exits 0
- [ ] `cd client && npm test` exits 0; the locked-in cookies-in-URL test passes
- [ ] `cd client && npm run check && npm run lint` exit 0
- [ ] `grep -n "cookies" client/src/lib/proxy-url.ts` returns nothing (param gone)
- [ ] `grep -n "q.get(\"cookies\")" server/app/proxy.py` returns nothing
- [ ] `grep -n "proxy-token" server/app/main.py` shows the new route
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated to `DONE`

## STOP conditions

Stop and report back (do not improvise) if:
- Files don't match the "Current state" excerpts (working tree drift).
- The deploy is confirmed multi-worker (`WORKERS>1` in prod config) — the
  in-memory token map won't work across workers; switch to approach B and note it.
- Making `transform.ts` token-aware would require converting many `$derived`
  reactive computations to async (ripple risk) — report the caller shape and the
  chosen approach before proceeding.
- Any existing test that asserts `cookies=` is present starts failing in a way
  that implies another code path still needs raw cookies in the URL.

## Maintenance notes

- A reviewer must confirm raw `cookies=` is **no longer honored** server-side
  (not merely un-sent by the client) — otherwise a hand-crafted URL re-opens the
  leak.
- Token TTL (3600s) should comfortably exceed a playback session; if long
  streams get 403s on segment fetches after an hour, the token expired mid-play
  — consider refresh-on-use (bump expiry in `_resolve_cookie_token`).
- If multi-worker is ever enabled, migrate to approach B (signed token) or a
  shared store; the in-memory map is the one thing tying this to single-worker.
- Deferred: encrypting cookies at rest in the token map (they're already
  process-memory-only and short-lived; encryption adds a key-management burden
  for marginal gain here).
