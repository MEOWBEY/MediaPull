"""Groq-backed Transcriber: hosted Whisper speech-to-text.

Transcription only -- speech becomes text in whatever language it was
spoken; no translation direction. Free tier at console.groq.com, no card
required. 429s are retried with backoff, honoring the API's own
``Retry-After`` header up to ``Settings.max_retries`` (same retry-count
semantics as the extractor).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from ..config import Settings
from .base import Segment, TranscriptionResult

logger = logging.getLogger("directstream.transcribe.groq")

_BASE_URL = "https://api.groq.com/openai/v1"
_TRANSCRIPTIONS_URL = f"{_BASE_URL}/audio/transcriptions"


class GroqError(Exception):
    """Raised when Groq's API fails after retries, or returns an unusable shape."""


class GroqTranscriber:
    def __init__(self, settings: Settings) -> None:
        if not settings.groq_api_key:
            raise GroqError("GROQ_API_KEY is not configured")
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            timeout=httpx.Timeout(120.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ----- transport with retry/backoff ---------------------------------

    async def _post_with_retry(self, url: str, **kwargs) -> httpx.Response:
        attempt = 0
        while True:
            try:
                resp = await self._client.post(url, **kwargs)
            except httpx.HTTPError as exc:
                if attempt >= self._settings.max_retries:
                    raise GroqError(f"Groq request failed: {exc}") from exc
                attempt += 1
                await asyncio.sleep(min(2**attempt, 20))
                continue

            if resp.status_code == 429:
                if attempt >= self._settings.max_retries:
                    raise GroqError(
                        "Groq's free-tier rate limit was hit and retries were "
                        "exhausted — try again in a few minutes."
                    )
                retry_after = float(resp.headers.get("retry-after", 2**attempt))
                attempt += 1
                logger.warning("Groq 429, retrying in %.0fs (attempt %d)", retry_after, attempt)
                await asyncio.sleep(min(retry_after, 60))
                continue

            if resp.status_code >= 400:
                raise GroqError(f"Groq API error {resp.status_code}: {resp.text[:500]}")

            return resp

    # ----- Whisper (transcribe) ------------------------------------------

    async def transcribe(self, audio_path: Path) -> TranscriptionResult:
        audio_bytes = audio_path.read_bytes()
        data = {"model": self._settings.groq_whisper_model, "response_format": "verbose_json"}
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
        else:
            # No segment-level detail returned (rare) -- treat the whole
            # clip as one segment rather than failing the pipeline outright.
            text = (payload.get("text") or "").strip()
            segments = [Segment(start=0.0, end=0.0, text=text)] if text else []

        return TranscriptionResult(segments=segments, language=payload.get("language") or "en")
