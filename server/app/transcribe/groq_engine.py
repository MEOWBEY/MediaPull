"""Groq-backed Transcriber: hosted Whisper speech-to-text.

Transcription only -- speech becomes text in whatever language it was
spoken; no translation direction. Free tier at console.groq.com, no card
required.

``GROQ_API_KEY`` may hold several comma-separated keys. Requests are spread
round-robin across the pool, and a 429 doesn't block the pipeline: the
rate-limited key is put on cooldown (honoring the API's ``Retry-After``) and
the request immediately retries on the next available key. Only when *every*
key is cooling down does the pipeline actually sleep -- so extra keys
translate directly into throughput instead of waiting.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from pathlib import Path

import httpx

from ..config import Settings
from .base import Segment, TranscriptionResult

logger = logging.getLogger("mediapull.transcribe.groq")

_BASE_URL = "https://api.groq.com/openai/v1"
_TRANSCRIPTIONS_URL = f"{_BASE_URL}/audio/transcriptions"

# Groq rejects uploads past its per-file cap (25MB on the free tier). Our own
# windowing keeps files under ~80% of it; this guard only turns a confusing
# HTTP 413 into an actionable error if that invariant ever breaks. Derived from
# the ``TRANSCRIBE_MAX_UPLOAD_MB`` setting (with a small safety margin) so
# raising the plan's cap needs only the env var, not a code change.
def _max_upload_bytes(settings: Settings) -> int:
    return int(settings.transcribe_max_upload_bytes * 0.96)

# Concurrent requests each key can comfortably sustain on the free tier
# (whisper-large-v3-turbo allows 20 req/min), and a global ceiling so a huge
# key pool can't hold dozens of chunk uploads in memory at once on a small VPS.
_PER_KEY_CONCURRENCY = 5
_MAX_TOTAL_CONCURRENCY = 16

# Fallback cue-end trim, used only when the API returns no word timestamps:
# Whisper's segment ends are frequently padded through trailing silence, so
# cap each cue's duration to what its text could plausibly take to say.
# 8 chars/sec is slower than any real speech.
_MIN_CUE_SECONDS = 1.5
_MAX_CUE_SECONDS = 7.0
_SLOW_SPEECH_CPS = 8.0


class GroqError(Exception):
    """Raised when Groq's API fails after retries, or returns an unusable shape."""


class _PoolKey:
    """One API key plus its rate-limit state. ``cooldown_until`` is a
    ``time.monotonic()`` deadline; ``math.inf`` means the key was rejected
    outright (401/403) and is out of the rotation for good."""

    __slots__ = ("value", "cooldown_until")

    def __init__(self, value: str) -> None:
        self.value = value
        self.cooldown_until = 0.0


class GroqTranscriber:
    def __init__(self, settings: Settings) -> None:
        keys = settings.groq_api_keys
        if not keys:
            raise GroqError("GROQ_API_KEY is not configured")
        self._settings = settings
        self._keys = [_PoolKey(k) for k in keys]
        self._rr = 0
        self._client = httpx.AsyncClient(base_url=_BASE_URL, timeout=httpx.Timeout(120.0))
        if len(self._keys) > 1:
            logger.info("Groq key pool: %d keys", len(self._keys))

    @property
    def max_concurrency(self) -> int:
        """How many chunk requests are worth running in parallel -- scales
        with the key pool instead of needing its own tuning knob."""
        return min(_MAX_TOTAL_CONCURRENCY, _PER_KEY_CONCURRENCY * len(self._keys))

    async def aclose(self) -> None:
        await self._client.aclose()

    # ----- key pool -------------------------------------------------------

    def _next_available_key(self) -> _PoolKey | None:
        now = time.monotonic()
        available = [k for k in self._keys if k.cooldown_until <= now]
        if not available:
            return None
        self._rr += 1
        return available[self._rr % len(available)]

    def _soonest_cooldown(self) -> float:
        """Seconds until the next key frees up; raises if every key was
        permanently rejected (there is nothing to wait for)."""
        deadlines = [k.cooldown_until for k in self._keys if k.cooldown_until != math.inf]
        if not deadlines:
            raise GroqError(
                "Every configured GROQ_API_KEY was rejected (invalid or revoked) -- "
                "check the keys in your .env."
            )
        return max(0.0, min(deadlines) - time.monotonic())

    # ----- transport with key rotation ------------------------------------

    async def _post_with_retry(self, url: str, **kwargs) -> httpx.Response:
        network_attempts = 0
        pool_sleeps = 0
        while True:
            key = self._next_available_key()
            if key is None:
                # Every key is rate-limited right now -- sleeping is the only
                # honest option left, bounded so a hammered pool still fails
                # with a clear message instead of stalling forever.
                pool_sleeps += 1
                if pool_sleeps > self._settings.max_retries + 1:
                    raise GroqError(
                        "Groq rate limits were hit on every configured API key and "
                        "retries were exhausted — try again in a few minutes, or add "
                        "more keys to GROQ_API_KEY."
                    )
                wait = min(self._soonest_cooldown(), 60.0) + 0.1
                logger.warning("all Groq keys cooling down, sleeping %.1fs", wait)
                await asyncio.sleep(wait)
                continue

            try:
                resp = await self._client.post(
                    url, headers={"Authorization": f"Bearer {key.value}"}, **kwargs
                )
            except httpx.HTTPError as exc:
                network_attempts += 1
                if network_attempts > self._settings.max_retries:
                    raise GroqError(f"Groq request failed: {exc}") from exc
                await asyncio.sleep(min(2**network_attempts, 20))
                continue

            if resp.status_code == 429:
                try:
                    retry_after = float(resp.headers.get("retry-after", "5"))
                except ValueError:
                    retry_after = 5.0
                key.cooldown_until = time.monotonic() + min(retry_after, 120.0)
                logger.warning(
                    "Groq 429 on key #%d, cooling it down %.0fs and rotating",
                    self._keys.index(key) + 1,
                    min(retry_after, 120.0),
                )
                continue  # immediately retries on the next available key

            if resp.status_code in (401, 403):
                # A bad key never recovers -- drop it from the rotation so the
                # rest of the pool keeps working instead of re-hitting it.
                key.cooldown_until = math.inf
                logger.error(
                    "Groq rejected key #%d (%d) -- removing it from the pool",
                    self._keys.index(key) + 1,
                    resp.status_code,
                )
                continue

            if resp.status_code >= 400:
                # The raw response body stays in the server log -- it can echo
                # request detail and must not surface in job.error.
                logger.error("Groq API error %s: %s", resp.status_code, resp.text[:500])
                raise GroqError(f"Transcription service error (HTTP {resp.status_code})")

            return resp

    # ----- Whisper (transcribe) ------------------------------------------

    async def transcribe(self, audio_path: Path) -> TranscriptionResult:
        audio_bytes = await asyncio.to_thread(audio_path.read_bytes)
        max_upload = _max_upload_bytes(self._settings)
        if len(audio_bytes) > max_upload:
            raise GroqError(
                f"Audio chunk {audio_path.name} is {len(audio_bytes) / 1e6:.0f}MB, "
                f"over the {self._settings.transcribe_max_upload_mb}MB per-request cap "
                "(TRANSCRIBE_MAX_UPLOAD_MB) — this indicates a chunking bug."
            )
        data: dict[str, object] = {
            "model": self._settings.groq_whisper_model,
            "response_format": "verbose_json",
            # Word-level timestamps: Whisper's segment ends are routinely
            # padded through trailing silence (captions linger after speech
            # stops) and its starts can drift. Per-word times let us pin each
            # cue to when speech actually starts/stops. httpx encodes the
            # list as repeated form fields, which is what the API expects.
            "timestamp_granularities[]": ["word", "segment"],
        }
        prompt = self._settings.transcribe_whisper_prompt.strip()
        if prompt:
            data["prompt"] = prompt
        resp = await self._post_with_retry(
            _TRANSCRIPTIONS_URL, files={"file": (audio_path.name, audio_bytes)}, data=data
        )
        payload = resp.json()

        raw_segments = payload.get("segments") or []
        if raw_segments:
            segments = [
                Segment(start=float(s["start"]), end=float(s["end"]), text=str(s["text"]).strip())
                for s in raw_segments
                if str(s.get("text", "")).strip()
            ]
            segments = _tighten_to_words(segments, payload.get("words") or [])
        else:
            # No segment-level detail returned (rare) -- treat the whole
            # clip as one segment rather than failing the pipeline outright.
            text = (payload.get("text") or "").strip()
            segments = [Segment(start=0.0, end=0.0, text=text)] if text else []

        return TranscriptionResult(segments=segments, language=payload.get("language") or "en")


def _tighten_to_words(segments: list[Segment], raw_words: list[dict]) -> list[Segment]:
    """Snap each segment's start/end to the actual spoken words inside it.

    With word timestamps this is exact: a cue appears when its first word is
    spoken and disappears right after its last one, so silence shows no
    caption at all. Without them (older models / a response that omitted
    ``words``), fall back to capping the duration by text length -- crude,
    but still strictly better than trusting the padded segment end.
    """
    words: list[tuple[float, float]] = []
    for w in raw_words:
        try:
            words.append((float(w["start"]), float(w["end"])))
        except (KeyError, TypeError, ValueError):
            continue
    words.sort()

    out: list[Segment] = []
    wi = 0
    for seg in segments:
        if words:
            # Words and segments are both time-ordered; walk forward once.
            while wi < len(words) and words[wi][1] <= seg.start:
                wi += 1
            wj = wi
            first_start: float | None = None
            last_end: float | None = None
            while wj < len(words) and words[wj][0] < seg.end:
                if first_start is None:
                    first_start = words[wj][0]
                last_end = words[wj][1]
                wj += 1
            wi = wj
            if first_start is not None and last_end is not None and last_end > first_start:
                out.append(Segment(start=first_start, end=last_end, text=seg.text))
                continue

        # Fallback: cap the duration to what the text could plausibly take
        # to say, so a silence-padded end still gets trimmed.
        budget = min(max(_MIN_CUE_SECONDS, len(seg.text) / _SLOW_SPEECH_CPS), _MAX_CUE_SECONDS)
        out.append(Segment(start=seg.start, end=min(seg.end, seg.start + budget), text=seg.text))
    return out
