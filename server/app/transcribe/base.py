"""Transcriber abstraction.

Speech-to-text only -- no translation direction. Isolates "audio ->
timestamped segments" behind a small interface so a local engine
(faster-whisper/whisper.cpp) could be added later without touching the rest
of the pipeline. Only a Groq-backed implementation exists today -- see
``groq_engine.py``. Research concluded a local engine isn't worth building
as the primary path for this project's scale; this interface is the
deliverable, not a second implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptionResult:
    segments: list[Segment]
    language: str  # code Whisper detected, e.g. "en", "fa", "es"


class Transcriber(Protocol):
    @property
    def max_concurrency(self) -> int:
        """How many chunk requests the engine can usefully run in parallel
        (for Groq: scales with the API-key pool)."""
        ...

    async def transcribe(self, audio_path: Path) -> TranscriptionResult:
        """Speech-to-text in whatever language was spoken, with per-segment
        timestamps and the detected language code."""
        ...
