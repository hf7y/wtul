"""Unit tests for lib/fake_drive.py - the simulated optical drive.

These test the simulator itself (spec validation, the output shapes it
claims to imitate, sandbox containment). The end-to-end "does rip_session()
actually work" rehearsal lives in tests/test_rip_rehearsal.py.

Run with:  python3 -m pytest tests/ -q
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import fake_drive


def _spec(**over):
    base = {
        "discid": "700a8608",
        "artist": "Belong",
        "album": "October Language",
        "tracks": [{"title": "I Never Lose", "length": "3:00"},
                   {"title": "Late Night", "length": "2:30"}],
    }
    base.update(over)
    return base


def _drive(tmp_path, spec=None, **over):
    parsed = _parse(spec or _spec(**over))
    ripdir = str(tmp_path / "2026-07-25")

    def album_dir_fn(artist, album, discid):
        album = album.strip() or "Unknown Album"
        if album == "Unknown Album":
            album = f"Unknown Album ({discid})"
        return os.path.join(ripdir, artist.strip() or "Unknown Artist", album)

    return fake_drive.FakeDrive(parsed, ripdir, album_dir_fn), ripdir


def _parse(spec_dict, tmp=None):
    """Round-trip a raw dict through load_spec()'s validation via a file."""
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(spec_dict, f)
    try:
        return fake_drive.load_spec(path)
    finally:
        os.unlink(path)


# -- spec loading / validation ------------------------------------------


def test_demo_spec_loads_without_a_file():
    spec = fake_drive.load_spec("demo")
    assert spec["tracks"]
    assert len(spec["discid"]) == 8


def test_demo_spec_is_not_mutated_by_loading():
    a = fake_drive.load_spec("demo")
    a["tracks"].append({"num": 99})
    b = fake_drive.load_spec("demo")
    assert len(b["tracks"]) == len(fake_drive.DEMO_SPEC["tracks"])


def test_empty_env_value_is_an_error():
    with pytest.raises(fake_drive.SpecError):
        fake_drive.load_spec("   ")


def test_missing_file_is_an_error_not_a_silent_fallback():
    with pytest.raises(fake_drive.SpecError):
        fake_drive.load_spec("/nonexistent/disc.json")


def test_malformed_json_is_an_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    with pytest.raises(fake_drive.SpecError):
        fake_drive.load_spec(str(p))


def test_json_that_is_a_list_not_an_object_is_an_error(tmp_path):
    p = tmp_path / "list.json"
    p.write_text('["a", "b"]')
    with pytest.raises(fake_drive.SpecError):
        fake_drive.load_spec(str(p))


def test_no_tracks_is_an_error():
    with pytest.raises(fake_drive.SpecError):
        _parse(_spec(tracks=[]))


def test_bad_discid_is_an_error():
    with pytest.raises(fake_drive.SpecError):
        _parse(_spec(discid="nope"))


def test_bad_track_length_is_an_error():
    with pytest.raises(fake_drive.SpecError):
        _parse(_spec(tracks=[{"title": "x", "length": "banana"}]))


def test_track_can_be_a_bare_title_string():
    spec = _parse(_spec(tracks=["Just A Title"]))
    assert spec["tracks"][0]["title"] == "Just A Title"


def test_blank_track_title_falls_back_to_track_n():
    spec = _parse(_spec(tracks=[{"title": "   "}]))
    assert spec["tracks"][0]["title"] == "Track 1"


# -- command dispatch ---------------------------------------------------


def test_handles_the_four_hardware_commands(tmp_path):
    d, _ = _drive(tmp_path)
    assert d.handles(["udevadm", "info", "--query=property", "--name=/dev/sr0"])
    assert d.handles(["cdparanoia", "-Q", "-d", "/dev/sr0"])
    assert d.handles(["abcde", "-N", "-d", "/dev/sr0", "-a", "cddb"])
    assert d.handles(["eject", "/dev/sr0"])


def test_does_not_handle_unrelated_commands(tmp_path):
    d, _ = _drive(tmp_path)
    assert not d.handles(["fpcalc", "track.mp3"])
    assert not d.handles(["curl", "https://api.discogs.com/"])
    assert not d.handles([])


def test_sees_through_the_timeout_wrapper(tmp_path):
    """rip_track() wraps abcde in `timeout --signal=TERM --kill-after=30s 900`;
    if the simulator didn't strip that it would decline every real rip."""
    d, _ = _drive(tmp_path)
    cmd = ["timeout", "--signal=TERM", "--kill-after=30s", "900",
           "abcde", "-N", "-d", "/dev/sr0", "-C", "700a8608",
           "-a", "read,encode,tag,move", "1"]
    assert d.handles(cmd)


def test_running_an_unhandled_command_raises_rather_than_no_ops(tmp_path):
    d, _ = _drive(tmp_path)
    with pytest.raises(fake_drive.SpecError):
        d.run(["fpcalc", "x.mp3"])


# -- udev ---------------------------------------------------------------


def test_udev_reports_disc_present_with_track_count(tmp_path):
    d, _ = _drive(tmp_path)
    rc, out = d.run(["udevadm", "info", "--query=property", "--name=/dev/sr0"])
    assert rc == 0
    assert "ID_CDROM_MEDIA=1" in out
    assert "ID_CDROM_MEDIA_TRACK_COUNT_AUDIO=2" in out


def test_udev_can_report_an_empty_drive(tmp_path):
    d, _ = _drive(tmp_path, disc_present=False)
    _, out = d.run(["udevadm", "info", "--query=property", "--name=/dev/sr0"])
    assert "ID_CDROM_MEDIA=0" in out
    assert "ID_CDROM_MEDIA_TRACK_COUNT_AUDIO=0" in out


def test_udev_output_is_marked_simulated(tmp_path):
    d, _ = _drive(tmp_path)
    _, out = d.run(["udevadm", "info", "--name=/dev/sr0"])
    assert "WTUL_SIMULATED=1" in out


# -- cdparanoia -Q ------------------------------------------------------


def test_toc_output_parses_with_the_real_track_durations_regex(tmp_path):
    """The point of the TOC fixture is that wtul-rip's own regex matches it -
    asserting on our own format would prove nothing."""
    import re
    d, _ = _drive(tmp_path)
    _, out = d.run(["cdparanoia", "-Q", "-d", "/dev/sr0"])
    durations = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\d+)\.\s+\d+\s+\[(\d+:\d+\.\d+)\]", line)
        if m:
            durations[int(m.group(1))] = m.group(2).rsplit(".", 1)[0]
    assert durations == {1: "03:00", 2: "02:30"}


# -- abcde -a cddb ------------------------------------------------------


def test_scrape_writes_a_cddbdiscid_readable_by_read_toc_discid(tmp_path):
    d, _ = _drive(tmp_path)
    d.run(["abcde", "-N", "-d", "/dev/sr0", "-a", "cddb"])
    parts = open(os.path.join(d.tempdir, "cddbdiscid")).read().split()
    assert parts[0] == "700a8608"
    assert int(parts[1]) == 2


def test_scrape_writes_cddbread_with_dtitle_and_ttitles(tmp_path):
    d, _ = _drive(tmp_path)
    d.run(["abcde", "-N", "-d", "/dev/sr0", "-a", "cddb"])
    body = open(os.path.join(d.tempdir, "cddbread.1")).read()
    assert "DTITLE=Belong / October Language" in body
    assert "TTITLE0=I Never Lose" in body
    assert "TTITLE1=Late Night" in body


def test_unmatched_disc_writes_discid_but_no_cddbread(tmp_path):
    """An unmatched disc still gets a TOC discid from cd-discid - that
    asymmetry is exactly why read_toc_discid() exists, so the simulator has
    to reproduce it rather than writing both files or neither."""
    d, _ = _drive(tmp_path, match=False)
    d.run(["abcde", "-N", "-d", "/dev/sr0", "-a", "cddb"])
    assert os.path.exists(os.path.join(d.tempdir, "cddbdiscid"))
    assert not os.path.exists(os.path.join(d.tempdir, "cddbread.1"))


def test_scrape_tempdir_is_named_like_abcdes(tmp_path):
    """newest_abcde_tempdir() globs RIPDIR/abcde.* - a differently-named dir
    would be invisible to it."""
    d, ripdir = _drive(tmp_path)
    d.run(["abcde", "-N", "-d", "/dev/sr0", "-a", "cddb"])
    assert os.path.basename(d.tempdir).startswith("abcde.")
    assert os.path.dirname(d.tempdir) == ripdir


# -- abcde -a read,encode,tag,move --------------------------------------


def _rip_cmd(n, discid="700a8608"):
    return ["timeout", "--signal=TERM", "--kill-after=30s", "900",
            "abcde", "-N", "-d", "/dev/sr0", "-C", discid,
            "-a", "read,encode,tag,move", str(n)]


def test_rip_writes_a_file_matching_find_track_file(tmp_path):
    import re
    d, ripdir = _drive(tmp_path)
    rc, out = d.run(_rip_cmd(1))
    assert rc == 0
    album_dir = os.path.join(ripdir, "Belong", "October Language")
    names = os.listdir(album_dir)
    # find_track_file()'s own pattern
    assert any(re.match(r"^0*1-.*\.mp3$", n, re.IGNORECASE) for n in names), names


def test_ripped_file_is_a_parseable_mp3_with_tags(tmp_path):
    """retag_mp3()/history() read these back with mutagen; a zero-byte stub
    would make a rehearsal fail on its own placeholder."""
    pytest.importorskip("mutagen")
    from mutagen.mp3 import MP3
    from mutagen.easyid3 import EasyID3
    d, ripdir = _drive(tmp_path)
    d.run(_rip_cmd(2))
    path = os.path.join(ripdir, "Belong", "October Language", "02-Late Night.mp3")
    assert MP3(path).info.length > 0
    tags = EasyID3(path)
    assert tags["artist"] == ["Belong"]
    assert tags["title"] == ["Late Night"]
    assert tags["tracknumber"] == ["2"]


def test_rip_emits_a_read_speed_line(tmp_path):
    d, _ = _drive(tmp_path, read_speed="7.5")
    _, out = d.run(_rip_cmd(1))
    assert "7.5x" in out


def test_failing_track_returns_nonzero_and_an_error_line(tmp_path):
    """sh_live() flags a track bad on an [ERROR] substring even at rc 0, so
    both signals have to be present for the retry path to be rehearsed."""
    d, _ = _drive(tmp_path, tracks=[{"title": "Scratched", "length": "3:00",
                                      "fails": True}])
    rc, out = d.run(_rip_cmd(1))
    assert rc != 0
    assert "[ERROR]" in out


def test_rip_of_a_track_not_on_the_disc_fails_loudly(tmp_path):
    d, _ = _drive(tmp_path)
    rc, out = d.run(_rip_cmd(99))
    assert rc != 0
    assert "[ERROR]" in out


def test_unmatched_disc_rips_into_the_unknown_album_discid_folder(tmp_path):
    d, ripdir = _drive(tmp_path, match=False)
    d.run(_rip_cmd(1))
    assert os.path.isdir(os.path.join(ripdir, "Unknown Artist",
                                      "Unknown Album (700a8608)"))


def test_track_title_with_shell_hostile_characters_is_munged(tmp_path):
    """abcde.conf's mungefilename maps ':' to '-' and strips quotes/'?'."""
    d, ripdir = _drive(tmp_path,
                       tracks=[{"title": 'Who? "Me": Yes', "length": "1:00"}])
    d.run(_rip_cmd(1))
    names = os.listdir(os.path.join(ripdir, "Belong", "October Language"))
    assert names == ["01-Who Me- Yes.mp3"], names


# -- eject / sandbox ----------------------------------------------------


def test_eject_is_recorded_and_never_touches_a_device(tmp_path):
    d, _ = _drive(tmp_path)
    rc, _ = d.run(["eject", "/dev/sr0"])
    assert rc == 0 and d.ejected is True


def test_sandbox_root_is_not_the_real_music_library(monkeypatch):
    monkeypatch.delenv(fake_drive.ENV_ROOT, raising=False)
    root = fake_drive.sandbox_root()
    assert os.path.join("Music", "mixes") not in root
    assert "rehearsal" in root


def test_sandbox_root_honours_the_override(monkeypatch, tmp_path):
    monkeypatch.setenv(fake_drive.ENV_ROOT, str(tmp_path))
    assert fake_drive.sandbox_root() == str(tmp_path)


def test_from_env_returns_none_when_not_simulating(monkeypatch, tmp_path):
    monkeypatch.delenv(fake_drive.ENV_SPEC, raising=False)
    assert fake_drive.from_env(str(tmp_path), lambda *a: str(tmp_path)) is None


def test_from_env_builds_a_drive_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv(fake_drive.ENV_SPEC, "demo")
    d = fake_drive.from_env(str(tmp_path), lambda *a: str(tmp_path))
    assert isinstance(d, fake_drive.FakeDrive)


def test_banner_says_rehearsal_and_not_verification(tmp_path):
    d, _ = _drive(tmp_path)
    banner = d.banner()
    assert "REHEARSAL" in banner
    assert "does NOT count as hardware verification" in banner


# -- edge cases / malformed input (stress pass, 2026-07-25) --------------


def test_tracks_as_a_dict_instead_of_a_list_is_an_error():
    with pytest.raises(fake_drive.SpecError):
        _parse(_spec(tracks={"1": "a"}))


def test_null_track_entry_is_an_error():
    with pytest.raises(fake_drive.SpecError):
        _parse(_spec(tracks=[None]))


def test_numeric_track_entry_is_an_error():
    with pytest.raises(fake_drive.SpecError):
        _parse(_spec(tracks=[42]))


def test_missing_tracks_key_entirely_is_an_error():
    spec = _spec()
    del spec["tracks"]
    with pytest.raises(fake_drive.SpecError):
        _parse(spec)


def test_seconds_over_59_in_a_length_is_an_error():
    with pytest.raises(fake_drive.SpecError):
        _parse(_spec(tracks=[{"title": "x", "length": "3:75"}]))


def test_negative_length_is_an_error():
    with pytest.raises(fake_drive.SpecError):
        _parse(_spec(tracks=[{"title": "x", "length": "-1:00"}]))


def test_length_may_carry_a_frames_component():
    """cdparanoia prints MM:SS.FF; accepting that shape means a spec can be
    pasted straight from a real TOC dump."""
    spec = _parse(_spec(tracks=[{"title": "x", "length": "3:55.20"}]))
    assert spec["tracks"][0]["seconds"] == 235


def test_uppercase_discid_is_accepted_and_normalised():
    """abcde/cd-discid emit lowercase hex; a hand-written spec may not, and
    the discid ends up in a folder name, so it has to be one or the other."""
    assert _parse(_spec(discid="700A8608"))["discid"] == "700a8608"


def test_discid_of_wrong_length_is_an_error():
    with pytest.raises(fake_drive.SpecError):
        _parse(_spec(discid="700a860"))


def test_zero_length_track_still_produces_a_valid_mp3(tmp_path):
    pytest.importorskip("mutagen")
    from mutagen.mp3 import MP3
    d, ripdir = _drive(tmp_path, tracks=[{"title": "Silence", "length": "0:00"}])
    assert d.run(_rip_cmd(1))[0] == 0
    path = os.path.join(ripdir, "Belong", "October Language", "01-Silence.mp3")
    assert MP3(path).info.length > 0


def test_long_track_does_not_produce_an_enormous_file(tmp_path):
    """A rehearsal shouldn't write a real-size file per track - the tag and
    length plumbing is identical either way."""
    d, ripdir = _drive(tmp_path, tracks=[{"title": "Epic", "length": "45:00"}])
    d.run(_rip_cmd(1))
    path = os.path.join(ripdir, "Belong", "October Language", "01-Epic.mp3")
    assert os.path.getsize(path) < 100_000


def test_unicode_track_title_round_trips(tmp_path):
    pytest.importorskip("mutagen")
    from mutagen.easyid3 import EasyID3
    title = "Björk – Jóga (ﬂ)"
    d, ripdir = _drive(tmp_path, tracks=[{"title": title, "length": "2:00"}])
    assert d.run(_rip_cmd(1))[0] == 0
    album_dir = os.path.join(ripdir, "Belong", "October Language")
    path = os.path.join(album_dir, os.listdir(album_dir)[0])
    assert EasyID3(path)["title"] == [title]


def test_a_99_track_disc_scrapes_and_tocs_consistently(tmp_path):
    """CD-DA's real ceiling is 99 tracks; the TOC and cddbread have to agree
    on the count or the tracklist and the rip queue disagree."""
    tracks = [{"title": f"T{i}", "length": "0:30"} for i in range(1, 100)]
    d, _ = _drive(tmp_path, tracks=tracks)
    d.run(["abcde", "-N", "-d", "/dev/sr0", "-a", "cddb"])
    parts = open(os.path.join(d.tempdir, "cddbdiscid")).read().split()
    assert int(parts[1]) == 99
    body = open(os.path.join(d.tempdir, "cddbread.1")).read()
    assert "TTITLE98=T99" in body
    _, toc = d.run(["cdparanoia", "-Q", "-d", "/dev/sr0"])
    assert " 99. " in toc


def test_two_scrapes_get_distinct_tempdirs(tmp_path):
    """newest_abcde_tempdir() picks by mtime; reusing one dir would let a
    second disc silently inherit the first's cddbread."""
    d, _ = _drive(tmp_path)
    d.run(["abcde", "-N", "-d", "/dev/sr0", "-a", "cddb"])
    first = d.tempdir
    d.run(["abcde", "-N", "-d", "/dev/sr0", "-a", "cddb"])
    assert d.tempdir != first


def test_track_title_that_is_only_hostile_characters_still_yields_a_filename(tmp_path):
    """mungefilename could strip a title down to nothing; the result still
    has to match find_track_file's ^0*N- pattern."""
    import re
    d, ripdir = _drive(tmp_path, tracks=[{"title": '"?', "length": "1:00"}])
    assert d.run(_rip_cmd(1))[0] == 0
    names = os.listdir(os.path.join(ripdir, "Belong", "October Language"))
    assert any(re.match(r"^0*1-.*\.mp3$", n) for n in names), names


def test_blank_album_is_treated_as_unknown(tmp_path):
    d, ripdir = _drive(tmp_path, album="   ")
    d.run(_rip_cmd(1))
    assert os.path.isdir(os.path.join(ripdir, "Belong",
                                      "Unknown Album (700a8608)"))


def test_streaming_a_non_rip_command_still_works(tmp_path):
    """stream() is only ever called with a rip today; doing nothing useful on
    another command would be a silent trap for a future caller."""
    d, _ = _drive(tmp_path)
    rc, lines = d.stream(["cdparanoia", "-Q", "-d", "/dev/sr0"])
    assert rc == 0 and any("[" in l for l in lines)


def test_streaming_an_unhandled_command_raises(tmp_path):
    d, _ = _drive(tmp_path)
    with pytest.raises(fake_drive.SpecError):
        d.stream(["fpcalc", "x.mp3"])


def test_timeout_wrapper_with_no_inner_command_is_not_claimed(tmp_path):
    d, _ = _drive(tmp_path)
    assert not d.handles(["timeout", "900"])
