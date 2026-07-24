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
