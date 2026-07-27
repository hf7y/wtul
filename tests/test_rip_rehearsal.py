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
import time
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
    # ".discid" is the re-rip cache's marker (find_prior_rip), written on
    # every completed disc since discid-rerip-cache merged.
    assert sorted(os.listdir(album_dir)) == [
        ".discid",
        "01-I Never Lose.mp3", "02-Late Night.mp3", "03-Remove the Inside.mp3"]
    with open(os.path.join(album_dir, ".discid")) as f:
        assert f.read().strip() == SPEC["discid"]


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


def test_prior_week_rip_is_symlinked_instead_of_reripped(monkeypatch, tmp_path, capsys):
    """End-to-end rehearsal of the discid re-rip cache at its integration
    point inside rip_session() - until now only its leaf functions
    (find_prior_rip / symlink_prior_rip / write_discid_marker) had tests,
    each alone, which is exactly the tested-apart-broken-together gap this
    suite exists to close. A disc completed on an earlier show night must be
    recognized by TOC discid and symlinked, not ripped again."""
    spec_path = _write_spec(tmp_path)
    mod = _load_rehearsal(monkeypatch, tmp_path, spec_path)
    assert mod.rip_session(mod.DEV) is True
    capsys.readouterr()

    # Re-file today's completed rip as if it had happened on an earlier
    # show night: today's dated dir is left empty, so only the .discid
    # marker in the prior week's dir can connect the two.
    prior_day = os.path.join(mod.MIXES_ROOT, "2026-07-10")
    os.makedirs(prior_day)
    os.rename(os.path.join(mod.RIPDIR, "Belong"),
              os.path.join(prior_day, "Belong"))

    mod2 = _load_rehearsal(monkeypatch, tmp_path, spec_path)
    assert mod2.rip_session(mod2.DEV) is True
    out = capsys.readouterr().out
    assert "Disc already ripped on 2026-07-10" in out
    assert "symlinked 3 track(s) instead of re-ripping" in out
    assert "All tracks already ripped" in out
    assert mod2.SIM.ripped == [], "the cache hit must prevent any re-rip"

    today_dir = os.path.join(mod2.RIPDIR, "Belong", "October Language")
    prior_dir = os.path.join(prior_day, "Belong", "October Language")
    for name in ("01-I Never Lose.mp3", "02-Late Night.mp3",
                 "03-Remove the Inside.mp3"):
        link = os.path.join(today_dir, name)
        assert os.path.islink(link)
        assert os.readlink(link) == os.path.join(prior_dir, name)
    # Today's dir gets its own marker too, so next week's cache lookup can
    # hit either copy.
    with open(os.path.join(today_dir, ".discid")) as f:
        assert f.read().strip() == SPEC["discid"]


def test_read_speed_line_reaches_the_log(monkeypatch, tmp_path):
    """#6's rip-speed monitoring parses these lines out of the session log;
    a rehearsal is the only way to produce one without a disc."""
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.rip_session(mod.DEV)
    logs = os.listdir(mod.LOGDIR)
    body = open(os.path.join(mod.LOGDIR, logs[0])).read()
    assert "4.2x" in body


def test_live_read_speed_print_fires_under_rehearsal(monkeypatch, tmp_path, capsys):
    """#6's live per-track "(read speed N.Nx)" print previously only ever ran
    with a real disc. FakeDrive emits the speed sample in cdparanoia's real
    |N.Nx| status format (what SPEED_RE actually matches), so the print - not
    just the log line - rehearses without a drive."""
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.rip_session(mod.DEV)
    assert "(read speed 4.2x)" in capsys.readouterr().out


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
    assert sorted(os.listdir(where)) == [".discid",
                                         "01-I Never Lose.mp3", "02-Late Night.mp3",
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


def test_rehearsal_never_prints_a_real_label(monkeypatch, tmp_path, capsys):
    """Same containment class as the catalog leak above, arrived 2026-07-25
    when label printing (#3) merged to main: print_label() shells out to the
    real catprint/BLE printer, so a complete rehearsal disc would physically
    print a junk label - wasting the label tape whose scarcity is already a
    live complaint. Rendering is left in (pure PIL); only the print is gated."""
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    calls = []
    monkeypatch.setattr(mod.label_render, "print_label",
                        lambda *a, **k: calls.append(a) or (True, None))
    assert mod.rip_session(mod.DEV) is True
    assert calls == [], "a rehearsal must never invoke the real label printer"
    assert "Label: print SUPPRESSED" in capsys.readouterr().out


def test_rehearsal_never_pairs_photo_capture(monkeypatch, tmp_path, capsys):
    """Third member of the same containment class (catalog row 2026-07-25,
    label print 2026-07-25): with PHOTO_CAPTURE_URL set in the real
    secrets.env, a complete rehearsal disc would print a pairing URL against
    the real GAS endpoint and invite a phone upload keyed to a discid that
    doesn't exist. Pairing is gated; nothing else about the rip changes."""
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.PHOTO_CAPTURE_URL = "https://example.com/exec"
    calls = []
    monkeypatch.setattr(mod.photo_capture, "new_pairing_code",
                        lambda *a, **k: calls.append(a) or "zzz999")
    assert mod.rip_session(mod.DEV) is True
    out = capsys.readouterr().out
    assert calls == [], "a rehearsal must never issue a real pairing code"
    assert "Photo capture: pairing SUPPRESSED" in out
    assert "open https://" not in out


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


# -- the sheet's DJ NAME / DATE columns (QUESTIONS.md reply, 2026-07-27) --
#
# "Updates should include under DJ NAME 'Guy' (my dj name) and DATE can be
# the date entered." DATE was already the entry date; DJ NAME was missing
# entirely, so every row #8 has ever written landed unattributed.


def _rehearse_catalog_row(monkeypatch, tmp_path, dj_name=None):
    """Run one complete rehearsed disc with the catalog write-back opted in
    and `write_row` injected, and return the row it would have POSTed.

    WTUL_DJ_NAME is read at module load, so it is set (or explicitly
    cleared) here, before exec_module - and always one of the two, so a
    real WTUL_DJ_NAME in the runner's own environment can never decide
    what these tests assert.
    """
    if dj_name is None:
        monkeypatch.delenv("WTUL_DJ_NAME", raising=False)
    else:
        monkeypatch.setenv("WTUL_DJ_NAME", dj_name)
    monkeypatch.setenv("WTUL_SIMULATE_ALLOW_CATALOG", "1")
    mod = _load_rehearsal(monkeypatch, tmp_path, _write_spec(tmp_path))
    mod.CATALOG_WRITEBACK_URL = "https://example.invalid/exec"
    calls = []
    monkeypatch.setattr(mod.catalog_writeback, "write_row",
                        lambda url, row: calls.append(row) or True)
    assert mod.rip_session(mod.DEV) is True
    assert len(calls) == 1
    return calls[0]


def test_catalog_row_carries_the_dj_name(monkeypatch, tmp_path):
    row = _rehearse_catalog_row(monkeypatch, tmp_path)
    # The key must read exactly as the sheet's header does: the GAS endpoint
    # matches keys to headers case-insensitively but does not collapse the
    # internal space, so "DJNAME"/"DJ_NAME" would be silently ignored.
    assert row["DJ NAME"] == "Guy"


def test_catalog_row_dj_name_is_overridable(monkeypatch, tmp_path):
    row = _rehearse_catalog_row(monkeypatch, tmp_path, dj_name="Someone Else")
    assert row["DJ NAME"] == "Someone Else"


def test_catalog_row_omits_dj_name_when_blanked(monkeypatch, tmp_path):
    """An explicitly empty WTUL_DJ_NAME writes no DJ NAME rather than
    falling back to the default - otherwise a second DJ could only opt out
    by attributing their rips to Guy."""
    row = _rehearse_catalog_row(monkeypatch, tmp_path, dj_name="   ")
    assert "DJ NAME" not in row


def test_catalog_row_date_is_the_date_entered(monkeypatch, tmp_path):
    row = _rehearse_catalog_row(monkeypatch, tmp_path)
    assert row["DATE"] == time.strftime("%Y-%m-%d")


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
    mp3s = sorted(f for f in os.listdir(new_dir) if f.endswith(".mp3"))
    assert len(mp3s) == 3, mp3s
    tags = EasyID3(os.path.join(new_dir, mp3s[0]))
    assert tags["artist"] == ["Real Artist"]
    assert tags["album"] == ["Real Album"]
    # The re-rip cache marker must follow the music: a marker left in the
    # old Unknown dir would make find_prior_rip() match a dir with no mp3s
    # in it on the next insert of this disc.
    with open(os.path.join(new_dir, ".discid")) as f:
        assert f.read().strip() == "700a8608"
    # The old Unknown folder should not be left behind alongside the fixed
    # one - and its parent shouldn't either once emptied.
    assert not os.path.isdir(os.path.join(mod.RIPDIR, "Unknown Artist",
                                          "Unknown Album (700a8608)"))
    assert not os.path.isdir(os.path.join(mod.RIPDIR, "Unknown Artist"))


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


def test_fix_by_discid_musicbrainz_search_pick_becomes_the_suggestion(
        monkeypatch, tmp_path, capsys):
    """'? <text>' at the artist prompt (the third fallback, ROADMAP #2) runs
    a MusicBrainz search; picking a row re-offers it as the suggestion, and
    blank input at both prompts is what accepts it - confirm/edit, same as
    every other suggestion source."""
    pytest.importorskip("mutagen")
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.ACOUSTID_API_KEY = ""
    monkeypatch.setattr(mod.metadata_lookup, "musicbrainz_search_release",
                        lambda q, **k: [{"artist": "Real Band",
                                         "album": "Real Record",
                                         "year": "1997", "score": 100}])
    answers = iter(["? real band record",  # artist prompt -> search
                    "1",                   # pick the first result
                    "",                    # artist prompt again -> accept
                    ""])                   # album prompt -> accept
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    mod.fix_by_discid("700a8608")
    out = capsys.readouterr().out
    assert "Real Band - Real Record (1997)" in out
    assert "suggestion now: Real Band - Real Record" in out
    assert os.path.isdir(os.path.join(mod.RIPDIR, "Real Band", "Real Record"))


def test_fix_by_discid_musicbrainz_no_match_falls_back_to_manual(
        monkeypatch, tmp_path, capsys):
    pytest.importorskip("mutagen")
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.ACOUSTID_API_KEY = ""
    monkeypatch.setattr(mod.metadata_lookup, "musicbrainz_search_release",
                        lambda q, **k: [])
    answers = iter(["? gibberish nobody knows",  # search finds nothing
                    "Manual Artist", "Manual Album"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    mod.fix_by_discid("700a8608")
    out = capsys.readouterr().out
    assert "No MusicBrainz match" in out
    assert os.path.isdir(os.path.join(mod.RIPDIR, "Manual Artist", "Manual Album"))


def test_fix_by_discid_musicbrainz_skipped_pick_changes_nothing(
        monkeypatch, tmp_path, capsys):
    """Blank at the pick prompt declines the search results; a bare '?'
    prints usage. Neither plants a suggestion, so the eventual blank artist
    input still refuses to guess."""
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.ACOUSTID_API_KEY = ""
    monkeypatch.setattr(mod.metadata_lookup, "musicbrainz_search_release",
                        lambda q, **k: [{"artist": "Tempting",
                                         "album": "But Wrong",
                                         "year": None, "score": 90}])
    answers = iter(["?",             # bare '?' -> usage text
                    "? tempting",    # search...
                    "",              # ...but decline the pick
                    "",              # artist prompt -> no suggestion to accept
                    ""])             # album prompt -> blank
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    mod.fix_by_discid("700a8608")
    out = capsys.readouterr().out
    assert "usage: ? <search text>" in out
    assert "No album given" in out
    assert not os.path.isdir(os.path.join(mod.RIPDIR, "Tempting", "But Wrong"))


def _answers_then_eof(*answers):
    """input() stand-in: yields the given answers, then raises EOFError -
    what a real closed/Ctrl+D stdin does."""
    it = iter(answers)

    def fake(*a):
        try:
            return next(it)
        except StopIteration:
            raise EOFError
    return fake


def test_fix_by_discid_eof_at_artist_prompt_cancels_cleanly(
        monkeypatch, tmp_path, capsys):
    """Ctrl+D at the artist prompt must cancel the fix - not accept the
    suggestion, and not escape as an EOFError that kills the watch loop
    (the same class run 18 guarded on the partial-disc retry prompt)."""
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.ACOUSTID_API_KEY = "test-key"
    monkeypatch.setattr(mod.metadata_lookup, "resolve_disc_metadata",
                        lambda *a, **k: ("Suggested Artist", "Suggested Album"))
    monkeypatch.setattr("builtins.input", _answers_then_eof())
    mod.fix_by_discid("700a8608")  # must not raise
    out = capsys.readouterr().out
    assert "fix cancelled, nothing moved" in out
    assert not os.path.isdir(os.path.join(mod.RIPDIR, "Suggested Artist"))
    assert os.path.isdir(os.path.join(mod.RIPDIR, "Unknown Artist",
                                      "Unknown Album (700a8608)"))


def test_fix_by_discid_eof_at_album_prompt_cancels_cleanly(
        monkeypatch, tmp_path, capsys):
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.ACOUSTID_API_KEY = ""
    monkeypatch.setattr("builtins.input", _answers_then_eof("Real Artist"))
    mod.fix_by_discid("700a8608")  # must not raise
    out = capsys.readouterr().out
    assert "fix cancelled, nothing moved" in out
    assert not os.path.isdir(os.path.join(mod.RIPDIR, "Real Artist"))
    assert os.path.isdir(os.path.join(mod.RIPDIR, "Unknown Artist",
                                      "Unknown Album (700a8608)"))


def test_fix_by_discid_eof_at_the_search_pick_skips_only_that_step(
        monkeypatch, tmp_path, capsys):
    """A single Ctrl+D at the pick prompt (a terminal sends exactly one EOF)
    declines the results; manual entry afterward still works."""
    pytest.importorskip("mutagen")
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    capsys.readouterr()
    mod.ACOUSTID_API_KEY = ""
    monkeypatch.setattr(mod.metadata_lookup, "musicbrainz_search_release",
                        lambda q, **k: [{"artist": "Tempting",
                                         "album": "But Wrong",
                                         "year": None, "score": 90}])
    answers = iter(["? tempting", EOFError, "Manual Artist", "Manual Album"])

    def fake(*a):
        nxt = next(answers)
        if nxt is EOFError:
            raise EOFError
        return nxt
    monkeypatch.setattr("builtins.input", fake)
    mod.fix_by_discid("700a8608")
    out = capsys.readouterr().out
    assert "skipping the search results" in out
    assert os.path.isdir(os.path.join(mod.RIPDIR, "Manual Artist",
                                      "Manual Album"))
    assert not os.path.isdir(os.path.join(mod.RIPDIR, "Tempting"))


def test_fix_by_discid_glob_metachars_match_nothing(
        monkeypatch, tmp_path, capsys):
    """'fix *' must not glob onto some correctly-named album ("... (Deluxe
    Edition)") and offer to move/retag the wrong folder - a typed discid is
    matched literally."""
    mod = _rehearse_unidentified(monkeypatch, tmp_path)
    deluxe = os.path.join(mod.RIPDIR, "Some Artist", "Album (Deluxe Edition)")
    os.makedirs(deluxe)
    capsys.readouterr()
    monkeypatch.setattr("builtins.input", _answers_then_eof())
    mod.fix_by_discid("*")
    out = capsys.readouterr().out
    assert "No ripped album found" in out
    assert os.path.isdir(deluxe)
    assert os.path.isdir(os.path.join(mod.RIPDIR, "Unknown Artist",
                                      "Unknown Album (700a8608)"))
