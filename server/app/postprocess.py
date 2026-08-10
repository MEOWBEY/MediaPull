"""Post-process Whisper transcription output to remove noise artifacts.

Applied after every Groq Whisper job (online and local) when
TRANSCRIBE_POSTPROCESS=true. Runs in microseconds on typical subtitle files.

What it fixes:
  - Music/noise placeholders: ♪ ♫ [Music] (Music) [Applause] [Laughter] etc.
  - Consecutive duplicate cues (Whisper hallucination at chunk boundaries)
  - Sub-0.5s isolated single-word cues (another common hallucination artifact)
  - Long cues that stack several sentences (fast dialogue, several speakers)
  - Trailing periods on finished cues (cosmetic; keeps the punctuation Whisper
    used internally for the split, so the splitter still works)

Long cues are usually split EXACTLY at the engine level (groq_engine
``_tighten_to_words``) using Whisper's real word timestamps, so cue times
never shift. This module is the safety net for responses without word
timestamps: it splits sentence-by-sentence, apportioning the cue's total
duration by each sentence's character count (speech rate is roughly constant
within a cue, so the estimate is close). The cue's overall start/end are
always preserved -- only the interior boundaries are estimated, never
fabricated outside the original span.
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

# Long-cue fallback split (only fires when a cue is still this long after the
# engine's exact word-timestamp split — i.e. no word timestamps were present).
_LONG_CUE_SECS = 8.0
_MIN_PART_CHARS = 12     # sentences shorter than this get merged into a neighbour
_MIN_PART_SECS = 0.8     # floor per split cue so nothing renders as a sliver

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


def clean(segments: list[Segment], *, split_long_cues: bool = True) -> list[Segment]:
    """Return a new list with noise segments removed and duplicates collapsed."""
    if not segments:
        return segments

    # 0. Cosmetic cue-end cleanup BEFORE everything else: drop trailing
    #    periods ("? " and "! " survive — they carry meaning). The splitter is
    #    not affected: it reads punctuation inside the cue, and cues that had
    #    their final period stripped are already split by then. Cues reduced
    #    to nothing ("..." alone) are caught by the noise filter below.
    cleaned = [Segment(s.start, s.end, _strip_trailing_dots(s.text)) for s in segments]

    # 1. Strip noise placeholders.
    cleaned = [s for s in cleaned if not _NOISE_RE.match(s.text)]

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

    # 4. Split leftover long multi-sentence cues (fallback for responses that
    #    carried no word timestamps — the engine already handled the rest).
    if split_long_cues:
        return _split_long_cues(deduped)
    return deduped


def _strip_trailing_dots(text: str) -> str:
    """Cosmetic end-of-cue cleanup: rstrip whitespace and drop trailing
    periods. "?" and "!" are untouched — "Really?." -> "Really?"."""
    text = text.rstrip()
    while text.endswith("."):
        text = text[:-1]
    return text


def _split_long_cues(segments: list[Segment]) -> list[Segment]:
    """Split cues longer than ``_LONG_CUE_SECS`` at sentence boundaries.

    Interior boundaries are estimated from character counts (each sentence's
    share of the total duration is its share of the total characters), so the
    cue's overall start/end never move and no pause is invented. Sentences too
    short to stand alone are merged back into their neighbour.
    """
    out: list[Segment] = []
    for seg in segments:
        duration = seg.end - seg.start
        if duration <= _LONG_CUE_SECS:
            out.append(seg)
            continue

        sentences = [p.strip() for p in _SENTENCE_SPLIT_RE.split(seg.text) if p.strip()]
        sentences = _merge_tiny_sentences(sentences)
        if len(sentences) < 2:
            out.append(seg)
            continue

        total_chars = sum(len(p) for p in sentences)
        if total_chars <= 0:
            out.append(seg)
            continue

        cursor = seg.start
        split: list[Segment] = []
        for sentence in sentences:
            piece_dur = duration * len(sentence) / total_chars
            piece_end = cursor + piece_dur
            if piece_dur < _MIN_PART_SECS:
                # Sliver — absorb into the previous cue so its end extends.
                if split:
                    split[-1] = Segment(split[-1].start, piece_end, split[-1].text)
                    cursor = piece_end
                    continue
                piece_end = cursor + _MIN_PART_SECS
            split.append(Segment(cursor, piece_end, sentence))
            cursor = piece_end

        out.extend(split)
    return out


def _merge_tiny_sentences(sentences: list[str]) -> list[str]:
    """Merge very short sentences (e.g. "Yes.") into the previous one so the
    proportional split doesn't leave a sliver cue of their own."""
    if len(sentences) < 2:
        return sentences
    merged: list[str] = []
    for sentence in sentences:
        if len(sentence) < _MIN_PART_CHARS and merged:
            merged[-1] += " " + sentence
        else:
            merged.append(sentence)
    return merged
