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
