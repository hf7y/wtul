"""End-to-end rehearsal of rip_session() against the simulated drive.

This is the coverage this project has never had: every other test file
exercises a leaf parser, while `rip_session()` - the function that actually
sequences a rip - could only be run with a disc in a real drive, so its
control flow (scrape -> tracklist -> per-track loop -> resume-skip ->
partial-disc retry signal -> eject -> catalog write-back) was only ever
verified by watching a real rip happen.

None of this replaces hardware verification (see lib/fake_drive.py's
docstring). It verifies wtul-rip's own logic given a disc-shaped
interaction, so a scarce real-disc session isn't spent rediscovering a bug
that was findable here.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import json
import os
import sys
from importlib.machinery import SourceFileLoader

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "bin", "wtul-rip")

SPEC = {
    "discid": "700a8608",
    "artist": "Belong",
    "album": "October Language",
    "read_speed": "4.2",
    "tracks": [
        {"title": "I Never Lose", "length": "3:00"},
        {"title": "Late Night", "length": "2:30"},
        {"title": "Remove the Inside", "length": "4:10"},
    ],
}


def _write_spec(tmp_path, **over):
    spec = json.loads(json.dumps(SPEC))
    spec.update(over)
    path = tmp_path / "disc.json"
    path.write_text(json.dumps(spec))
    return str(path)


def _load_rehearsal(monkeypatch, tmp_path, spec_path):
    """Load bin/wtul-rip in rehearsal mode, fully sandboxed and offline."""
    monkeypatch.setattr("sys.argv", ["wtul-rip"])
    # HOME redirect keeps the real ~/.config/wtul/secrets.env out of this.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("WTUL_SIMULATE_DRIVE", spec_path)
    monkeypatch.setenv("WTUL_SIMULATE_ROOT", str(tmp_path / "sandbox"))
    monkeypatch.delenv("CATALOG_WRITEBACK_URL", raising=False)

    loader = SourceFileLoader("wtul_rip_rehearsal", _MODPATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)

    # A real selectable stdin at EOF: rip_session() and _sh_live_simulated()
    # both select() on sys.stdin, and pytest's captured stdin has no fileno.
    monkeypatch.setattr(mod.sys, "stdin", open(os.devnull))
    # Spinitron is a live network scrape inside rip_session() - a rehearsal
    # must not depend on the station's website being up.
    monkeypatch.setattr(mod.spinitron, "fetch_recent_spins_public", lambda *a, **k: [])

    mod.init_simulation()
    assert mod.SIM is not None
    return mod


# -- containment: the thing that must never break -----------------------


def test_rehearsal_sandboxes_away_from_the_real_music_library(monkeypatch, tmp_path):
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    assert os.path.join("Music", "mixes") not in mod.RIPDIR
    assert str(tmp_path / "sandbox") in mod.RIPDIR
    assert str(tmp_path / "sandbox") in mod.LOGDIR


def test_rehearsal_uses_a_separate_lockfile(monkeypatch, tmp_path):
    """So a rehearsal neither blocks nor is blocked by a real rip."""
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    assert "-sim-" in mod.LOCKFILE


def test_not_simulating_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["wtul-rip"])
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("WTUL_SIMULATE_DRIVE", raising=False)
    loader = SourceFileLoader("wtul_rip_real", _MODPATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    assert mod.SIMULATING is False
    assert mod.SIM is None
    assert os.path.join("Music", "mixes") in mod.RIPDIR


def test_bad_spec_exits_rather_than_using_the_real_drive(monkeypatch, tmp_path):
    """The one failure mode worth aborting over: asked for a rehearsal,
    silently rips a real disc instead."""
    monkeypatch.setattr("sys.argv", ["wtul-rip"])
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("WTUL_SIMULATE_DRIVE", "/nonexistent/disc.json")
    loader = SourceFileLoader("wtul_rip_badspec", _MODPATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    with pytest.raises(SystemExit) as e:
        mod.init_simulation()
    assert e.value.code != 0
    assert mod.SIM is None


# -- the happy path -----------------------------------------------------


def test_full_disc_rips_all_tracks_and_reports_done(monkeypatch, tmp_path, capsys):
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    done = mod.rip_session(mod.DEV)
    assert done is True
    out = capsys.readouterr().out
    assert "3/3 tracks ripped" in out
    assert "Belong - October Language (3 tracks)" in out
    album_dir = os.path.join(mod.RIPDIR, "Belong", "October Language")
    assert sorted(os.listdir(album_dir)) == [
        "01-I Never Lose.mp3", "02-Late Night.mp3", "03-Remove the Inside.mp3"]


def test_full_disc_ejects_and_cleans_up_its_tempdir(monkeypatch, tmp_path):
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.rip_session(mod.DEV)
    assert mod.SIM.ejected is True
    # A completed disc removes its own scratch dir - otherwise the stale-
    # tempdir pruner is the only thing that ever would.
    assert not os.path.isdir(mod.SIM.tempdir)


def test_tracklist_shows_real_durations_from_the_toc(monkeypatch, tmp_path, capsys):
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.rip_session(mod.DEV)
    out = capsys.readouterr().out
    assert "03:00" in out and "02:30" in out and "04:10" in out


def test_session_log_is_written_and_marked_simulated(monkeypatch, tmp_path):
    """A rehearsal transcript must be unmistakable in history() - the whole
    risk of this mode is a fake rip later being read as a real one."""
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.rip_session(mod.DEV)
    logs = os.listdir(mod.LOGDIR)
    assert len(logs) == 1
    assert "SIMULATED" in logs[0]
    body = open(os.path.join(mod.LOGDIR, logs[0])).read()
    assert "SIMULATED REHEARSAL" in body
    assert "session finished - 3/3 tracks ripped" in body


def test_read_speed_line_reaches_the_log(monkeypatch, tmp_path):
    """#6's rip-speed monitoring parses these lines out of the session log;
    a rehearsal is the only way to produce one without a disc."""
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.rip_session(mod.DEV)
    logs = os.listdir(mod.LOGDIR)
    body = open(os.path.join(mod.LOGDIR, logs[0])).read()
    assert "4.2x" in body


# -- the unhappy paths, which a real disc rarely reproduces on demand ---


def test_unmatched_disc_falls_back_to_unknown_and_still_rips(monkeypatch, tmp_path, capsys):
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path, match=False))
    done = mod.rip_session(mod.DEV)
    assert done is True
    out = capsys.readouterr().out
    assert "No CDDB/MusicBrainz match" in out
    # The disc-ID-suffixed folder is what keeps unidentified discs from all
    # colliding in one "Unknown Album" directory.
    assert os.path.isdir(os.path.join(mod.RIPDIR, "Unknown Artist",
                                      "Unknown Album (700a8608)"))


def test_failed_track_leaves_disc_for_retry(monkeypatch, tmp_path, capsys):
    tracks = json.loads(json.dumps(SPEC["tracks"]))
    tracks[1]["fails"] = True
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path, tracks=tracks))
    done = mod.rip_session(mod.DEV)
    assert done is False, "a partly-failed disc must stay in the drive for retry"
    out = capsys.readouterr().out
    assert "2/3 tracks ripped" in out
    assert "Some tracks failed" in out
    assert mod.SIM.ejected is False, "must not eject a disc with tracks still to get"


def test_retry_after_failure_only_rerips_the_missing_track(monkeypatch, tmp_path, capsys):
    """The resume path: a second session must skip what's already on disk.
    This is the behaviour the TOC-discid resume fix existed to protect, and
    it has never had a test because it needs two rips of one disc."""
    tracks = json.loads(json.dumps(SPEC["tracks"]))
    tracks[1]["fails"] = True
    spec_path = _write_spec(tmp_path, tracks=tracks)
    mod = _load_rehearsal(monkeypatch, tmp_path, spec_path)
    assert mod.rip_session(mod.DEV) is False
    capsys.readouterr()

    # Second pass with the same sandbox, disc now readable (as if reseated).
    mod2 = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    assert mod2.rip_session(mod2.DEV) is True
    out = capsys.readouterr().out
    assert "1/1 tracks ripped" in out, "should only re-rip the one missing track"
    assert "(done)" in out, "already-ripped tracks should be flagged in the list"
    assert mod2.SIM.ripped == [2]


def test_fully_ripped_disc_reinserted_does_no_work(monkeypatch, tmp_path, capsys):
    spec_path = _write_spec(tmp_path)
    mod = _load_rehearsal(monkeypatch, tmp_path, spec_path)
    mod.rip_session(mod.DEV)
    capsys.readouterr()
    mod2 = _load_rehearsal(monkeypatch, tmp_path, spec_path)
    assert mod2.rip_session(mod2.DEV) is True
    assert "All tracks already ripped" in capsys.readouterr().out
    assert mod2.SIM.ripped == []


def test_punctuated_disc_lands_where_wtul_rip_looks_and_resumes(monkeypatch, tmp_path, capsys):
    """The 2026-07-25 munging bug, end to end.

    An apostrophe/colon/"?" in the metadata is the common case, not an edge
    one - abcde strips them from the folder name (abcde.conf's
    `mungefilename`) and wtul-rip used to look for the unstripped name, so
    reinserting such a disc re-ripped every track. The assertion on the
    directory NAME matters as much as the resume behaviour: without it this
    test would still pass if both halves agreed on a wrong folder, which is
    exactly how the rehearsal harness missed the bug in the first place.
    """
    spec_path = _write_spec(tmp_path, artist="Guns N' Roses",
                            album="Appetite: For Destruction?")
    mod = _load_rehearsal(monkeypatch, tmp_path, spec_path)
    assert mod.rip_session(mod.DEV) is True
    capsys.readouterr()

    where = mod.album_dir_path("Guns N' Roses", "Appetite: For Destruction?",
                               SPEC["discid"])
    assert os.path.basename(os.path.dirname(where)) == "Guns N Roses"
    assert os.path.basename(where) == "Appetite- For Destruction"
    assert sorted(os.listdir(where)) == ["01-I Never Lose.mp3", "02-Late Night.mp3",
                                         "03-Remove the Inside.mp3"]

    mod2 = _load_rehearsal(monkeypatch, tmp_path, spec_path)
    assert mod2.rip_session(mod2.DEV) is True
    assert "All tracks already ripped" in capsys.readouterr().out
    assert mod2.SIM.ripped == []


def test_every_track_failing_reports_zero_and_holds_the_disc(monkeypatch, tmp_path, capsys):
    tracks = [dict(t, fails=True) for t in json.loads(json.dumps(SPEC["tracks"]))]
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path, tracks=tracks))
    assert mod.rip_session(mod.DEV) is False
    assert "0/3 tracks ripped" in capsys.readouterr().out


def test_single_track_disc_rips(monkeypatch, tmp_path, capsys):
    mod = _load_rehearsal(monkeypatch, tmp_path,
                          _write_spec(tmp_path, tracks=[{"title": "Only One",
                                                         "length": "1:30"}]))
    assert mod.rip_session(mod.DEV) is True
    assert "1/1 tracks ripped" in capsys.readouterr().out


def test_spinitron_failure_does_not_abort_the_rip(monkeypatch, tmp_path, capsys):
    """Spinitron is informational only; a network failure mid-scrape must
    never cost a rip."""
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))

    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(mod.spinitron, "fetch_recent_spins_public", boom)
    assert mod.rip_session(mod.DEV) is True
    out = capsys.readouterr().out
    assert "Spinitron lookup failed" in out
    assert "3/3 tracks ripped" in out


def test_matched_spins_are_reported_as_informational(monkeypatch, tmp_path, capsys):
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    monkeypatch.setattr(mod.spinitron, "matched_track_numbers", lambda *a, **k: {2})
    assert mod.rip_session(mod.DEV) is True
    out = capsys.readouterr().out
    assert "1 track(s) already played on air" in out
    # Informational only - it must not reorder or restrict the rip.
    assert "3/3 tracks ripped" in out


def test_disc_present_false_reports_an_empty_drive(monkeypatch, tmp_path):
    mod = _load_rehearsal(monkeypatch, tmp_path,
                          _write_spec(tmp_path, disc_present=False))
    assert mod.disc_audio_track_count(mod.DEV) == 0


def test_status_reports_the_simulated_disc(monkeypatch, tmp_path, capsys):
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.status()
    out = capsys.readouterr().out
    assert "Disc present: yes" in out
    assert "3 audio tracks" in out


def test_rehearsal_never_posts_to_the_real_rotation_catalog(monkeypatch, tmp_path, capsys):
    """The containment bug this mode actually shipped with, on 2026-07-25: a
    sandboxed RIPDIR still left the catalog write-back pointed at the real
    sheet (CATALOG_WRITEBACK_URL comes from ~/.config/wtul/secrets.env), so a
    rehearsal logged a fake album into the station's live catalog - and #8
    built no delete endpoint, so it had to come out by hand."""
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.CATALOG_WRITEBACK_URL = "https://example.invalid/exec"
    calls = []
    monkeypatch.setattr(mod.catalog_writeback, "write_row",
                        lambda url, row: calls.append(row) or True)
    assert mod.rip_session(mod.DEV) is True
    assert calls == [], "a rehearsal must never write to the real catalog"
    assert "SUPPRESSED" in capsys.readouterr().out


def test_catalog_writeback_fires_only_on_a_complete_disc(monkeypatch, tmp_path):
    """The underlying rule (a half-ripped album must not reach the rotation
    catalog), rehearsed with the suppression opted out of and write_row
    injected - so nothing leaves this process either way."""
    monkeypatch.setenv("WTUL_SIMULATE_ALLOW_CATALOG", "1")
    tracks = json.loads(json.dumps(SPEC["tracks"]))
    tracks[1]["fails"] = True
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path, tracks=tracks))
    assert mod.SIMULATE_ALLOW_CATALOG is True
    mod.CATALOG_WRITEBACK_URL = "https://example.invalid/exec"
    calls = []
    monkeypatch.setattr(mod.catalog_writeback, "write_row",
                        lambda url, row: calls.append(row) or True)
    assert mod.rip_session(mod.DEV) is False
    assert calls == []

    mod2 = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod2.CATALOG_WRITEBACK_URL = "https://example.invalid/exec"
    calls2 = []
    monkeypatch.setattr(mod2.catalog_writeback, "write_row",
                        lambda url, row: calls2.append(row) or True)
    assert mod2.rip_session(mod2.DEV) is True
    assert len(calls2) == 1
    assert calls2[0]["ARTIST"] == "Belong"
    assert calls2[0]["LOCAL"] is True


# -- `fix <discid>` on a rehearsed unidentified disc ---------------------
#
# This is the other stability-milestone criterion's logic (#2's metadata-fix
# path). It had no coverage either, for the same reason: producing an
# "Unknown Album (discid)" folder to fix needed a real unidentified disc.
# The AcoustID/Discogs lookup itself is injected here - it is a real network
# call in production and already live-verified separately.


def _rehearse_unidentified(monkeypatch, tmp_path):
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path, match=False))
    assert mod.rip_session(mod.DEV) is True
    return mod


def test_fix_by_discid_finds_the_rehearsed_unknown_disc(monkeypatch, tmp_path, capsys):
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    monkeypatch.setattr("builtins.input", lambda *a: "")
    mod.ACOUSTID_API_KEY = ""
    mod.fix_by_discid("700a8608")
    out = capsys.readouterr().out
    assert "Unknown Album (700a8608)" in out
    # No album given and no suggestion available -> refuses to guess.
    assert "No album given" in out


def test_fix_by_discid_applies_a_manual_correction(monkeypatch, tmp_path, capsys):
    pytest.importorskip("mutagen")
    from mutagen.easyid3 import EasyID3
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.ACOUSTID_API_KEY = ""
    answers = iter(["Real Artist", "Real Album"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    mod.fix_by_discid("700a8608")

    new_dir = os.path.join(mod.RIPDIR, "Real Artist", "Real Album")
    assert os.path.isdir(new_dir), os.listdir(mod.RIPDIR)
    files = sorted(os.listdir(new_dir))
    assert len(files) == 3, files
    tags = EasyID3(os.path.join(new_dir, files[0]))
    assert tags["artist"] == ["Real Artist"]
    assert tags["album"] == ["Real Album"]
    # The old Unknown folder should not be left behind alongside the fixed one.
    assert not os.path.isdir(os.path.join(mod.RIPDIR, "Unknown Artist",
                                          "Unknown Album (700a8608)"))


def test_fix_by_discid_accepts_a_suggestion_on_blank_input(monkeypatch, tmp_path, capsys):
    """#2's confirm/edit discipline: a fuzzy match is offered, never applied
    blind, and blank input is what accepts it."""
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.ACOUSTID_API_KEY = "test-key"
    monkeypatch.setattr(mod.metadata_lookup, "resolve_disc_metadata",
                        lambda *a, **k: ("Suggested Artist", "Suggested Album"))
    monkeypatch.setattr("builtins.input", lambda *a: "")
    mod.fix_by_discid("700a8608")
    out = capsys.readouterr().out
    assert "suggestion: Suggested Artist - Suggested Album" in out
    assert "unverified match" in out
    assert os.path.isdir(os.path.join(mod.RIPDIR, "Suggested Artist",
                                      "Suggested Album"))


def test_fix_by_discid_typed_input_overrides_the_suggestion(monkeypatch, tmp_path, capsys):
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.ACOUSTID_API_KEY = "test-key"
    monkeypatch.setattr(mod.metadata_lookup, "resolve_disc_metadata",
                        lambda *a, **k: ("Wrong Guess", "Wrong Album"))
    answers = iter(["Actually This", "And This"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    mod.fix_by_discid("700a8608")
    assert os.path.isdir(os.path.join(mod.RIPDIR, "Actually This", "And This"))
    assert not os.path.isdir(os.path.join(mod.RIPDIR, "Wrong Guess", "Wrong Album"))


def test_fix_by_discid_on_an_unknown_discid_says_so(monkeypatch, tmp_path, capsys):
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.fix_by_discid("deadbeef")
    assert "No ripped album found" in capsys.readouterr().out


def test_fix_by_discid_survives_a_failing_lookup(monkeypatch, tmp_path, capsys):
    """A network/fpcalc failure during the suggestion step must still leave
    manual entry usable, not abort the fix."""
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.ACOUSTID_API_KEY = "test-key"
    monkeypatch.setattr(mod.metadata_lookup, "resolve_disc_metadata",
                        lambda *a, **k: (None, None))
    answers = iter(["Hand Typed", "Hand Album"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    mod.fix_by_discid("700a8608")
    out = capsys.readouterr().out
    assert "no confident match" in out
    assert os.path.isdir(os.path.join(mod.RIPDIR, "Hand Typed", "Hand Album"))


def test_history_lists_the_rehearsed_disc(monkeypatch, tmp_path, capsys):
    pytest.importorskip("mutagen")
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.rip_session(mod.DEV)
    capsys.readouterr()
    mod.history()
    out = capsys.readouterr().out
    assert "Belong" in out
    # The rehearsal's own session log must read as simulated here too.
    assert "SIMULATED" in out
