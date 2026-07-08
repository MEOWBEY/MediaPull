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
        )
    except OSError as exc:
        logger.error("ffmpeg binary %r is not runnable: %s", settings.ffmpeg_binary, exc)
        raise WaveformError(f"ffmpeg is not installed or not on PATH ({settings.ffmpeg_binary!r})") from exc

    try:
        raw, stderr = await asyncio.wait_for(proc.communicate(), timeout=_FFMPEG_DECODE_TIMEOUT)
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

    # s16le is little-endian 16-bit signed -- matches array('h')'s native
    # layout on the x86_64/ARM64 targets this app deploys to.
    usable_len = (len(raw) // 2) * 2
    samples = array.array("h")
    samples.frombytes(raw[:usable_len])
    if not samples:
        return []

    peaks = await asyncio.to_thread(_compute_peaks, samples)
    return _downsample(peaks, max_points)


def _compute_peaks(samples: array.array) -> list[float]:
    """Pure-Python per-sample scan -- run off the event loop via
    ``asyncio.to_thread`` since a long track makes this slow enough to block
    all other request handling if run inline."""
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
