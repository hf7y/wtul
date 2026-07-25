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
