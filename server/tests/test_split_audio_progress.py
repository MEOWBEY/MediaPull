"""Unit tests for the ffmpeg stderr progress parser feeding the split-audio
percentage displayed inside the client's split button."""

import pytest

from app.split_audio import FfmpegProgress, _parse_ffmpeg_clock


class TestParseFfmpegClock:
    def test_hms_clock(self) -> None:
        assert _parse_ffmpeg_clock("time=00:01:30.00") == pytest.approx(90.0)

    def test_fractional_seconds(self) -> None:
        assert _parse_ffmpeg_clock("out_time=00:00:12.34") == pytest.approx(12.34)

    def test_microsecond_form(self) -> None:
        assert _parse_ffmpeg_clock("out_time_us=12340000") == pytest.approx(12.34)

    def test_millisecond_form(self) -> None:
        assert _parse_ffmpeg_clock("out_time_ms=12340") == pytest.approx(12.34)

    def test_lines_without_clock(self) -> None:
        for line in (
            "",
            "  Metadata:",
            "Stream #0:0(und): Audio: aac (LC)",
            "Duration: 00:05:23.34, start: 0.000000, bitrate: 1000 kb/s",
            "progress=end",
        ):
            assert _parse_ffmpeg_clock(line) is None


class TestFfmpegProgress:
    def test_pending_until_duration_seen(self) -> None:
        p = FfmpegProgress()
        # A time= line before Duration now returns 0.1 (early-progress signal)
        # so the client doesn't stay stuck at 5% for short files.
        assert p.push("time=00:00:50.00") == pytest.approx(0.1)
        # The Duration line itself carries no clock value — still no ratio.
        assert p.push("Duration: 01:00:00.00, start: 0.0") is None

    def test_progress_ratio(self) -> None:
        p = FfmpegProgress()
        p.push("Duration: 00:02:00.00, start: 0.000000, bitrate: 500 kb/s")
        assert p.push("time=00:01:00.00") == pytest.approx(0.5)
        assert p.push("time=00:02:00.00") == pytest.approx(1.0)

    def test_clamped_to_one(self) -> None:
        p = FfmpegProgress()
        p.push("Duration: 00:01:00.00, start: 0.0")
        # Encoders sometimes overshoot the reported duration slightly.
        assert p.push("time=00:01:01.00") == 1.0

    def test_unknown_duration_stays_none(self) -> None:
        p = FfmpegProgress()
        # When duration is never provided, the first time= line returns 0.1
        # as an early-progress hint; subsequent lines without duration also
        # return 0.1 (not None) to keep the bar moving.
        assert p.push("time=00:01:00.00") == pytest.approx(0.1)