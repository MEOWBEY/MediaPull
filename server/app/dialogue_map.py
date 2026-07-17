"""Dialogue-map peak extraction for the player's seek bar.

Decodes the same mono/16kHz audio track already produced for Whisper to raw
PCM once, and downsamples to ~1 peak per 100ms -- cheap enough to run once
per transcription job and ship as a small JSON array alongside the subtitles.
Avoids an unreliable client-side Web Audio decode of a proxied/CORS media
URL (see VideoPlayer.svelte's existing CORS/proxy constraints).
"""

from __future__ import annotations

import array
import asyncio
import logging
import subprocess
import sys
from pathlib import Path

from . import proc_util
from .config import Settings

logger = logging.getLogger("mediapull.dialogue_map")

_SAMPLE_RATE = 16000
_WINDOW_MS = 100
_SAMPLES_PER_WINDOW = int(_SAMPLE_RATE * _WINDOW_MS / 1000)
# Bounds the PCM-decode subprocess -- generous relative to _FFMPEG_TIMEOUT in
# audio.py since this is decoding a full audio stream, not just transcoding.
_FFMPEG_DECODE_TIMEOUT = 60


class DialogueMapError(Exception):
    pass


async def extract_peaks(
    audio_path: Path, settings: Settings, *, max_points: int = 3000
) -> list[float]:
    """Normalized (0..1) peak amplitudes, one per ~100ms window, downsampled
    further if the result would exceed ``max_points`` (keeps long videos'
    payload small)."""
    peaks = await _decode_peaks(audio_path, settings)
    return _downsample(peaks, max_points)


async def extract_peaks_chunks(
    paths: list[Path], settings: Settings, *, max_points: int = 3000
) -> list[float]:
    """Same as ``extract_peaks`` but for the parallel path, where the audio
    only exists as ordered chunk files. Decodes each chunk in order and
    concatenates the per-window peaks before the single final downsample, so
    the seek-bar map is identical to decoding one joined track. Chunks are
    decoded sequentially -- a small VPS shouldn't run N PCM decodes at once."""
    peaks: list[float] = []
    for path in paths:
        peaks.extend(await _decode_peaks(path, settings))
    return _downsample(peaks, max_points)


# One byte per s16le sample is 2; a 100ms window is this many bytes.
_WINDOW_BYTES = _SAMPLES_PER_WINDOW * 2
# Pull PCM off ffmpeg's pipe in ~1MB blocks. The whole point of streaming is to
# never hold the full decoded track (16kHz*2B = ~115MB per audio-hour) in RAM at
# once -- only this block plus the tiny running peaks list live at any moment.
_READ_BLOCK = 1 << 20


async def _decode_peaks(audio_path: Path, settings: Settings) -> list[float]:
    """Decode one audio file to mono/16kHz PCM and reduce it to per-100ms peak
    amplitudes, **streaming** the PCM off ffmpeg's stdout so a long track never
    materializes as one giant buffer. Peaks are computed per whole-window block
    off the event loop; only a ~1MB block is resident at a time."""
    try:
        proc = await proc_util.spawn(
            [
                settings.ffmpeg_binary,
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(audio_path),
                "-f",
                "s16le",
                "-ac",
                "1",
                "-ar",
                str(_SAMPLE_RATE),
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        logger.error("ffmpeg binary %r is not runnable: %s", settings.ffmpeg_binary, exc)
        raise DialogueMapError(f"ffmpeg is not installed or not on PATH ({settings.ffmpeg_binary!r})") from exc

    def _pump_stdout() -> list[float]:
        assert proc.stdout is not None
        peaks: list[float] = []
        buf = bytearray()
        while True:
            block = proc.stdout.read(_READ_BLOCK)
            if not block:
                break
            buf.extend(block)
            # Reduce only complete 100ms windows; keep the sub-window remainder
            # in `buf` so the next block continues where this one stopped. The
            # cut is a whole-window multiple, so samples stay 2-byte aligned.
            whole = (len(buf) // _WINDOW_BYTES) * _WINDOW_BYTES
            if whole:
                block_bytes = bytes(buf[:whole])
                del buf[:whole]
                peaks.extend(_peaks_from_bytes(block_bytes))
        # Trailing partial window (audio not landing on a 100ms boundary).
        if buf:
            peaks.extend(_peaks_from_bytes(bytes(buf)))
        return peaks

    def _pump_stderr() -> bytes:
        assert proc.stderr is not None
        return proc.stderr.read()

    async def _consume() -> tuple[list[float], bytes]:
        # stdout/stderr are drained concurrently (each in its own thread) --
        # sequentially would risk a deadlock if one pipe fills while only the
        # other is being read.
        peaks, stderr = await asyncio.gather(
            asyncio.to_thread(_pump_stdout), asyncio.to_thread(_pump_stderr)
        )
        await asyncio.to_thread(proc.wait)
        return peaks, stderr

    try:
        peaks, stderr = await proc_util.guarded(_consume, proc=proc, timeout=_FFMPEG_DECODE_TIMEOUT)
    except TimeoutError as exc:
        raise DialogueMapError("ffmpeg PCM decode timed out") from exc
    if proc.returncode != 0:
        raise DialogueMapError(
            f"ffmpeg PCM decode failed: {stderr.decode(errors='ignore')[-500:].strip()}"
        )
    return peaks

def _peaks_from_bytes(raw: bytes) -> list[float]:
    """Per-100ms peak amplitudes for one block of s16le PCM."""
    usable_len = (len(raw) // 2) * 2
    samples = array.array("h")
    samples.frombytes(raw[:usable_len])
    if sys.byteorder == "big":
        samples.byteswap()
    peaks: list[float] = []
    n = len(samples)
    step = _SAMPLES_PER_WINDOW
    for i in range(0, n, step):
        chunk = samples[i : i + step]
        if chunk:
            peaks.append(max(map(abs, chunk)) / 32768.0)
    return peaks


def _downsample(peaks: list[float], max_points: int) -> list[float]:
    if len(peaks) <= max_points:
        return peaks

    ratio = len(peaks) / max_points
    out: list[float] = []
    for i in range(max_points):
        start = int(i * ratio)
        end = max(start + 1, int((i + 1) * ratio))
        window = peaks[start:end]
        out.append(max(window) if window else 0.0)
    return out
