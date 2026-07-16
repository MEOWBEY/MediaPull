# Plan 006: Enforce the configured `transcribe_job_timeout` (today it is a silent no-op)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: written against the **working tree** at commit
> `a225b1c` with uncommitted changes applied to `server/app/jobs.py` and
> `server/app/config.py`. `git diff a225b1c..HEAD` shows nothing — do NOT trust
> it. Open the files and compare against the "Current state" excerpts. On any
> mismatch, STOP.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-test-baseline.md
- **Category**: bug
- **Planned at**: commit `a225b1c` (+ uncommitted working-tree changes), 2026-07-13

## Why this matters

`config.py:110-111` defines a setting whose docstring promises safety:

```python
    # Whole-job wall-clock cap; a stuck/very slow job is killed and reported
    # as an error rather than running forever.
    transcribe_job_timeout: int = Field(default=900, ge=60, le=3600, alias="TRANSCRIBE_JOB_TIMEOUT")
```

**Nothing reads it.** `grep -rn "transcribe_job_timeout" server/` returns only
its definition — no `asyncio.wait_for`, no cancellation, nowhere. A
transcription job that wedges (a Groq request that never returns, an ffmpeg
extract that hangs on a stalled CDN socket) runs **forever**: it holds a slot in
`store.semaphore` (`transcribe_max_concurrent_jobs`, default 2) and a
`cpu_semaphore` permit, so after two stuck jobs the whole `/transcribe` feature
is dead until the process restarts. `transcribe_job_ttl` (`config.py:107-108`)
only sweeps the *record* from memory on the next `create()`; it never cancels
the running task. This plan wires the timeout up so the documented behavior is
real, with a regression test so it can't silently rot again.

## Current state

- `server/app/config.py:111` — `transcribe_job_timeout` defined, unused.
- `server/app/jobs.py` — `run_transcription_job` is the job entry point; it wraps
  the whole pipeline and already has terminal-state handling.
- `server/app/main.py:277-287` — `start_transcribe` route spawns the job task.

`jobs.py:148-155` (signature):
```python
async def run_transcription_job(
    job_id: str,
    formats: list[VideoFormat],
    settings: Settings,
    store: JobStore,
    transcriber: Transcriber,
    duration_hint: float | None = None,
) -> None:
    work_dir = create_work_dir()
```

`jobs.py:469-483` (the outer try/except that owns terminal status — this is
where the timeout must be caught, because `asyncio.TimeoutError` is *not* an
`asyncio.CancelledError` subclass on Python 3.11+, so the existing handlers
would misclassify a timeout as a generic error with an ugly message):
```python
    try:
        await _pipeline()
    except asyncio.CancelledError:
        logger.info("transcription job %s cancelled", job_id)
        await store.update(job_id, status="cancelled", step_label="Cancelled", progress=1.0)
    except Exception as exc:
        logger.exception("transcription job %s failed", job_id)
        await store.update(
            job_id,
            status="error",
            step_label="Error",
            progress=1.0,
            error=str(exc) or type(exc).__name__,
        )
```

**Key fact about the pipeline's cancellation semantics** (verified): `_pipeline`
and its `_run_windowed` / `_run_single_pass` inner functions already tear down
every spawned task and their ffmpeg children in `finally` blocks
(`jobs.py:325-335`, `jobs.py:454-457`) *and* `run_transcription_job` cleans the
work dir in a `finally` (`jobs.py:465-467`). So cancelling `_pipeline()` via
`wait_for` timeout triggers all existing cleanup — you do NOT need to add
teardown logic, only to start the clock and label the terminal state.

**Repo conventions to follow**:
- `asyncio.wait_for(coro, timeout=…)` is the established pattern in this codebase
  (`audio.py:421,458,510`, `waveform.py:124`, `extractor.py:247`). Match it.
- On Python ≥3.11 `asyncio.wait_for` raises `TimeoutError` (the builtin, which is
  aliased by `asyncio.TimeoutError`). Catch `asyncio.TimeoutError` explicitly and
  place that `except` **before** the broad `except Exception`.
- Status vocabulary is fixed: terminal statuses are `("done", "error", "cancelled")`
  (`jobs.py:38`). A timeout is a failure the user should see, so use
  `status="error"` with a clear `error` message — do NOT invent a new status
  string (the client's `TranscribeStatus` and `_TERMINAL_STATUSES` don't know it).

## Commands you will need

| Purpose        | Command                                          | Expected on success |
|----------------|--------------------------------------------------|---------------------|
| Backend tests  | `cd server && python -m pytest -q`               | exit 0, all pass    |
| This file only | `cd server && python -m pytest tests/test_job_timeout.py -q` | exit 0  |
| Backend lint   | `cd server && ruff check app/`                   | exit 0              |
| Grep no-op gone| `grep -rn "transcribe_job_timeout" server/app/`  | 2+ hits (config + jobs) |

## Scope

**In scope** (the only files you should modify or create):
- `server/app/jobs.py` — wrap `_pipeline()` in `asyncio.wait_for` and add a
  `TimeoutError` branch to the terminal try/except.
- `server/tests/test_job_timeout.py` (create).
- `plans/README.md` — mark this plan's row.

**Out of scope** (do NOT touch, even though they look related):
- The pipeline internals (`_run_windowed`, `_run_single_pass`, `_finalize`,
  reporters) — they already handle cancellation; adding timeouts inside them
  would double-count and fight the outer cap.
- `transcribe_job_ttl` and `_sweep_expired_locked` — separate concern (memory
  reclaim of finished jobs), correct as-is.
- `main.py` `start_transcribe` — the timeout belongs on the job coroutine, not
  the route; changing the route risks blocking the request on the job.
- Per-chunk / per-request Groq timeouts inside `transcribe/groq_engine.py`.

## Git workflow

- Branch: `improve/006-transcribe-job-timeout`
- Commit message: `Fix: enforce transcribe_job_timeout (was defined but unused)`
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Wrap the pipeline in the configured timeout

In `jobs.py`, change the outer runner (`jobs.py:469-483`). Replace:

```python
    try:
        await _pipeline()
    except asyncio.CancelledError:
        logger.info("transcription job %s cancelled", job_id)
        await store.update(job_id, status="cancelled", step_label="Cancelled", progress=1.0)
    except Exception as exc:
        logger.exception("transcription job %s failed", job_id)
        await store.update(
            job_id,
            status="error",
            step_label="Error",
            progress=1.0,
            error=str(exc) or type(exc).__name__,
        )
```

with:

```python
    try:
        await asyncio.wait_for(_pipeline(), timeout=settings.transcribe_job_timeout)
    except asyncio.CancelledError:
        logger.info("transcription job %s cancelled", job_id)
        await store.update(job_id, status="cancelled", step_label="Cancelled", progress=1.0)
    except asyncio.TimeoutError:
        logger.warning(
            "transcription job %s exceeded %ss wall-clock cap -- killed",
            job_id,
            settings.transcribe_job_timeout,
        )
        await store.update(
            job_id,
            status="error",
            step_label="Timed out",
            progress=1.0,
            error=(
                f"Transcription exceeded the {settings.transcribe_job_timeout}s time "
                "limit and was stopped. Try a shorter source or raise "
                "TRANSCRIBE_JOB_TIMEOUT."
            ),
        )
    except Exception as exc:
        logger.exception("transcription job %s failed", job_id)
        await store.update(
            job_id,
            status="error",
            step_label="Error",
            progress=1.0,
            error=str(exc) or type(exc).__name__,
        )
```

`asyncio` is already imported at `jobs.py:5`. When `wait_for` times out it
cancels `_pipeline()`, which propagates `CancelledError` into the pipeline's
`finally` blocks — the existing task teardown and `cleanup_work_dir`
(`jobs.py:465-467`) still run. You are not changing that.

**Verify**: `cd server && ruff check app/` → exit 0.

### Step 2: Add a regression test

Create `server/tests/test_job_timeout.py`. It drives `run_transcription_job`
with a stub transcriber and a tiny timeout, monkeypatching the acquisition
layer so no real ffmpeg/network runs, and asserts the job ends in `error` with a
timeout message. Match the `asyncio_mode = auto` style from plan 001's
`tests/test_jobstore.py`.

```python
import asyncio
import pytest
from app.config import Settings
from app.jobs import JobStore, run_transcription_job


class _HangingTranscriber:
    max_concurrency = 1

    async def transcribe(self, path):  # never returns within the test window
        await asyncio.sleep(3600)

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_job_times_out_and_is_marked_error(monkeypatch):
    settings = Settings()
    settings.transcribe_job_timeout = 1  # 1s cap for the test

    # Force the single-pass path and make acquisition instant + fake so the
    # job blocks on the hanging transcriber, not on real I/O.
    import app.jobs as jobs_mod

    async def fake_plan_acquisition(formats, settings, duration_hint=None):
        class _Plan:
            windows = None  # -> single-pass path
        return _Plan()

    async def fake_acquire_audio(*a, **k):
        return jobs_mod.create_work_dir() / "audio.opus"

    async def fake_probe_duration(*a, **k):
        return 10.0

    async def fake_chunk_audio(*a, **k):
        # one dummy chunk so the transcribe loop runs and then hangs
        from app.audio import AudioChunk
        return [AudioChunk(path=a[0], offset_seconds=0.0)]

    async def fake_extract_peaks_chunks(*a, **k):
        return [0.0]

    monkeypatch.setattr(jobs_mod, "plan_acquisition", fake_plan_acquisition)
    monkeypatch.setattr(jobs_mod, "acquire_audio", fake_acquire_audio)
    monkeypatch.setattr(jobs_mod, "probe_duration", fake_probe_duration)
    monkeypatch.setattr(jobs_mod, "chunk_audio", fake_chunk_audio)
    monkeypatch.setattr(jobs_mod, "extract_peaks_chunks", fake_extract_peaks_chunks)

    store = JobStore(settings)
    job = await store.create()
    await run_transcription_job(
        job.id, [], settings, store, _HangingTranscriber(), duration_hint=10.0
    )
    result = await store.get(job.id)
    assert result.status == "error"
    assert "time limit" in (result.error or "").lower()
```

> The exact monkeypatch surface (which acquisition functions exist / their
> signatures) must match `jobs.py`'s imports at `jobs.py:11-21` and the
> `AudioChunk` constructor. If a stubbed function's signature doesn't line up,
> adjust the stub to match the real one — do NOT change `jobs.py` to fit the
> test. If you cannot make the single-pass path reach the hanging transcriber
> within ~10 lines of stubs, STOP and report; a heavier integration test is out
> of scope for this plan.

**Verify**: `cd server && python -m pytest tests/test_job_timeout.py -q` → 1 passed (runs in ~1–2s, not 3600s — proving the cap fired).

### Step 3: Full suite + lint

**Verify**:
- `cd server && python -m pytest -q` → exit 0, all pass.
- `cd server && ruff check app/` → exit 0.

### Step 4: Update `plans/README.md`

Set this plan's row to `DONE`.

## Test plan

- New test `server/tests/test_job_timeout.py::test_job_times_out_and_is_marked_error`:
  a job whose transcriber hangs is stopped at the 1s cap and lands in `status="error"`
  with a message containing "time limit". The test completing in ~1–2s (not
  blocking 3600s) is itself the proof the timeout fires.
- Model after `server/tests/test_jobstore.py` (plan 001) for the `JobStore`
  fixture + `asyncio` style.
- No new tests for the windowed path — the timeout wraps `_pipeline()` above
  both paths, so single-pass coverage exercises the same `wait_for`.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `cd server && python -m pytest -q` exits 0, all pass
- [ ] `cd server && ruff check app/` exits 0
- [ ] `grep -n "wait_for(_pipeline" server/app/jobs.py` shows the wrapped call
- [ ] `grep -n "asyncio.TimeoutError" server/app/jobs.py` shows the new branch
- [ ] `server/tests/test_job_timeout.py` exists and passes
- [ ] No files outside the in-scope list are modified (`git status`)
- [ ] `plans/README.md` status row updated to `DONE`

## STOP conditions

Stop and report back (do not improvise) if:
- `jobs.py:469-483` doesn't match the "Current state" excerpt (working tree drift).
- The suite hangs or the new test takes ≫ a few seconds — the timeout isn't
  actually cancelling the pipeline; do not paper over it by shrinking the sleep.
- Cancelling `_pipeline()` via `wait_for` leaves an ffmpeg process or task
  orphaned (visible as a warning/leak in test output) — the teardown assumption
  is wrong; escalate rather than adding ad-hoc kills here.
- The stub signatures in Step 2 can't be reconciled with `jobs.py`'s real
  imports within a small edit.

## Maintenance notes

- A reviewer should confirm the `except asyncio.TimeoutError` branch sits
  **before** `except Exception` (order matters) and uses `status="error"` (a new
  status string would break the client and `_TERMINAL_STATUSES`).
- If a future change moves the pipeline off `run_transcription_job` (e.g. to a
  worker queue), the wall-clock cap must move with it — the setting exists to
  guarantee a stuck job can't hold a concurrency slot forever.
- Deferred: finer-grained per-stage timeouts (Groq request, single ffmpeg
  extract). This plan is the coarse whole-job backstop only.
