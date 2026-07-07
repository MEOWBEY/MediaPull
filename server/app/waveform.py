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
from pathlib import Path

_SAMPLE_RATE = 16000
_WINDOW_MS = 100
_SAMPLES_PER_WINDOW = int(_SAMPLE_RATE * _WINDOW_MS / 1000)


class WaveformError(Exception):
    pass


async def extract_peaks(audio_path: Path, *, max_points: int = 3000) -> list[float]:
    """Normalized (0..1) peak amplitudes, one per ~100ms window, downsampled
    further if the result would exceed ``max_points`` (keeps long videos'
    payload small)."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
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
    raw, stderr = await proc.communicate()
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

    peaks: list[float] = []
    for i in range(0, len(samples), _SAMPLES_PER_WINDOW):
        window = samples[i : i + _SAMPLES_PER_WINDOW]
        if not window:
            continue
        peaks.append(max(abs(s) for s in window) / 32768.0)

    return _downsample(peaks, max_points)


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
