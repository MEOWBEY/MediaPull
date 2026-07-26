"""Native (source-provided) subtitle listing + format codec metadata tests.

Covers the extractor-agnostic subtitle path: yt-dlp only populates
``subtitles``/``automatic_captions`` for most extractors (Vimeo, ...) when the
``writesubtitles``/``writeautomaticsub`` params are set, so the options build
must request them -- YouTube alone fills them unconditionally.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from app.config import Settings
from app.extractor import Extractor
from app.models import VideoFormat, VideoInfo
from app.serializers import to_client_video


# ----- yt-dlp options: subtitles must be requested for ALL extractors ----


def test_ydl_opts_request_subtitles_and_auto_captions():
    extractor = Extractor(Settings())
    for generic in (False, True):
        opts = extractor._build_ydl_opts(generic=generic)
        assert opts["writesubtitles"] is True
        assert opts["writeautomaticsub"] is True
        # Metadata-only invariant: the app never downloads media here.
        assert opts["extract_flat"] is False


# ----- track selection is extractor-agnostic -----------------------------


def test_select_subtitle_tracks_non_youtube_vtt():
    """A Vimeo-shaped info dict (plain .vtt file URLs, no timedtext) lists
    its manual captions with the URL untouched."""
    info = {
        "subtitles": {
            "en": [
                {
                    "ext": "vtt",
                    "url": "https://captions.example.com/texttrack/123.vtt",
                    "name": "English",
                }
            ]
        },
        "automatic_captions": {},
    }
    tracks = Extractor._select_subtitle_tracks(info)
    assert len(tracks) == 1
    assert tracks[0].lang == "en"
    assert tracks[0].label == "English"
    assert tracks[0].ext == "vtt"
    assert tracks[0].is_auto is False
    assert tracks[0].url == "https://captions.example.com/texttrack/123.vtt"


def test_select_subtitle_tracks_manual_wins_over_auto_same_lang():
    info = {
        "subtitles": {"en": [{"ext": "vtt", "url": "https://x.example/manual.vtt"}]},
        "automatic_captions": {"en": [{"ext": "vtt", "url": "https://x.example/auto.vtt"}]},
    }
    tracks = Extractor._select_subtitle_tracks(info)
    assert len(tracks) == 1
    assert tracks[0].url == "https://x.example/manual.vtt"
    assert tracks[0].is_auto is False


def test_select_subtitle_tracks_srt_fallback_keeps_true_ext():
    """A source that only offers .srt is listed with ext=srt so the client's
    parser picks the right grammar."""
    info = {
        "subtitles": {"de": [{"ext": "srt", "url": "https://x.example/de.srt"}]},
        "automatic_captions": {},
    }
    tracks = Extractor._select_subtitle_tracks(info)
    assert tracks[0].ext == "srt"
    assert tracks[0].url == "https://x.example/de.srt"


def test_select_subtitle_tracks_timedtext_forced_to_vtt():
    """YouTube timedtext entries (often json3 first) are rewritten to fmt=vtt."""
    info = {
        "subtitles": {},
        "automatic_captions": {
            "en": [
                {
                    "ext": "json3",
                    "url": "https://www.youtube.com/api/timedtext?v=abc&fmt=json3",
                }
            ]
        },
    }
    tracks = Extractor._select_subtitle_tracks(info)
    assert tracks[0].ext == "vtt"
    query = parse_qs(urlparse(tracks[0].url).query)
    assert query["fmt"] == ["vtt"]
    assert tracks[0].is_auto is True
    assert tracks[0].label.endswith("(auto)")


def test_select_subtitle_tracks_video_language_ranked_first():
    info = {
        "language": "fr",
        "subtitles": {
            "ab": [{"ext": "vtt", "url": "https://x.example/ab.vtt"}],
            "en": [{"ext": "vtt", "url": "https://x.example/en.vtt"}],
            "fr": [{"ext": "vtt", "url": "https://x.example/fr.vtt"}],
        },
        "automatic_captions": {},
    }
    tracks = Extractor._select_subtitle_tracks(info)
    assert [t.lang for t in tracks] == ["fr", "en", "ab"]


def test_select_subtitle_tracks_skips_entries_without_url():
    info = {
        "subtitles": {"en": [{"ext": "vtt", "data": "WEBVTT\n"}]},
        "automatic_captions": {},
    }
    assert Extractor._select_subtitle_tracks(info) == []


# ----- per-format codec metadata (has-sound hint for any site) ----------


def test_to_format_passes_codecs_through():
    fmt = Extractor._to_format(
        {
            "url": "https://cdn.example.com/v.mp4",
            "ext": "mp4",
            "format_id": "22",
            "acodec": "mp4a.40.2",
            "vcodec": "avc1.64001f",
        }
    )
    assert fmt.acodec == "mp4a.40.2"
    assert fmt.vcodec == "avc1.64001f"
    assert fmt.video_only is False


def test_to_format_video_only_and_unknown_codecs():
    video_only = Extractor._to_format(
        {
            "url": "https://cdn.example.com/v137.mp4",
            "format_id": "137",
            "acodec": "none",
            "vcodec": "avc1.640028",
        }
    )
    assert video_only.video_only is True
    assert video_only.acodec == "none"

    # No codec info at all -> None (unknown), never a false "no sound" claim.
    unknown = Extractor._to_format(
        {"url": "https://cdn.example.com/clip.mp4", "format_id": "x"}
    )
    assert unknown.acodec is None
    assert unknown.vcodec is None
    assert unknown.video_only is False


def test_client_format_includes_codecs():
    info = VideoInfo(
        id="1",
        title="t",
        webpage_url="https://example.com/v",
        formats=[
            VideoFormat(
                format_id="f1",
                url="https://cdn.example/v.mp4",
                acodec="none",
                vcodec="vp9",
            )
        ],
    )
    client = to_client_video(info)
    assert client.formats[0].acodec == "none"
    assert client.formats[0].vcodec == "vp9"
