"""Unit tests for mix-label track assembly (ROADMAP #3/#9 pipeline vision).
No real mutagen files or Discogs calls - genre_year_lookup is injected.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import os
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "lib", "mix_label.py")
_spec = importlib.util.spec_from_file_location("mix_label", _MODPATH)
mix_label = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mix_label)


def test_format_duration():
    assert mix_label._format_duration(65) == "1:05"
    assert mix_label._format_duration(59) == "0:59"


def test_collect_mix_tracks_calls_lookup_once_per_album(tmp_path):
    album_dir = tmp_path / "Artist" / "Album"
    album_dir.mkdir(parents=True)
    (album_dir / "1-Song A.mp3").touch()
    (album_dir / "2-Song B.mp3").touch()

    fake_tags = {"title": "Song A", "artist": "Artist", "album": "Album", "duration": 200}
    calls = []

    def fake_lookup(artist, album):
        calls.append((artist, album))
        return "Rock", "2001"

    with patch.object(mix_label, "_read_tags", return_value=fake_tags):
        tracks = mix_label.collect_mix_tracks(str(tmp_path), genre_year_lookup=fake_lookup)

    assert len(tracks) == 2
    assert calls == [("Artist", "Album")]  # cached, not called per-track
    assert all(t["genre"] == "Rock" and t["year"] == "2001" for t in tracks)


def test_format_tracklist_lines_omits_missing_genre_year():
    tracks = [
        {"title": "A", "artist": "X", "album": "Y", "duration": 65, "genre": None, "year": None},
        {"title": "B", "artist": "X", "album": "Y", "duration": 60, "genre": "Rock", "year": "1999"},
    ]
    lines = mix_label.format_tracklist_lines(tracks)
    assert lines[0] == "A — X (Y) 1:05"
    assert lines[1] == "B — X (Y, 1999) [Rock] 1:00"
