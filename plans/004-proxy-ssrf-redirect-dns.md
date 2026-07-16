# Plan 004: Re-check the destination host on every redirect hop and resolved IP in the media proxy

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: this plan was written against the **working
> tree** at commit `a225b1c` *with uncommitted changes already applied* to
> `server/app/proxy.py`. `git diff a225b1c..HEAD` will therefore show nothing
> even though the file differs from the committed blob. Do NOT trust the SHA
> diff — instead open `server/app/proxy.py` and compare it against the
> "Current state" excerpts below line-by-line. On any mismatch, treat it as a
> STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/001-test-baseline.md
- **Category**: security
- **Planned at**: commit `a225b1c` (+ uncommitted working-tree changes), 2026-07-13

## Why this matters

`GET /proxy-video` fetches an arbitrary, user-supplied `url` and streams the
bytes back. `ProxyService._check_host` (`proxy.py:87`) is the SSRF guard: it
rejects loopback / RFC-1918 / link-local destinations and (optionally) enforces
a host allow-list. But that check runs exactly **once, against the URL the
client sent** — and both outbound requests set `allow_redirects=True`
(`proxy.py:117`). So:

1. **Redirect bypass** — an allowed public host (`cdn.example.com`, or any host
   when no allow-list is configured, which is the *default*) can answer with a
   `302` to `http://169.254.169.254/…` (cloud metadata), `http://127.0.0.1:…`,
   or an internal `10.x` service. curl_cffi follows it transparently and the
   guard never sees the final URL. The proxy then streams the internal
   response back to the attacker.
2. **DNS-rebinding / literal bypass** — `_check_host` matches on the hostname
   *string*, never on the address it resolves to. A hostname like
   `rebind.attacker.example` that resolves to `127.0.0.1`, or an IPv4-mapped
   IPv6 literal (`::ffff:127.0.0.1`), or a bracketed IPv6 form, sails through.

The default deploy has `PROXY_ALLOWED_HOSTS` empty (`config.py:196`), so the
private-range string check is the *only* guard — and redirects defeat it
entirely. This plan closes both holes: follow redirects manually and re-run
`_check_host` on every hop, and strengthen `_check_host` to reject
IPv4-mapped/bracketed IPv6 and hostnames that *resolve* to a blocked address.

## Current state

- `server/app/proxy.py` — the media reverse-proxy. Relevant pieces:

`proxy.py:57-65` (private-IP helpers):
```python
# 172.16.0.0/12 = 172.16.0.0 – 172.31.255.255
_PRIVATE_172_PREFIXES = tuple(f"172.{i}." for i in range(16, 32))


def _is_private_172(hostname: str) -> bool:
    """True when *hostname* is inside the 172.16.0.0/12 private range."""
    return hostname.startswith(_PRIVATE_172_PREFIXES)
```

`proxy.py:87-114` (`_check_host` — the guard, string-based only):
```python
    def _check_host(self, url: str) -> bool:
        """True if this destination is allowed (config host allow-list, or no
        list is configured). Returns False for internal/private IPs regardless
        of allow-list status."""
        try:
            hostname = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        if not hostname:
            return False
        # Always reject loopback / private-ranges / link-local —
        # the proxy has no reason to fetch from internal networks.
        if (
            hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
            or hostname.startswith("10.")
            or hostname.startswith("192.168.")
            or _is_private_172(hostname)
            or hostname.startswith("169.254.")
            or hostname == "[::1]"
        ):
            return False
        if self._allowed_hosts:
            # Suffix match: "googlevideo.com" matches "r1---sn-abc.googlevideo.com"
            return any(
                hostname == allowed or hostname.endswith("." + allowed)
                for allowed in self._allowed_hosts
            )
        return True
```

`proxy.py:116-119` (redirects enabled — the hole):
```python
    def _request_kwargs(self, headers: dict[str, str]) -> dict:
        kwargs: dict = {"headers": headers, "allow_redirects": True}
        kwargs.update(self._impersonate_kw)
        return kwargs
```

Both `_handle_playlist` (`proxy.py:171-206`) and `_handle_stream`
(`proxy.py:210-258`) call `self._session.get(source, **self._request_kwargs(...))`.
`urlparse` is already imported at `proxy.py:22`.

**Note on `urlparse(...).hostname`**: for `http://[::1]/x` it returns `"::1"`
(brackets stripped), so the existing `hostname == "[::1]"` branch is dead but
harmless — leave it. For `http://[::ffff:127.0.0.1]/x` it returns
`"::ffff:127.0.0.1"`, which today passes the guard. That is one of the gaps.

**Repo conventions to follow**:
- Backend is FastAPI + `async`/`await`; blocking calls must not run on the event
  loop. DNS resolution (`socket.getaddrinfo`) is blocking — run it via
  `asyncio.get_running_loop().run_in_executor(None, …)` (no new thread pool).
- Errors are surfaced as `JSONResponse({"error": …}, status_code=…)`, matching
  the existing 403/502 responses in this file.
- Logging uses the module logger `logger = logging.getLogger("pullbox.proxy")`
  with `logger.warning(...)`; match it. Do NOT log the full internal URL at
  `info` level (it may contain cookies in the query — see plan 007).
- Standard library only (`ipaddress`, `socket`, `asyncio`) — do NOT add a new
  dependency.

## Commands you will need

| Purpose        | Command                                        | Expected on success |
|----------------|------------------------------------------------|---------------------|
| Backend tests  | `cd server && python -m pytest -q`             | exit 0, all pass    |
| This file only | `cd server && python -m pytest tests/test_proxy_host_check.py -q` | exit 0 |
| Backend lint   | `cd server && ruff check app/`                 | exit 0              |

## Scope

**In scope** (the only files you should modify or create):
- `server/app/proxy.py` — `_check_host` (strengthen), a new
  `_resolve_and_check` async helper, a new manual-redirect helper, and the two
  call sites in `_handle_playlist` / `_handle_stream`.
- `server/tests/test_proxy_host_check.py` — extend (created by plan 001).
- `plans/README.md` — mark this plan's row.

**Out of scope** (do NOT touch, even though they look related):
- `server/app/extractor.py` `_direct_video` / `_probe_ok` / `_scrape` — those
  also fetch user URLs with redirects, but extraction is the app's explicit
  purpose (the user pastes a page URL knowing the server fetches it) and it does
  not stream arbitrary internal responses back verbatim the way the proxy does.
  A separate hardening pass can cover them; bundling them here widens blast
  radius and risks breaking extraction. If you believe extraction is exploitable
  the same way, note it and STOP — do not fix it here.
- `_download_filename`, `_rewrite_hls`, header forwarding — unrelated.
- The `PROXY_ALLOWED_HOSTS` / `PROXY_ENABLED` config — leave as-is; this plan
  hardens the guard that runs *when no allow-list is set*.

## Git workflow

- Branch: `improve/004-proxy-ssrf-redirect-dns`
- Commit message: `Security: re-check proxy host on redirects and resolved IPs`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Add imports and a blocked-IP helper

At the top of `proxy.py`, add to the stdlib imports:
```python
import asyncio
import ipaddress
import socket
```
(Keep them grouped with the existing `import logging` / `import re`.)

Replace the private-IP helpers block (`proxy.py:57-65`) with an
`ipaddress`-based check that covers every private/reserved range in one place,
including IPv4-mapped IPv6:

```python
# ---- private-IP guards -------------------------------------------------


def _is_blocked_ip(host: str) -> bool:
    """True when *host* is an IP literal in a range the proxy must never reach.

    Covers loopback, RFC-1918 private, link-local, unique-local (fc00::/7),
    unspecified (0.0.0.0/::), and IPv4-mapped IPv6 (::ffff:10.0.0.1). Returns
    False when *host* is not an IP literal (a DNS name) — those are resolved
    separately in `_resolve_and_check`.
    """
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    # Unwrap IPv4-mapped / 6to4 so ::ffff:127.0.0.1 is judged as 127.0.0.1.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_unspecified
        or ip.is_multicast
    )
```

Delete `_PRIVATE_172_PREFIXES` and `_is_private_172`.

**STOP** if `_is_private_172` is imported anywhere outside `proxy.py` — grep
first: `grep -rn "_is_private_172" server/`. Plan 001's
`test_proxy_host_check.py` imports it; you will replace that test in Step 4, so
that reference is expected. Any *source* import outside `proxy.py` is a STOP.

**Verify**: `cd server && python -c "from app.proxy import _is_blocked_ip; assert _is_blocked_ip('::ffff:127.0.0.1') and _is_blocked_ip('10.0.0.1') and _is_blocked_ip('169.254.1.1') and not _is_blocked_ip('8.8.8.8') and not _is_blocked_ip('example.com')"` → exits 0, no output.

### Step 2: Make `_check_host` use the new helper (still synchronous, string/literal layer)

Rewrite `_check_host` so the private-range decision goes through
`_is_blocked_ip`, keeping the allow-list logic intact:

```python
    def _check_host(self, url: str) -> bool:
        """True if this destination's *hostname* is allowed. String-level guard
        only — IP-literal ranges and the allow-list. DNS names are resolved and
        re-checked in `_resolve_and_check`."""
        try:
            hostname = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        if not hostname:
            return False
        if hostname == "localhost" or _is_blocked_ip(hostname):
            return False
        if self._allowed_hosts:
            return any(
                hostname == allowed or hostname.endswith("." + allowed)
                for allowed in self._allowed_hosts
            )
        return True
```

**Verify**: `cd server && python -m pytest tests/test_proxy_host_check.py -q` — expect failures ONLY for tests that reference the deleted `_is_private_172` (fixed in Step 4); the loopback/private/allow-list cases must still pass.

### Step 3: Add async resolve-and-check, and manual redirect following

Add two methods to `ProxyService`. The first resolves a hostname and rejects it
if *any* resolved address is blocked (kills DNS rebinding). The second replaces
`allow_redirects=True` with a bounded manual loop that re-checks every hop.

```python
    async def _resolve_and_check(self, url: str) -> bool:
        """Re-check `_check_host`, then resolve the hostname and reject if any
        resolved address is a blocked (internal) IP. DNS lookup is blocking, so
        it runs in the default executor."""
        if not self._check_host(url):
            return False
        hostname = (urlparse(url).hostname or "").lower()
        # An IP literal was already fully judged by `_check_host`.
        try:
            ipaddress.ip_address(hostname)
            return True
        except ValueError:
            pass
        loop = asyncio.get_running_loop()
        try:
            infos = await loop.run_in_executor(
                None, socket.getaddrinfo, hostname, None
            )
        except socket.gaierror:
            # Can't resolve → let the actual request fail loudly upstream,
            # rather than silently allowing. Reject.
            return False
        return not any(_is_blocked_ip(str(info[4][0])) for info in infos)

    async def _get_checked(self, url: str, *, stream: bool, headers: dict[str, str]):
        """Like `session.get(..., allow_redirects=True)` but re-runs the SSRF
        guard on every redirect hop (default is off; we follow by hand). Returns
        the final curl_cffi response, or raises `PermissionError` if any hop
        targets a disallowed host."""
        current = url
        for _ in range(self._MAX_REDIRECTS):
            if not await self._resolve_and_check(current):
                raise PermissionError(current)
            kwargs = dict(self._impersonate_kw)
            resp = await self._session.get(
                current, headers=headers, allow_redirects=False,
                stream=stream, **kwargs,
            )
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                await resp.aclose()
                if not location:
                    raise PermissionError(current)
                current = urljoin(current, location)
                continue
            return resp
        raise PermissionError(current)
```

Add a class constant near the top of `ProxyService.__init__` or as a class
attribute: `_MAX_REDIRECTS = 5`. `urljoin` is already imported (`proxy.py:22`).

`_request_kwargs` is now only used by the manual loop's non-redirect concerns;
since `_get_checked` builds kwargs inline, **delete `_request_kwargs`** (`proxy.py:116-119`)
and update the two call sites in the next step.

### Step 4: Switch both handlers to `_get_checked`

In `_handle_playlist` (`proxy.py:171-206`), replace:
```python
        try:
            resp = await self._session.get(source, **self._request_kwargs(headers))
        except Exception as exc:  # noqa: BLE001 - surface any transport error
            logger.warning("playlist proxy request failed for %s: %s", source, exc)
            return JSONResponse({"error": f"Upstream error: {exc}"}, status_code=502)
```
with:
```python
        try:
            resp = await self._get_checked(source, stream=False, headers=headers)
        except PermissionError:
            logger.warning("playlist proxy blocked disallowed redirect target")
            return JSONResponse(
                {"error": "Proxying to this host is not allowed"}, status_code=403
            )
        except Exception as exc:  # noqa: BLE001 - surface any transport error
            logger.warning("playlist proxy request failed for %s: %s", source, exc)
            return JSONResponse({"error": f"Upstream error: {exc}"}, status_code=502)
```

In `_handle_stream` (`proxy.py:210-258`), replace the `self._session.get(source, stream=True, **self._request_kwargs(headers))`
call the same way, using `stream=True` and the same `PermissionError` → 403 /
`Exception` → 502 handling.

The top-level `handle()` (`proxy.py:134`) already calls `_check_host(source)`
before dispatching — leave that as a cheap fast-path reject; `_get_checked`
re-checks the first hop anyway so there is no gap.

**Verify**: `cd server && ruff check app/` → exit 0.

### Step 5: Replace the plan-001 host-check test with resolved-IP coverage

Plan 001's `tests/test_proxy_host_check.py` imports `_is_private_172` (now
deleted). Rewrite that file to import `_is_blocked_ip` and cover the new cases.
Match the existing pytest style (`asyncio_mode = auto`, `Settings()` fixture):

```python
import pytest
from app.proxy import ProxyService, _is_blocked_ip
from app.config import Settings


@pytest.fixture
def proxy():
    return ProxyService(Settings())


@pytest.mark.parametrize("host", [
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
    "10.0.0.1", "192.168.1.5", "172.16.5.5", "172.31.255.254",
    "169.254.0.1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "fc00::1",
])
def test_blocked_loopback_and_private(proxy, host):
    assert proxy._check_host(f"http://{host}/x") is False


def test_is_blocked_ip_edges():
    assert _is_blocked_ip("172.16.0.1") and _is_blocked_ip("172.31.255.255")
    assert not _is_blocked_ip("172.15.0.1") and not _is_blocked_ip("172.32.0.1")
    assert not _is_blocked_ip("8.8.8.8")
    assert not _is_blocked_ip("example.com")  # not an IP literal


def test_allowed_when_no_allowlist(proxy):
    assert proxy._check_host("https://cdn.example.com/file.mp4") is True


def test_allowed_hosts_match_subdomains_and_exact():
    p = ProxyService(Settings())
    p._allowed_hosts = ["googlevideo.com"]
    assert p._check_host("https://r1---sn-abc.googlevideo.com/v.mp4") is True
    assert p._check_host("https://googlevideo.com/v.mp4") is True


def test_disallows_lookalike_suffix():
    p = ProxyService(Settings())
    p._allowed_hosts = ["googlevideo.com"]
    assert p._check_host("https://googlevideo.com.evil.example/x") is False
    assert p._check_host("https://evilgooglevideo.com/x") is False


@pytest.mark.asyncio
async def test_resolve_and_check_rejects_rebind(proxy, monkeypatch):
    """A public hostname that resolves to a loopback address is rejected."""
    def fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("127.0.0.1", 0))]
    import app.proxy as proxy_mod
    monkeypatch.setattr(proxy_mod.socket, "getaddrinfo", fake_getaddrinfo)
    assert await proxy._resolve_and_check("https://rebind.example.com/x") is False


@pytest.mark.asyncio
async def test_resolve_and_check_allows_public(proxy, monkeypatch):
    def fake_getaddrinfo(host, port):
        return [(2, 1, 6, "", ("93.184.216.34", 0))]
    import app.proxy as proxy_mod
    monkeypatch.setattr(proxy_mod.socket, "getaddrinfo", fake_getaddrinfo)
    assert await proxy._resolve_and_check("https://example.com/x") is True
```

**Verify**: `cd server && python -m pytest tests/test_proxy_host_check.py -q` → all pass. Then `cd server && python -m pytest -q` → the whole suite passes (no other file references the removed symbols).

### Step 6: Update `plans/README.md`

Set this plan's row to `DONE`.

## Test plan

- New/updated tests in `server/tests/test_proxy_host_check.py`:
  - IPv4-mapped IPv6 literals (`::ffff:127.0.0.1`, `::ffff:10.0.0.1`) and
    unique-local (`fc00::1`) are blocked — the pre-fix gap.
  - `_is_blocked_ip` boundary cases at the 172.16/12 edges.
  - `_resolve_and_check` rejects a hostname resolving to loopback (DNS rebind)
    and allows one resolving to a public IP — both via monkeypatched
    `socket.getaddrinfo` (no real DNS in tests).
  - Existing allow-list / lookalike-suffix cases still pass.
- Model the test structure after the existing `tests/test_proxy_host_check.py`
  from plan 001.
- Redirect-hop re-checking is covered indirectly (the `PermissionError` → 403
  path); a full redirect integration test needs a live curl_cffi mock and is
  explicitly deferred (see Maintenance notes) to keep this plan's tests offline.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `cd server && python -m pytest -q` exits 0, all tests pass
- [ ] `cd server && ruff check app/` exits 0
- [ ] `grep -n "_is_private_172" server/app/proxy.py` returns nothing
- [ ] `grep -n "allow_redirects=True" server/app/proxy.py` returns nothing (redirects are now manual)
- [ ] `grep -n "_get_checked" server/app/proxy.py` shows the helper and both call sites
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated to `DONE`

## STOP conditions

Stop and report back (do not improvise) if:
- `server/app/proxy.py` does not match the "Current state" excerpts (working
  tree drifted since this plan was written).
- Removing `allow_redirects` breaks a legitimate playback flow you can observe
  (e.g. a CDN that 302s within the *same* allowed host and now 403s) — the host
  re-check should permit same-host redirects; if it doesn't, the resolve logic
  is wrong, escalate rather than loosen the guard.
- `_is_private_172` is imported by a source file other than `proxy.py`.
- curl_cffi's `AsyncSession.get` does not accept `allow_redirects=False` /
  `stream=` as written in this repo's version — verify against
  `_handle_stream`'s existing usage before assuming the signature.
- You find extraction (`extractor.py`) is exploitable the same way — note it,
  do NOT fix it here.

## Maintenance notes

- A reviewer should confirm redirects are now followed *manually* and
  `_check_host`/`_resolve_and_check` runs on the pre-redirect URL of every hop,
  not just the client-supplied one.
- `socket.getaddrinfo` runs on the default executor (blocking) — if the proxy
  ever moves to a fully non-blocking DNS resolver, keep the resolved-IP block.
- There is a residual TOCTOU window between resolve and connect (curl_cffi
  re-resolves on its own connect). Fully closing it requires pinning the
  resolved IP into the connection (custom resolver / connecting by IP with SNI),
  which curl_cffi doesn't expose cleanly — deferred deliberately. The redirect
  + resolve checks stop the overwhelming majority of practical SSRF; document
  this residual in `KNOWN_ISSUES.md` if you want it tracked.
- Deferred: a redirect-following integration test with a mocked session, and
  applying the same guard to `extractor.py`'s fetch paths.
