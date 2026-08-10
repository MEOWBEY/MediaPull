"""Post-process pass: noise/duplicate cleanup plus the no-word-timestamps
fallback for splitting long cues (proportional, span-preserving)."""

from __future__ import annotations

from app.postprocess import _split_long_cues, clean
from app.transcribe.base import Segment


def _seg(start: float, end: float, text: str) -> Segment:
    return Segment(start, end, text)


def test_strips_noise_placeholders() -> None:
    segs = [
        _seg(0.0, 1.0, "♪ music ♪"),
        _seg(1.0, 2.0, "[Music]"),
        _seg(2.0, 3.0, "(Applause)"),
        _seg(3.0, 4.0, "Hello there."),
    ]
    out = clean(segs)
    assert [s.text for s in out] == ["Hello there"]


def test_collapses_consecutive_duplicates() -> None:
    segs = [
        _seg(0.0, 1.0, "Hello there."),
        _seg(1.0, 2.0, "Hello there."),
        _seg(2.0, 3.0, "This is real."),
    ]
    out = clean(segs)
    assert [s.text for s in out] == ["Hello there", "This is real"]


def test_keeps_short_cue_adjacent_to_speech() -> None:
    # "No." is short but sits right next to real speech — must be kept
    # (with its end period stripped like every other cue).
    segs = [_seg(0.0, 0.4, "No."), _seg(0.5, 3.0, "I did not say that at all.")]
    assert [s.text for s in clean(segs)] == ["No", "I did not say that at all"]


def test_removes_trailing_periods_but_keeps_question_and_exclamation() -> None:
    segs = [
        _seg(0.0, 1.0, "Let's go."),
        _seg(1.0, 2.0, "Fine.."),
        _seg(2.0, 3.0, "Really?."),
        _seg(3.0, 4.0, "Wow!."),
        _seg(4.0, 5.0, "What?"),
    ]
    out = clean(segs)
    assert [s.text for s in out] == ["Let's go", "Fine", "Really?", "Wow!", "What?"]
    # Timing is untouched by the cosmetic strip.
    assert [s.start for s in out] == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_drops_cue_that_is_only_periods() -> None:
    segs = [_seg(0.0, 1.0, "Hello there."), _seg(1.0, 2.0, "..."), _seg(2.0, 3.0, "Later.")]
    out = clean(segs)
    assert [s.text for s in out] == ["Hello there", "Later"]


def test_drops_isolated_short_single_word_cue() -> None:
    segs = [_seg(0.0, 2.0, "Hello there."), _seg(10.0, 10.3, "Hmm."), _seg(12.0, 13.0, "Later.")]
    out = clean(segs)
    assert "Hmm." not in [s.text for s in out]


def test_proportional_split_preserves_total_span() -> None:
    seg = _seg(10.0, 20.0, "First sentence here. Second sentence here. Third sentence here.")
    out = _split_long_cues([seg])
    assert len(out) == 3
    assert out[0].start == 10.0
    assert out[-1].end == 20.0
    # Each cue's duration is its share of the total character count.
    total = len("First sentence here.") + len("Second sentence here.") + len("Third sentence here.")
    assert abs(out[0].end - out[0].start - 10.0 * len("First sentence here.") / total) < 0.01
    # Cues tile the span without gaps or overlaps.
    for a, b in zip(out, out[1:]):
        assert a.end == b.start


def test_proportional_split_merges_tiny_sentences() -> None:
    seg = _seg(0.0, 9.0, "This is the first long sentence here. Yes. And the second part follows right after that.")
    out = _split_long_cues([seg])
    assert len(out) == 2
    assert out[0].text == "This is the first long sentence here. Yes."
    assert out[1].text == "And the second part follows right after that."


def test_short_cues_never_split() -> None:
    seg = _seg(0.0, 3.0, "This one is short. So is this one.")
    assert _split_long_cues([seg]) == [seg]


def test_split_long_cues_flag_disables_fallback() -> None:
    seg = _seg(0.0, 9.0, "This is the first long sentence here. And the second part follows right after that. Take care.")
    out = clean([seg], split_long_cues=False)
    assert [o.text for o in out] == ["This is the first long sentence here. And the second part follows right after that. Take care"]
    assert out[0].start == 0.0 and out[0].end == 9.0  # timing unchanged
    out = clean([seg], split_long_cues=True)
    assert len(out) == 2  # "Take care." is too short to stand alone, merges back
    assert out[-1].end == 9.0  # split preserves the span, then strips the final dot
