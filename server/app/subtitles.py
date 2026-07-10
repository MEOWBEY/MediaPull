"""Merge chunked transcription results (timestamp-offset correction) and
format the resulting segments as SRT (download) and WebVTT (native
``<track>`` rendering -- browsers don't parse .srt for text tracks)."""

from __future__ import annotations

from .transcribe.base import Segment

_MIN_SEGMENT_DURATION = 0.3


def merge_chunks(chunk_results: list[tuple[float, list[Segment]]]) -> list[Segment]:
    """Combine each chunk's segments into one timeline.

    Each chunk's segments carry times relative to that chunk's own start;
    ``offset`` (the chunk's position in the original audio) is added back so
    the merged timeline lines up with the full video.
    """
    merged: list[Segment] = []
    for offset, segments in chunk_results:
        for seg in segments:
            merged.append(Segment(start=seg.start + offset, end=seg.end + offset, text=seg.text))

    merged.sort(key=lambda s: s.start)

    # Drop exact-duplicate adjacent segments -- can happen at a chunk
    # boundary if Whisper repeats a trailing word from the previous chunk.
    deduped: list[Segment] = []
    for seg in merged:
        if deduped and deduped[-1].text == seg.text and abs(deduped[-1].start - seg.start) < 1.0:
            continue
        deduped.append(seg)

    # Guard against zero/negative-duration cues (e.g. a whole-clip fallback
    # segment with no real per-word timing) -- SRT/VTT players render these
    # poorly or not at all. Silence-padded ends are already tightened to the
    # words' real timing at the engine level (see groq_engine._tighten_to_words).
    return [
        seg if seg.end > seg.start else Segment(seg.start, seg.start + _MIN_SEGMENT_DURATION, seg.text)
        for seg in deduped
    ]


def _format_timestamp(seconds: float, *, decimal_sep: str) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal_sep}{millis:03d}"


def to_srt(segments: list[Segment]) -> str:
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        lines.append(str(i))
        lines.append(
            f"{_format_timestamp(seg.start, decimal_sep=',')} --> "
            f"{_format_timestamp(seg.end, decimal_sep=',')}"
        )
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def to_vtt(segments: list[Segment]) -> str:
    lines: list[str] = ["WEBVTT", ""]
    for seg in segments:
        lines.append(
            f"{_format_timestamp(seg.start, decimal_sep='.')} --> "
            f"{_format_timestamp(seg.end, decimal_sep='.')}"
        )
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)
