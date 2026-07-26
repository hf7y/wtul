"""Unit tests for AcoustID/Discogs metadata lookup (ROADMAP #2).

Network and fpcalc are mocked throughout - no real API calls, no real
audio files.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import json
import os
import subprocess
from unittest.mock import patch

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "lib", "metadata_lookup.py")
_spec = importlib.util.spec_from_file_location("metadata_lookup", _MODPATH)
ml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml)


class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


class _FakeResponse:
    def __init__(self, body_dict):
        self._body = json.dumps(body_dict).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_fingerprint_file_parses_fpcalc_json():
    fake = _FakeCompletedProcess(0, json.dumps({"duration": 180, "fingerprint": "AB12"}))
    with patch.object(ml.subprocess, "run", return_value=fake):
        duration, fp = ml.fingerprint_file("/fake/track.mp3")
    assert duration == 180
    assert fp == "AB12"


def test_fingerprint_file_missing_binary_returns_none():
    with patch.object(ml.subprocess, "run", side_effect=FileNotFoundError):
        assert ml.fingerprint_file("/fake/track.mp3") == (None, None)


def test_fingerprint_file_nonzero_exit_returns_none():
    fake = _FakeCompletedProcess(1, "")
    with patch.object(ml.subprocess, "run", return_value=fake):
        assert ml.fingerprint_file("/fake/track.mp3") == (None, None)


def test_fingerprint_file_non_dict_json_returns_none():
    # Well-formed JSON that isn't an object (e.g. a fpcalc build with a
    # broken/changed output shape) shouldn't crash the per-track loop.
    fake = _FakeCompletedProcess(0, json.dumps([1, 2, 3]))
    with patch.object(ml.subprocess, "run", return_value=fake):
        assert ml.fingerprint_file("/fake/track.mp3") == (None, None)


def test_acoustid_lookup_parses_results():
    body = {
        "status": "ok",
        "results": [{
            "score": 0.93,
            "recordings": [{
                "title": "Water No Get Enemy",
                "artists": [{"name": "Fela Kuti"}],
                "releasegroups": [{"title": "Expensive Shit"}],
            }],
        }],
    }
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse(body)):
        guesses = ml.acoustid_lookup("key", 300, "fp")
    assert guesses == [{"score": 0.93, "artist": "Fela Kuti",
                         "title": "Water No Get Enemy", "album": "Expensive Shit"}]


def test_acoustid_lookup_no_match_returns_empty():
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse({"status": "ok", "results": []})):
        assert ml.acoustid_lookup("key", 300, "fp") == []


def test_acoustid_lookup_network_error_returns_empty():
    with patch.object(ml.urllib.request, "urlopen", side_effect=OSError("boom")):
        assert ml.acoustid_lookup("key", 300, "fp") == []


def test_acoustid_lookup_non_dict_json_returns_empty():
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse(["oops"])):
        assert ml.acoustid_lookup("key", 300, "fp") == []


def test_acoustid_lookup_non_dict_nested_entries_skipped():
    # Well-formed JSON, but a non-dict entry anywhere inside results/
    # recordings/artists/releasegroups (a stray string/null) shouldn't
    # crash the parse - just be skipped like an empty entry would be.
    body = {
        "status": "ok",
        "results": [
            "oops",
            {
                "score": 0.9,
                "recordings": [
                    "oops",
                    {
                        "title": "Real Track",
                        "artists": [{"name": "Real Artist"}, "oops"],
                        "releasegroups": ["oops", {"title": "Real Album"}],
                    },
                ],
            },
        ],
    }
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse(body)):
        guesses = ml.acoustid_lookup("key", 300, "fp")
    assert guesses == [{"score": 0.9, "artist": "Real Artist",
                         "title": "Real Track", "album": "Real Album"}]


def test_best_album_guess_majority_vote():
    guesses = [
        {"score": 0.9, "artist": "Fela Kuti", "album": "Expensive Shit", "title": "A"},
        {"score": 0.8, "artist": "Fela Kuti", "album": "Expensive Shit", "title": "B"},
        {"score": 0.95, "artist": "Someone Else", "album": "Different Album", "title": "C"},
    ]
    artist, album, score = ml.best_album_guess(guesses)
    assert (artist, album, score) == ("Fela Kuti", "Expensive Shit", 0.9)


def test_best_album_guess_below_threshold_excluded():
    guesses = [{"score": 0.1, "artist": "X", "album": "Y", "title": "Z"}]
    assert ml.best_album_guess(guesses) == (None, None, 0)


def test_best_album_guess_empty_input():
    assert ml.best_album_guess([None, None]) == (None, None, 0)


def test_discogs_search_by_artist_returns_top_result():
    body = {"results": [{"title": "Fela Kuti - Expensive Shit"}]}
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse(body)):
        assert ml.discogs_search_by_artist("token", "Fela Kuti") == "Fela Kuti - Expensive Shit"


def test_discogs_search_by_artist_no_results():
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse({"results": []})):
        assert ml.discogs_search_by_artist("token", "Nobody") is None


def test_discogs_search_by_artist_non_dict_json_returns_none():
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse("oops")):
        assert ml.discogs_search_by_artist("token", "Nobody") is None


def test_discogs_search_by_artist_non_dict_result_entry_returns_none():
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse({"results": ["oops"]})):
        assert ml.discogs_search_by_artist("token", "Nobody") is None


def test_discogs_genre_year_prefers_release_title_match():
    body = {"results": [{"style": ["Shoegaze", "Drone", "Ambient"], "genre": ["Electronic"], "year": "2009"}]}
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse(body)) as mocked:
        genre, year = ml.discogs_genre_year("token", "belong", album="October Language")
    assert genre == "Shoegaze, Drone"
    assert year == "2009"
    # release_title search matched first try - only one request made, no artist-only fallback needed.
    assert mocked.call_count == 1


def test_discogs_genre_year_falls_back_to_artist_only():
    responses = [_FakeResponse({"results": []}), _FakeResponse({"results": [{"genre": ["Jazz"], "year": "1975"}]})]
    with patch.object(ml.urllib.request, "urlopen", side_effect=responses):
        genre, year = ml.discogs_genre_year("token", "Fela Kuti", album="Unmatched Title")
    assert genre == "Jazz"
    assert year == "1975"


def test_discogs_genre_year_skips_artist_only_fallback_for_self_titled_album():
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse({"results": []})) as mocked:
        genre, year = ml.discogs_genre_year("token", "Morgan Lane", album="Morgan Lane")
    assert (genre, year) == (None, None)
    # only the release_title search ran - no artist-only fallback for a self-titled album.
    assert mocked.call_count == 1


def test_discogs_genre_year_no_match_returns_none_none():
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse({"results": []})):
        genre, year = ml.discogs_genre_year("token", "Nobody")
    assert genre is None
    assert year is None


def test_discogs_genre_year_non_dict_json_returns_none_none():
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse("oops")):
        genre, year = ml.discogs_genre_year("token", "Nobody", album="Anything")
    assert (genre, year) == (None, None)


def test_discogs_genre_year_non_dict_result_entry_returns_none_none():
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse({"results": ["oops"]})):
        genre, year = ml.discogs_genre_year("token", "Nobody")
    assert (genre, year) == (None, None)


def test_resolve_disc_metadata_no_key_is_noop():
    assert ml.resolve_disc_metadata(["/a.mp3"], acoustid_key=None) == (None, None)


def test_resolve_disc_metadata_acoustid_only():
    fp_result = (180, "fp")
    guess = [{"score": 0.9, "artist": "Fela Kuti", "album": "Expensive Shit", "title": "A"}]
    with patch.object(ml, "fingerprint_file", return_value=fp_result), \
         patch.object(ml, "acoustid_lookup", return_value=guess):
        artist, album = ml.resolve_disc_metadata(["/a.mp3"], acoustid_key="key")
    assert (artist, album) == ("Fela Kuti", "Expensive Shit")


def test_resolve_disc_metadata_falls_back_to_discogs():
    fp_result = (180, "fp")
    guess = [{"score": 0.9, "artist": "Fela Kuti", "album": None, "title": "A"}]
    with patch.object(ml, "fingerprint_file", return_value=fp_result), \
         patch.object(ml, "acoustid_lookup", return_value=guess), \
         patch.object(ml, "discogs_search_by_artist", return_value="Zombie") as mock_discogs:
        artist, album = ml.resolve_disc_metadata(
            ["/a.mp3"], acoustid_key="key", discogs_token="token")
    assert (artist, album) == ("Fela Kuti", "Zombie")
    mock_discogs.assert_called_once_with("token", "Fela Kuti")


def test_resolve_disc_metadata_unfingerprintable_track_skipped():
    with patch.object(ml, "fingerprint_file", return_value=(None, None)):
        artist, album = ml.resolve_disc_metadata(["/a.mp3"], acoustid_key="key")
    assert (artist, album) == (None, None)


def test_resolve_disc_metadata_throttles_between_acoustid_calls():
    fp_result = (180, "fp")
    guess = [{"score": 0.9, "artist": "Fela Kuti", "album": "Expensive Shit", "title": "A"}]
    sleeps = []
    # track1 call at t=0.0; track2's pre-call check at t=0.1 (only 0.1s
    # elapsed, under the 0.35s floor -> must sleep 0.25s); its post-call
    # clock reads t=0.45 (as if the sleep+API call actually took that
    # long); track3's pre-call check at t=0.9 is already >=0.35s past
    # that -> no sleep needed for the second gap.
    ticks = iter([0.0, 0.1, 0.45, 0.9, 1.0])
    with patch.object(ml, "fingerprint_file", return_value=fp_result), \
         patch.object(ml, "acoustid_lookup", return_value=guess):
        ml.resolve_disc_metadata(
            ["/a.mp3", "/b.mp3", "/c.mp3"], acoustid_key="key",
            min_interval=0.35, sleep_fn=sleeps.append, clock=lambda: next(ticks))
    assert sleeps == [pytest.approx(0.25)]


def test_resolve_disc_metadata_no_sleep_when_calls_already_spaced_out():
    fp_result = (180, "fp")
    guess = [{"score": 0.9, "artist": "Fela Kuti", "album": "Expensive Shit", "title": "A"}]
    ticks = iter([0.0, 1.0, 1.0])
    with patch.object(ml, "fingerprint_file", return_value=fp_result), \
         patch.object(ml, "acoustid_lookup", return_value=guess):
        ml.resolve_disc_metadata(
            ["/a.mp3", "/b.mp3"], acoustid_key="key",
            min_interval=0.35, sleep_fn=lambda s: (_ for _ in ()).throw(AssertionError("should not sleep")),
            clock=lambda: next(ticks))


def _mb_release(artist="Radiohead", title="OK Computer", date="1997-05-21",
                score=100, **extra):
    rel = {"title": title, "score": score, "date": date,
           "artist-credit": [{"name": artist}]}
    rel.update(extra)
    return rel


def test_musicbrainz_search_parses_results():
    body = {"releases": [_mb_release()]}
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse(body)):
        results = ml.musicbrainz_search_release("radiohead ok computer")
    assert results == [{"artist": "Radiohead", "album": "OK Computer",
                        "year": "1997", "score": 100}]


def test_musicbrainz_search_dedupes_pressings_and_caps_at_limit():
    # One release typically appears once per pressing/country - the picker
    # should show distinct (artist, album) rows, not five identical lines.
    # Real pressings of one release differ by date/country, so the
    # duplicates here deliberately do too - dedupe must key on
    # (artist, album) alone, not on any pressing-level field.
    body = {"releases": [_mb_release(date=f"199{i}-01-01") for i in range(4)]
            + [_mb_release(title=f"Album {i}") for i in range(10)]}
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse(body)):
        results = ml.musicbrainz_search_release("radiohead", limit=5)
    assert len(results) == 5
    assert results[0]["album"] == "OK Computer"
    assert [r["album"] for r in results[1:]] == ["Album 0", "Album 1",
                                                 "Album 2", "Album 3"]


def test_musicbrainz_search_joins_multiple_artist_credits():
    body = {"releases": [_mb_release(
        **{"artist-credit": [{"name": "David Byrne"}, {"name": "Brian Eno"}]})]}
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse(body)):
        results = ml.musicbrainz_search_release("bush of ghosts")
    assert results[0]["artist"] == "David Byrne & Brian Eno"


def test_musicbrainz_search_empty_query_never_hits_network():
    with patch.object(ml.urllib.request, "urlopen",
                      side_effect=AssertionError("should not be called")):
        assert ml.musicbrainz_search_release("") == []
        assert ml.musicbrainz_search_release("   ") == []


def test_musicbrainz_search_no_results_returns_empty():
    with patch.object(ml.urllib.request, "urlopen",
                      return_value=_FakeResponse({"releases": []})):
        assert ml.musicbrainz_search_release("nobody") == []


def test_musicbrainz_search_network_error_returns_empty():
    with patch.object(ml.urllib.request, "urlopen", side_effect=OSError("boom")):
        assert ml.musicbrainz_search_release("radiohead") == []


def test_musicbrainz_search_non_dict_json_returns_empty():
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse(["oops"])):
        assert ml.musicbrainz_search_release("radiohead") == []


def test_musicbrainz_search_malformed_entries_skipped():
    # Same well-formed-but-wrong-shaped discipline as the AcoustID/Discogs
    # parsers: stray non-dict entries, missing titles, credit lists holding
    # junk, and short/garbage dates are all skipped, never raised on.
    body = {"releases": [
        "oops",
        {"score": 90},                                        # no title
        _mb_release(**{"artist-credit": "not-a-list"}),       # bad credits
        _mb_release(**{"artist-credit": ["oops", {"x": 1}]}), # no usable name
        _mb_release(artist="Real Artist", title="Real Album",
                    date="199", score="high"),                # bad date+score
    ]}
    with patch.object(ml.urllib.request, "urlopen", return_value=_FakeResponse(body)):
        results = ml.musicbrainz_search_release("whatever")
    assert results == [{"artist": "Real Artist", "album": "Real Album",
                        "year": None, "score": None}]


def test_musicbrainz_search_releases_not_a_list_returns_empty():
    with patch.object(ml.urllib.request, "urlopen",
                      return_value=_FakeResponse({"releases": {"oops": 1}})):
        assert ml.musicbrainz_search_release("radiohead") == []
