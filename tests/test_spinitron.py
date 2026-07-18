"""Unit tests for the Spinitron matching/reorder core (ROADMAP #1).

Pure logic only - no network, no API key, no drive. The `fetch_recent_spins`
client is intentionally not exercised here (it needs the user's real key); it
is thin by design so everything that carries logic is tested below.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "lib", "spinitron.py")
_spec = importlib.util.spec_from_file_location("spinitron", _MODPATH)
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)


def test_normalize_strips_qualifiers_and_punctuation():
    assert sp._normalize("Do It Right Now (Instrumental)") == "do it right now"
    assert sp._normalize("L.A. Woman!") == "l a woman"
    assert sp._normalize("  Multiple   Spaces  ") == "multiple spaces"
    assert sp._normalize(None) == ""


def test_similarity_case_and_punctuation_insensitive():
    assert sp._similarity("Louisiana", "louisiana!") == 1.0
    assert sp._similarity("The Beatles", "beatles") > 0.7
    assert sp._similarity("Hello", "Goodbye") < 0.5


def test_spin_matches_requires_both_artist_and_title():
    spin = {"artist": "Fela Kuti", "song": "Water No Get Enemy"}
    assert sp.spin_matches_track(spin, "fela kuti", "water no get enemy")
    # Same artist, different song -> no match (artist alone must not front-load).
    assert not sp.spin_matches_track(spin, "Fela Kuti", "Zombie")
    # Same song title, different artist -> no match.
    assert not sp.spin_matches_track(spin, "Some Cover Band", "Water No Get Enemy")


def test_matched_track_numbers_album_artist():
    titles = {1: "Zombie", 2: "Water No Get Enemy", 3: "Shakara"}
    spins = [
        {"artist": "Fela Kuti", "song": "Water No Get Enemy"},
        {"artist": "Fela Kuti", "song": "Shakara (Oloje)"},   # qualifier ignored
    ]
    matched = sp.matched_track_numbers(titles, "Fela Kuti", spins)
    assert matched == {2, 3}


def test_matched_track_numbers_per_track_artist_for_compilations():
    titles = {1: "Song A", 2: "Song B"}
    per_artist = {1: "Artist One", 2: "Artist Two"}
    spins = [{"artist": "Artist Two", "song": "Song B"}]
    matched = sp.matched_track_numbers(
        titles, "Various", spins, per_track_artist=per_artist)
    assert matched == {2}


def test_matched_empty_when_no_spins():
    titles = {1: "Anything"}
    assert sp.matched_track_numbers(titles, "Someone", []) == set()


def test_reorder_preserves_group_order():
    # matched {5, 2} -> those first in queue order (2 before 5), rest unchanged.
    assert sp.reorder_queue([1, 2, 3, 4, 5], {5, 2}) == [2, 5, 1, 3, 4]


def test_reorder_no_matches_is_identity():
    assert sp.reorder_queue([1, 2, 3], set()) == [1, 2, 3]


def test_reorder_ignores_matches_not_in_queue():
    # already-ripped tracks (not in queue) in the matched set are harmless.
    assert sp.reorder_queue([1, 2], {2, 99}) == [2, 1]


def test_reorder_returns_new_list():
    q = [1, 2, 3]
    out = sp.reorder_queue(q, {3})
    assert out == [3, 1, 2]
    assert q == [1, 2, 3]   # input untouched
