"""Characterization tests for the cross-event-loop subprocess helper.

``proc_util`` exists so every ffmpeg/ffprobe/gallery-dl spawn behaves
identically no matter which asyncio loop uvicorn installed (the Windows
SelectorEventLoop downgrade under ``--reload`` can't spawn subprocesses
natively -- see the module docstring). These tests pin the two guarantees
callers depend on: ``communicate`` drains both pipes without deadlock, and
``guarded`` kills + reaps the child on both timeout and cancellation so no
ffmpeg process ever outlives its job.

Portable by design: they drive ``sys.executable`` (always present) instead
of ffmpeg, so they run the same on a CI box without media tooling installed.
"""

import asyncio
import subprocess
import sys

import pytest

from app import proc_util


async def _spawn_python(code: str) -> subprocess.Popen:
    return await proc_util.spawn(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


async def test_communicate_reads_both_pipes():
    proc = await _spawn_python(
        "import sys; sys.stdout.write('out'); sys.stderr.write('err')"
    )
    stdout, stderr = await proc_util.communicate(proc)
    assert stdout == b"out"
    assert stderr == b"err"
    assert proc.returncode == 0


async def test_communicate_drains_large_output_without_deadlock():
    # Both pipes get more than a pipe buffer's worth at once: a sequential
    # (read-stdout-then-stderr) drain would wedge here. Concurrent reads must not.
    proc = await _spawn_python(
        "import sys; sys.stdout.write('o' * 200000); sys.stderr.write('e' * 200000)"
    )
    stdout, stderr = await asyncio.wait_for(proc_util.communicate(proc), timeout=10)
    assert len(stdout) == 200000
    assert len(stderr) == 200000


async def test_guarded_returns_value_within_timeout():
    proc = await _spawn_python("pass")
    result = await proc_util.guarded(
        lambda: proc_util.communicate(proc), proc=proc, timeout=10
    )
    assert result == (b"", b"")


async def test_guarded_kills_and_reaps_on_timeout():
    # A child that would run far longer than the timeout must be killed, and
    # TimeoutError must surface so callers can translate it into their own error.
    proc = await _spawn_python("import time; time.sleep(30)")
    with pytest.raises(TimeoutError):
        await proc_util.guarded(
            lambda: proc_util.communicate(proc), proc=proc, timeout=0.5
        )
    # kill() + reap already happened inside guarded, so the child is dead and
    # its return code is available without blocking.
    assert proc.poll() is not None


async def test_guarded_kills_child_on_cancellation():
    # A cancelled job (client disconnect, shutdown) must not leak the ffmpeg
    # child. CancelledError propagates unchanged after the kill.
    proc = await _spawn_python("import time; time.sleep(30)")
    task = asyncio.create_task(
        proc_util.guarded(
            lambda: proc_util.communicate(proc), proc=proc, timeout=30
        )
    )
    await asyncio.sleep(0.2)  # let guarded start awaiting the child
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert proc.poll() is not None
