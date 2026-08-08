"""Post-process Whisper transcription output to remove noise artifacts.

Applied after every Groq Whisper job (online and local) when
TRANSCRIBE_POSTPROCESS=true. Runs in microseconds on typical subtitle files.

What it fixes:
  - Music/noise placeholders: ♪ ♫ [Music] (Music) [Applause] [Laughter] etc.
  - Consecutive duplicate cues (Whisper hallucination at chunk boundaries)
  - Sub-0.5s isolated single-word cues (another common hallucination artifact)

Long cues that stack several sentences are NOT split here: post-processing
has no timing information, and a re-timed-by-length split would fabricate
pauses that don't exist. Where real word timestamps exist, the engine
(groq_engine._tighten_to_words) splits such cues at its sentence boundaries
using the words' true times instead.
"""

from __future__ import annotations

import re

from .transcribe.base import Segment

# Patterns that mark non-speech content Whisper adds as placeholders.
_NOISE_RE = re.compile(
    r"""
    ^[\s♪♫\-–—~*]*$              # lines that are only music symbols / dashes
    | ^\s*\[.*?\]\s*$             # [Music] [Applause] [Laughter] [Noise] etc.
    | ^\s*\(.*?\)\s*$             # (Music) (Applause) same with parens
    | ^\s*♪[^♪]*♪?\s*$           # ♪ lyric ♪  or lone ♪
    """,
    re.VERBOSE | re.IGNORECASE,
)

_SHORT_CUE_SECS = 0.5
_SHORT_WORD_LIMIT = 1  # cues with <= this many words are checked for shortness


def clean(segments: list[Segment]) -> list[Segment]:
    """Return a new list with noise segments removed and duplicates collapsed."""
    if not segments:
        return segments

    # 1. Strip noise placeholders.
    cleaned = [s for s in segments if not _NOISE_RE.match(s.text)]

    # 2. Drop sub-0.5s single-word cues — almost always hallucinated filler.
    #    Keep them when they are adjacent to real speech (not isolated) because
    #    a genuine single-word utterance can be short (e.g. "Yes.", "No.", "OK.")
    #    in a pause-heavy conversation. "Isolated" here means no other cue
    #    overlaps or is within 1s of it.
    filtered: list[Segment] = []
    for i, seg in enumerate(cleaned):
        duration = seg.end - seg.start
        words = seg.text.split()
        if duration < _SHORT_CUE_SECS and len(words) <= _SHORT_WORD_LIMIT:
            prev_end = cleaned[i - 1].end if i > 0 else -999
            next_start = cleaned[i + 1].start if i < len(cleaned) - 1 else 999
            if seg.start - prev_end > 1.0 and next_start - seg.end > 1.0:
                continue  # isolated short cue — drop it
        filtered.append(seg)

    # 3. Collapse consecutive identical cues (Whisper repeats the same text at
    #    chunk seams when silence is mis-attributed). "Identical" is case- and
    #    whitespace-normalised.
    deduped: list[Segment] = []
    for seg in filtered:
        norm = " ".join(seg.text.lower().split())
        if deduped:
            prev_norm = " ".join(deduped[-1].text.lower().split())
            if norm == prev_norm:
                continue
        deduped.append(seg)

    return deduped
