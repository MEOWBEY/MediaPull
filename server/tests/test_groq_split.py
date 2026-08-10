"""Engine-level long-cue splitting: uses Whisper's real word timestamps, so
splitting never shifts or fabricates timing."""

from __future__ import annotations

from app.transcribe.base import Segment
from app.transcribe.groq_engine import _split_long_segment, _tighten_to_words


def _words(*items: tuple[str, float, float]) -> list[dict]:
    """Build the ``words`` payload shape Groq returns for each word.

    ``items`` are raw ``(word, start, end)`` tuples, like the API returns.
    """
    return [{"word": w, "start": s, "end": e} for w, s, e in items]


def _w(*items: tuple[str, float, float]) -> list[tuple[float, float, str]]:
    """Raw ``(word, start, end)`` tuples -> the engine's ``(start, end, word)``."""
    return [(s, e, w) for w, s, e in items]


def test_short_segment_stays_one_cue() -> None:
    words = _w(("Hello", 0.0, 0.3), ("there.", 0.3, 0.7), ("How", 0.9, 1.1), ("are", 1.1, 1.3), ("you?", 1.3, 1.6))
    out = _split_long_segment(words, "Hello there. How are you?")
    assert len(out) == 1
    assert out[0][2] == "Hello there. How are you?"


def test_fast_exchange_below_threshold_stays_whole() -> None:
    # A quick "No. What? Why?" back-and-forth is under the split thresholds and
    # should NOT be torn apart — short cues are fine to read whole.
    words = _w(("No.", 0.0, 0.3), ("What?", 0.4, 0.7), ("Why?", 0.8, 1.1))
    out = _split_long_segment(words, "No. What? Why?")
    assert len(out) == 1


def test_long_multisentence_split_uses_exact_word_times() -> None:
    raw = (
        ("We", 0.0, 0.3),
        ("cannot", 0.35, 0.65),
        ("let", 0.7, 1.0),
        ("this", 1.05, 1.35),
        ("go.", 1.4, 1.7),
        ("I", 1.8, 2.1),
        ("am", 2.15, 2.45),
        ("not", 2.5, 2.8),
        ("letting", 2.85, 3.15),
        ("you", 3.2, 3.5),
        ("walk", 3.55, 3.85),
        ("out.", 3.9, 4.2),
        ("You", 4.3, 4.6),
        ("need", 4.65, 4.95),
        ("to", 5.0, 5.3),
        ("stay", 5.35, 5.65),
        ("now.", 5.7, 6.0),
    )
    seg = Segment(0.0, 6.2, "We cannot let this go. I am not letting you walk out. You need to stay now.")
    out = _tighten_to_words([seg], _words(*raw))
    assert [o.text for o in out] == [
        "We cannot let this go.",
        "I am not letting you walk out.",
        "You need to stay now.",
    ]
    # Exact real-word boundaries — nothing invented, total span preserved.
    assert out[0].start == 0.0 and out[0].end == 1.7
    assert out[1].start == 1.8 and out[1].end == 4.2
    assert out[2].start == 4.3 and out[2].end == 6.0


def test_oversized_sentence_splits_at_commas() -> None:
    # One run-on sentence (no sentence punctuation except the final period)
    # longer than the max cue length — splits at comma boundaries.
    raw = (
        ("Well", 0.0, 0.3),
        ("I", 0.4, 0.7),
        ("mean", 0.8, 1.1),
        ("if", 1.2, 1.5),
        ("you", 1.6, 1.9),
        ("really", 2.0, 2.3),
        ("think", 2.4, 2.7),
        ("about", 2.8, 3.1),
        ("it", 3.2, 3.5),
        ("we", 3.6, 3.9),
        ("could", 4.0, 4.3),
        ("just", 4.4, 4.7),
        ("go", 4.8, 5.1),
        ("today,", 5.2, 5.5),
        ("either", 5.6, 5.9),
        ("way", 6.0, 6.3),
        ("I", 6.4, 6.7),
        ("am", 6.8, 7.1),
        ("fine", 7.2, 7.5),
        ("with", 7.6, 7.9),
        ("it.", 8.0, 8.3),
    )
    seg = Segment(0.0, 8.8, "Well I mean if you really think about it we could just go today, either way I am fine with it.")
    out = _tighten_to_words([seg], _words(*raw))
    assert len(out) == 2
    assert out[0].end == 5.5  # "today," — the comma boundary, exact word time
    assert out[1].start == 5.6  # "either" — first word of the second piece
    assert out[0].text.endswith("today,")
    assert out[1].text.startswith("either")


def test_tiny_piece_merges_into_neighbour() -> None:
    # A one-word "Yes." is a real utterance — it keeps its own cue. The split
    # itself must never leave slivers like a lone trailing word.
    words = _w(
        ("Yes.", 0.0, 0.4),
        ("Go", 0.6, 0.9),
        ("over", 1.0, 1.3),
        ("there", 1.4, 1.7),
        ("right", 1.8, 2.1),
        ("now", 2.2, 2.5),
        ("and", 2.6, 2.9),
        ("tell", 3.0, 3.3),
        ("me", 3.4, 3.7),
        ("exactly", 3.8, 4.1),
        ("what", 4.2, 4.5),
        ("all", 4.6, 4.9),
        ("happened.", 5.0, 5.3),
    )
    out = _split_long_segment(words, "Yes. Go over there right now and tell me exactly what all happened.")
    # 13 words / 5.3s / 2 sentences -> split into 2 real cues.
    assert len(out) == 2
    assert out[0][2] == "Yes."
    assert out[1][2] == "Go over there right now and tell me exactly what all happened."
    assert out[0][1] == 0.4 and out[1][0] == 0.6  # exact word times, no shift


def test_no_words_falls_back_to_budget_trim() -> None:
    seg = Segment(10.0, 30.0, "This is a fairly short line of speech.")
    out = _tighten_to_words([seg], [])
    assert len(out) == 1
    assert out[0].start == 10.0
    assert out[0].end <= 30.0  # trimmed, never extended


def test_punctuation_keeps_no_leading_space() -> None:
    words = _w(("Hello,", 0.0, 0.3), ("world!", 0.3, 0.7))
    out = _split_long_segment(words, "Hello, world!")
    assert out[0][2] == "Hello, world!"
