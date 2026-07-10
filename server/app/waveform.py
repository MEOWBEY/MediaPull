"""Waveform peak extraction for the player's dialogue-map seek bar.

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
from pathlib import Path

from .config import Settings

logger = logging.getLogger("directstream.waveform")

_SAMPLE_RATE = 16000
_WINDOW_MS = 100
_SAMPLES_PER_WINDOW = int(_SAMPLE_RATE * _WINDOW_MS / 1000)
# Bounds the PCM-decode subprocess -- generous relative to _FFMPEG_TIMEOUT in
# audio.py since this is decoding a full audio stream, not just transcoding.
_FFMPEG_DECODE_TIMEOUT = 60


class WaveformError(Exception):
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
        proc = await asyncio.create_subprocess_exec(
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
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=_READ_BLOCK * 4,  # StreamReader buffer high-water mark
        )
    except OSError as exc:
        logger.error("ffmpeg binary %r is not runnable: %s", settings.ffmpeg_binary, exc)
        raise WaveformError(f"ffmpeg is not installed or not on PATH ({settings.ffmpeg_binary!r})") from exc

    peaks: list[float] = []
    buf = bytearray()

    async def _pump() -> None:
        assert proc.stdout is not None
        while True:
            block = await proc.stdout.read(_READ_BLOCK)
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
                peaks.extend(await asyncio.to_thread(_peaks_from_bytes, block_bytes))
        # Trailing partial window (audio not landing on a 100ms boundary).
        if buf:
            peaks.extend(await asyncio.to_thread(_peaks_from_bytes, bytes(buf)))
            buf.clear()

    async def _consume() -> bytes:
        assert proc.stderr is not None
        _, stderr = await asyncio.gather(_pump(), proc.stderr.read())
        await proc.wait()
        return stderr

    try:
        stderr = await asyncio.wait_for(_consume(), timeout=_FFMPEG_DECODE_TIMEOUT)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise WaveformError("ffmpeg PCM decode timed out") from exc
    except asyncio.CancelledError:
        # Don't leave the decode child running as an orphan if this job gets
        # cancelled/times out while waiting on it.
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode != 0:
        raise WaveformError(
            f"ffmpeg PCM decode failed: {stderr.decode(errors='ignore')[-500:].strip()}"
        )
    return peaks


def _peaks_from_bytes(raw: bytes) -> list[float]:
    """Per-100ms peak amplitudes for one block of s16le PCM. Pure-Python scan,
    run off the event loop via ``asyncio.to_thread`` -- a long track makes this
    slow enough to block all other request handling if run inline. s16le is
    little-endian 16-bit signed, matching ``array('h')`` on the x86_64/ARM64
    targets this app deploys to."""
    usable_len = (len(raw) // 2) * 2
    samples = array.array("h")
    samples.frombytes(raw[:usable_len])
    peaks: list[float] = []
    for i in range(0, len(samples), _SAMPLES_PER_WINDOW):
        window = samples[i : i + _SAMPLES_PER_WINDOW]
        if not window:
            continue
        peaks.append(max(abs(s) for s in window) / 32768.0)
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
