"""Smoke tests for wiring Spinitron prioritization into bin/wtul-rip
(ROADMAP #1). Confirms the module loads and the API key gate defaults to
off - does NOT exercise rip_session() itself, which needs a real drive/abcde.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import os
from importlib.machinery import SourceFileLoader

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "bin", "wtul-rip")


def _load_wtul_rip(monkeypatch, argv=None, env_key=None):
    monkeypatch.setattr("sys.argv", argv or ["wtul-rip"])
    if env_key is None:
        monkeypatch.delenv("SPINITRON_API_KEY", raising=False)
    else:
        monkeypatch.setenv("SPINITRON_API_KEY", env_key)
    loader = SourceFileLoader("wtul_rip_under_test", _MODPATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_spinitron_key_defaults_empty_when_unset(monkeypatch):
    mod = _load_wtul_rip(monkeypatch, env_key=None)
    assert mod.SPINITRON_API_KEY == ""


def test_spinitron_key_picked_up_when_set(monkeypatch):
    mod = _load_wtul_rip(monkeypatch, env_key="  test-key-123  ")
    assert mod.SPINITRON_API_KEY == "test-key-123"


def test_spinitron_module_importable_from_wtul_rip(monkeypatch):
    mod = _load_wtul_rip(monkeypatch, env_key=None)
    assert hasattr(mod.spinitron, "fetch_recent_spins")
    assert hasattr(mod.spinitron, "reorder_queue")
    assert hasattr(mod.spinitron, "matched_track_numbers")
