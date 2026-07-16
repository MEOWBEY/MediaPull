"""Subprocess execution that works regardless of which asyncio event loop is
active.

``asyncio.create_subprocess_exec`` needs ``ProactorEventLoop`` on Windows --
plain ``SelectorEventLoop`` doesn't implement subprocess support there at
all and raises a bare ``NotImplementedError`` for every spawn. uvicorn
forces exactly that SelectorEventLoop downgrade on Windows whenever it runs
with ``--reload`` or multiple workers (``Config.use_subprocess`` in
uvicorn's own source, unrelated to anything this app configures), which is
this project's documented local dev command -- so every ffmpeg/ffprobe call
in the transcription pipeline failed under normal Windows dev use.

Spawning via ``subprocess.Popen`` and doing its blocking reads in worker
threads (``asyncio.to_thread``) sidesteps the loop's native subprocess
transport entirely, so behavior is identical no matter which loop is active.
"""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def spawn(args: list[str], **popen_kwargs: object) -> subprocess.Popen:
    """Start a process off the event loop -- ``Popen()`` itself is a
    blocking syscall on Windows."""
    return await asyncio.to_thread(subprocess.Popen, args, **popen_kwargs)  # type: ignore[arg-type]


async def communicate(proc: subprocess.Popen) -> tuple[bytes, bytes]:
    """``Popen.communicate()``, off the event loop. Reads stdout and stderr
    concurrently (each in its own thread) to avoid a deadlock if one pipe
    fills while only the other is being drained."""

    def _read_stdout() -> bytes:
        assert proc.stdout is not None
        return proc.stdout.read()

    def _read_stderr() -> bytes:
        assert proc.stderr is not None
        return proc.stderr.read()

    stdout, stderr = await asyncio.gather(
        asyncio.to_thread(_read_stdout), asyncio.to_thread(_read_stderr)
    )
    await asyncio.to_thread(proc.wait)
    return stdout, stderr


async def guarded(
    coro_factory: Callable[[], Awaitable[T]], *, proc: subprocess.Popen, timeout: float
) -> T:
    """Await ``coro_factory()`` with a timeout, killing and reaping ``proc``
    if it times out or this call is cancelled -- so a wedged or
    cancelled/timed-out ffmpeg child never outlives its job. Callers
    translate ``asyncio.TimeoutError`` into their own error type;
    ``asyncio.CancelledError`` propagates unchanged after cleanup, same as
    it always did with the native asyncio subprocess API.
    """
    try:
        return await asyncio.wait_for(coro_factory(), timeout=timeout)
    except (TimeoutError, asyncio.CancelledError):
        proc.kill()
        await asyncio.to_thread(proc.wait)
        raise
