"""Smoke tests for wiring Spinitron prioritization into bin/wtul-rip
(ROADMAP #1). Confirms the module loads and the spinitron functions it needs
are reachable - does NOT exercise rip_session() itself, which needs a real
drive/abcde.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import os
from importlib.machinery import SourceFileLoader

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "bin", "wtul-rip")


def _load_wtul_rip(monkeypatch, argv=None):
    monkeypatch.setattr("sys.argv", argv or ["wtul-rip"])
    loader = SourceFileLoader("wtul_rip_under_test", _MODPATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_spinitron_module_importable_from_wtul_rip(monkeypatch):
    mod = _load_wtul_rip(monkeypatch)
    assert hasattr(mod.spinitron, "fetch_recent_spins_public")
    assert hasattr(mod.spinitron, "reorder_queue")
    assert hasattr(mod.spinitron, "matched_track_numbers")


def test_metadata_lookup_module_importable_from_wtul_rip(monkeypatch):
    mod = _load_wtul_rip(monkeypatch)
    assert hasattr(mod.metadata_lookup, "resolve_disc_metadata")


def test_catalog_writeback_module_importable_from_wtul_rip(monkeypatch):
    mod = _load_wtul_rip(monkeypatch)
    assert hasattr(mod.catalog_writeback, "post_row")


def test_read_toc_discid_parses_well_formed_file(monkeypatch, tmp_path):
    (tmp_path / "cddbdiscid").write_text("700a8608 11 150 ...\n")
    mod = _load_wtul_rip(monkeypatch)
    assert mod.read_toc_discid(str(tmp_path)) == ("700a8608", 11)


def test_read_toc_discid_missing_file_returns_none(monkeypatch, tmp_path):
    mod = _load_wtul_rip(monkeypatch)
    assert mod.read_toc_discid(str(tmp_path)) == (None, 0)


def test_read_toc_discid_non_numeric_track_count_returns_none(monkeypatch, tmp_path):
    # A truncated/corrupted write (e.g. drive I/O hiccup) could leave a
    # non-numeric second token - this shouldn't crash rip_session with an
    # uncaught ValueError, just degrade like the missing-file case.
    (tmp_path / "cddbdiscid").write_text("700a8608 notanumber\n")
    mod = _load_wtul_rip(monkeypatch)
    assert mod.read_toc_discid(str(tmp_path)) == (None, 0)


def test_acoustid_key_env_var_picked_up(monkeypatch, tmp_path):
    # Point HOME at an empty tmp dir so this doesn't pick up the real
    # ~/.config/wtul/secrets.env (which has real secrets on the actual
    # machine) - this test wants to see only the env vars it sets itself.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ACOUSTID_API_KEY", "  test-key  ")
    monkeypatch.delenv("DISCOGS_TOKEN", raising=False)
    mod = _load_wtul_rip(monkeypatch)
    assert mod.ACOUSTID_API_KEY == "test-key"
    assert mod.DISCOGS_TOKEN == ""


def test_earcon_enabled_by_default(monkeypatch, capsys):
    monkeypatch.delenv("WTUL_EARCON", raising=False)
    mod = _load_wtul_rip(monkeypatch)
    mod.earcon()
    assert capsys.readouterr().out == "\a"


def test_earcon_disabled_via_env_var(monkeypatch, capsys):
    monkeypatch.setenv("WTUL_EARCON", "0")
    mod = _load_wtul_rip(monkeypatch)
    mod.earcon()
    assert capsys.readouterr().out == ""


def test_spin_poll_secs_defaults_and_env_override(monkeypatch):
    monkeypatch.delenv("WTUL_SPIN_POLL_SECS", raising=False)
    mod = _load_wtul_rip(monkeypatch)
    assert mod.SPIN_POLL_SECS == 60

    monkeypatch.setenv("WTUL_SPIN_POLL_SECS", "15")
    mod = _load_wtul_rip(monkeypatch)
    assert mod.SPIN_POLL_SECS == 15


def test_spin_poll_secs_falls_back_on_malformed_env_var(monkeypatch):
    monkeypatch.setenv("WTUL_SPIN_POLL_SECS", "not-a-number")
    mod = _load_wtul_rip(monkeypatch)
    assert mod.SPIN_POLL_SECS == 60


def test_check_for_new_spins_seeds_silently_on_first_call(monkeypatch, capsys):
    mod = _load_wtul_rip(monkeypatch)
    monkeypatch.setattr(
        mod.spinitron, "fetch_recent_spins_public",
        lambda: [{"artist": "Talking Heads", "song": "Once in a Lifetime"}],
    )
    keys = mod.check_for_new_spins(None)
    assert keys == {("Talking Heads", "Once in a Lifetime")}
    assert capsys.readouterr().out == ""


def test_check_for_new_spins_prints_only_newly_seen(monkeypatch, capsys):
    mod = _load_wtul_rip(monkeypatch)
    seen = {("Talking Heads", "Once in a Lifetime")}
    monkeypatch.setattr(
        mod.spinitron, "fetch_recent_spins_public",
        lambda: [
            {"artist": "Talking Heads", "song": "Once in a Lifetime"},
            {"artist": "Devo", "song": "Whip It"},
        ],
    )
    keys = mod.check_for_new_spins(seen)
    assert keys == {
        ("Talking Heads", "Once in a Lifetime"),
        ("Devo", "Whip It"),
    }
    out = capsys.readouterr().out
    assert "Devo - Whip It" in out
    assert "Talking Heads" not in out


def test_check_for_new_spins_never_raises_on_fetch_failure(monkeypatch, capsys):
    mod = _load_wtul_rip(monkeypatch)

    def boom():
        raise mod.urllib.error.URLError("no network")

    monkeypatch.setattr(mod.spinitron, "fetch_recent_spins_public", boom)
    seen = {("Devo", "Whip It")}
    keys = mod.check_for_new_spins(seen)
    assert keys is seen
    assert capsys.readouterr().out == ""

    keys = mod.check_for_new_spins(seen, quiet_errors=False)
    assert keys is seen
    assert "spin check failed" in capsys.readouterr().out


# --- discid-based rerip cache (QUESTIONS.md 2026-07-24 "fingerprint-cache
# re-rips" idea, built as a stopgap against TOC discid - already computed
# for free per rip - not a real audio fingerprint) ---

def test_find_prior_rip_returns_none_with_no_markers(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    mod = _load_wtul_rip(monkeypatch)
    assert mod.find_prior_rip("deadbeef") is None


def test_find_prior_rip_matches_marker_from_an_earlier_week(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    mod = _load_wtul_rip(monkeypatch)
    prior_dir = os.path.join(mod.MIXES_ROOT, "2026-07-10", "Some Artist", "Some Album")
    os.makedirs(prior_dir)
    mod.write_discid_marker(prior_dir, "deadbeef")
    assert mod.find_prior_rip("deadbeef") == prior_dir
    assert mod.find_prior_rip("othervalue") is None


def test_find_prior_rip_excludes_given_dir(monkeypatch, tmp_path):
    # Today's own (still-empty) album dir shouldn't ever count as its own
    # "prior" rip, even if something wrote a marker into it already.
    monkeypatch.setenv("HOME", str(tmp_path))
    mod = _load_wtul_rip(monkeypatch)
    todays_dir = os.path.join(mod.RIPDIR, "Some Artist", "Some Album")
    os.makedirs(todays_dir)
    mod.write_discid_marker(todays_dir, "deadbeef")
    assert mod.find_prior_rip("deadbeef", exclude_dir=todays_dir) is None


def test_find_prior_rip_prefers_most_recently_modified(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    mod = _load_wtul_rip(monkeypatch)
    older = os.path.join(mod.MIXES_ROOT, "2026-06-01", "A", "B")
    newer = os.path.join(mod.MIXES_ROOT, "2026-07-01", "A", "B")
    os.makedirs(older)
    os.makedirs(newer)
    mod.write_discid_marker(older, "deadbeef")
    older_marker = os.path.join(older, ".discid")
    os.utime(older_marker, (1000, 1000))
    mod.write_discid_marker(newer, "deadbeef")
    newer_marker = os.path.join(newer, ".discid")
    os.utime(newer_marker, (2000, 2000))
    assert mod.find_prior_rip("deadbeef") == newer


def test_symlink_prior_rip_links_mp3s_and_skips_existing(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    mod = _load_wtul_rip(monkeypatch)
    prior_dir = os.path.join(mod.MIXES_ROOT, "2026-07-10", "A", "B")
    os.makedirs(prior_dir)
    with open(os.path.join(prior_dir, "01-Song.mp3"), "w") as f:
        f.write("fake mp3 data")
    with open(os.path.join(prior_dir, "notes.txt"), "w") as f:
        f.write("not a track")

    album_dir = os.path.join(mod.RIPDIR, "A", "B")
    os.makedirs(album_dir)
    with open(os.path.join(album_dir, "02-AlreadyHere.mp3"), "w") as f:
        f.write("already ripped separately")

    linked = mod.symlink_prior_rip(prior_dir, album_dir)
    assert linked == 1
    assert os.path.islink(os.path.join(album_dir, "01-Song.mp3"))
    assert not os.path.exists(os.path.join(album_dir, "notes.txt"))
    # A track that already existed in album_dir isn't touched/relinked.
    assert not os.path.islink(os.path.join(album_dir, "02-AlreadyHere.mp3"))


def test_write_discid_marker_is_silent_on_missing_dir(monkeypatch, tmp_path):
    # album_dir not existing shouldn't raise - a completed rip always makes
    # its own dir first, but this stays defensive rather than assuming.
    monkeypatch.setenv("HOME", str(tmp_path))
    mod = _load_wtul_rip(monkeypatch)
    missing_dir = os.path.join(mod.MIXES_ROOT, "2026-07-10", "Nope", "Nope")
    mod.write_discid_marker(missing_dir, "deadbeef")  # must not raise


def test_photo_capture_module_importable_from_wtul_rip(monkeypatch):
    mod = _load_wtul_rip(monkeypatch)
    assert hasattr(mod.photo_capture, "new_pairing_code")
    assert hasattr(mod.photo_capture, "check_photo")


def test_ocr_metadata_module_importable_from_wtul_rip(monkeypatch):
    mod = _load_wtul_rip(monkeypatch)
    assert hasattr(mod.ocr_metadata, "ocr_cover_candidates")
    assert hasattr(mod.ocr_metadata, "find_cover_image")


def test_photo_capture_url_env_var_picked_up(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PHOTO_CAPTURE_URL", "  https://example.com/exec  ")
    mod = _load_wtul_rip(monkeypatch)
    assert mod.PHOTO_CAPTURE_URL == "https://example.com/exec"


def test_pending_photos_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    mod = _load_wtul_rip(monkeypatch)
    assert mod._load_pending_photos() == []
    mod._record_pending_photo("abc123", "disc-1", "/tmp/album", ["/tmp/album/1.mp3"],
                               "Artist", "Album")
    pending = mod._load_pending_photos()
    assert len(pending) == 1
    assert pending[0]["pairing_code"] == "abc123"
    assert pending[0]["disc_id"] == "disc-1"
