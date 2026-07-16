# Plan 003: Abort prior in-flight fetch in `ExtractionController`

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report — do not improvise. When done, update the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat a225b1c..HEAD -- client/src/lib/extraction.svelte.ts client/src/lib/components/InputUrl.svelte`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: MED
- **Depends on**: plans/001-test-baseline.md
- **Category**: bug
- **Planned at**: commit `a225b1c`, 2026-07-13

## Why this matters

`ExtractionController.start()` (at `client/src/lib/extraction.svelte.ts:384`) creates a fresh `AbortController` each call. If `run()` is invoked while a previous extract is still running (rapid paste + Enter, retry button, or batch re-entry), the old `AbortController` is overwritten **without its prior fetch being aborted**. The leaked request continues until the 3-minute timeout while the user thinks the new paste succeeded. Worse: `cancel()` (at line 323) flips `batchAborted` and calls `stop()`, which DOES set the signal aborted for the new request, but it lands AFTER the new fetch has already started — confusing the "running" state.

The fix is mechanical: capture the prior controller and abort it before allocating a new one. Tests verify the lifecycle (`plans/001` already created the locked-in `extraction-controller.test.ts`).

## Current state

**Relevant code** (verified excerpts):

`client/src/lib/extraction.svelte.ts:62`:
```typescript
private controller: AbortController | null = null;
```

`client/src/lib/extraction.svelte.ts:336-381` (`run()` excerpt):
```typescript
private async run<T>(config: { ... }): Promise<boolean> {
    this.start();
    appStore.isVideoExtractRunning = true;
    appStore.videoExtractError = null;

    const signal = this.controller?.signal;
    if (!signal) { ... }

    try {
      const result = await config.task(signal);
      if (this.controller?.signal.aborted) { return false; }
      config.onSuccess(result);
      return true;
    } catch (error) {
      if (error instanceof ApiError && error.aborted) { return false; }
      ...
    } finally {
      appStore.isVideoExtractRunning = false;
      this.stop();
    }
}
```

`client/src/lib/extraction.svelte.ts:384-398` (`start()` / `stop()`):
```typescript
private start(): void {
    this.controller = new AbortController();
    this.elapsedSeconds = 0;
    this.timer = setInterval(() => this.elapsedSeconds++, 1000);
}

private stop(): void {
    this.controller?.abort();
    this.controller = null;
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
}
```

References:
- Plan 001 created `client/tests/extraction-controller.test.ts` with a locked-in test that asserts `first.signal.aborted === true` after `start()` is called twice — currently fails.

**Repo conventions** (verified): code is `.svelte.ts` (Svelte 5 runes syntax — `$state`, `$derived` etc.), Tabs for indent, `'use strict'` not used; semicolons absent; const/let no-unused allow on private fields.

## Commands you will need

| Purpose   | Command                  | Expected on success |
|-----------|--------------------------|---------------------|
| Frontend tests | `cd client && npm test --silent` | exit 0; locked-in test flips green |
| Typecheck | `npm run check` | exit 0 |
| Lint | `npm run lint` | exit 0 |

## Scope

**In scope**:
- `client/src/lib/extraction.svelte.ts` — `start()` only.
- `client/tests/extraction-controller.test.ts` — extend with one extra test that uses the real `ExtractionController.start()` semantics.
- `plans/README.md`

**Out of scope**:
- `Cancel()` semantics — leave alone; the abort-on-restart in `start()` covers the leak.
- Batch loop behavior (`extractMany` at L86) — do NOT add a guard inside the for-loop; the controller's lifecycle handles it. Touching the batch would create a duplicate guard.
- `appState` / `libraryStore` — no change needed.
- Visual feedback (`toast` calls) — leave alone.

## Git workflow

- Branch: `improve/003-extraction-controller-abort`
- Commit message: `Frontend: abort prior in-flight fetch in ExtractionController.start()`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Abort the prior controller in `start()`

Edit `start()` to abort any in-flight controller before allocating the new one:

```typescript
// realtime fetch is single-flight — abort whatever is still in flight so a
// re-entered paste/retry doesn't leak the prior request up to the 3-min
// server timeout and confuse the running flag.
private readonly start = (): void => {
    this.controller?.abort();
    this.controller = new AbortController();
    this.elapsedSeconds = 0;
    this.timer = setInterval(() => this.elapsedSeconds++, 1000);
};
```

Convert `start` from method-syntax to arrow-bound property so re-binding (if any future refactor does it) keeps `this`. This is compatible with Svelte 5's class-field reactivity.

`stop()` is unchanged — it already does `this.controller?.abort()` which is correct for the normal end-of-task case.

### Step 2: Verify locked-in test passes

```
cd client && npm test
```

Expected: `extraction-controller.test.ts` → `1 passed` for `does not leak pending fetches` (the locked-in test from plan 001).

### Step 3: Add a test using the real class

Append to `client/tests/extraction-controller.test.ts`:

```typescript
import { ExtractionController } from '$lib/extraction.svelte';

describe('ExtractionController.start aborts prior controller', () => {
  it('aborts the previous AbortController when start() is re-entered', () => {
    const c = new ExtractionController();
    // Reach into the private field via any cast — test only.
    (c as any).start();
    const first = (c as any).controller as AbortController;
    (c as any).start();
    expect(first.signal.aborted).toBe(true);
    expect((c as any).controller).not.toBe(first);
  });
});
```

Run `npm test` → `2 passed` in that file.

### Step 4: Run the full frontend gate

```
cd client && npm test && npm run check && npm run lint
```

All three exit 0; no `any` newly-leaked, no new error.

### Step 5: Update `plans/README.md`

Set this plan's status to `DONE`.

## Test plan

- Locked-in `extraction-controller.test.ts::does not leak pending fetches` flips green.
- New `ExtractionController.start aborts prior controller` passes — touching the real class.
- All other frontend tests unchanged.
- A future regression that re-introduces a leak (e.g. subclass that bypasses `start`) is now caught by the suite.

## Done criteria

- [ ] `cd client && npm test` exits 0 with the two new tests passing
- [ ] `cd client && npm run check` exits 0
- [ ] `cd client && npm run lint` exits 0
- [ ] `git status` lists only `client/src/lib/extraction.svelte.ts`, `client/tests/extraction-controller.test.ts`, `plans/README.md`
- [ ] `grep -n "abort()" client/src/lib/extraction.svelte.ts` shows the new abort site in `start()`
- [ ] `plans/README.md` updated

## STOP conditions

Stop and report back (do not improvise) if:
- The locked-in test was already green before Step 1 — your edit may be ineffectual or the test was miswritten.
- The locked-in test still red after Step 1 — `start()` is the wrong place; escalate rather than try alternative hook points.
- Tests in unrelated files start failing — the edit leaked into shared state.

## Maintenance notes

- This is a behavioral fix on a controller that's tightly coupled to `appStore`. A reviewer should specifically check `run()` (lines 336-381) was NOT modified — only `start()` changed.
- `cancel()` already aborts via `stop()`; no change there.
- If a future plan adds a queue-style batching layer above `ExtractionController`, the abort-on-restart invariant must hold at *both* layers (otherwise the user's fleet of concurrent pastes still leaks).
