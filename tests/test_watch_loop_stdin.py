"""main()'s watch loop must survive a stdin that isn't a terminal.

Found 2026-07-25 while trying to drive a rehearsal from a batch job:
`wtul-rip </dev/null` pinned a core at 100%. A closed/EOF stdin is
permanently "readable" as far as select() is concerned, so the loop
returned instantly every time instead of polling the drive every
POLL_SECS - and the partial-disc retry prompt below it used bare input(),
which raises EOFError with no handler at all.

Neither needs a drive to reproduce or to test: both are in the loop's own
control flow. (Whether the drive-watching half then behaves correctly
against real hardware is a separate, still hardware-gated question.)

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import os
from importlib.machinery import SourceFileLoader

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "bin", "wtul-rip")


def _load(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", ["wtul-rip"])
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    loader = SourceFileLoader("wtul_rip_watchloop_test", _MODPATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    # A real fd at EOF - pytest's captured stdin has no fileno() to select on.
    monkeypatch.setattr(mod.sys, "stdin", open(os.devnull))
    monkeypatch.setattr(mod, "LOCKFILE", str(tmp_path / "lock"))
    return mod


class _Stop(Exception):
    """Breaks out of the otherwise-infinite watch loop from inside sleep."""


def _bounded_sleep(mod, monkeypatch, rounds):
    """Let the loop idle `rounds` times, then stop it."""
    seen = {"n": 0}

    def fake_sleep(_secs):
        seen["n"] += 1
        if seen["n"] >= rounds:
            raise _Stop
    monkeypatch.setattr(mod.time, "sleep", fake_sleep)
    return seen


def test_eof_stdin_is_dropped_from_the_select_set(monkeypatch, tmp_path, capsys):
    mod = _load(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "disc_audio_track_count", lambda dev: 0)
    _bounded_sleep(mod, monkeypatch, rounds=3)

    calls = {"n": 0}
    real_select = mod.select.select

    def counting_select(rlist, wlist, xlist, timeout):
        calls["n"] += 1
        assert calls["n"] <= 1, "select() on an EOF stdin - the busy-loop is back"
        return real_select(rlist, wlist, xlist, timeout)
    monkeypatch.setattr(mod.select, "select", counting_select)

    with pytest.raises(_Stop):
        mod.main()
    # One select to discover EOF, then polling only - and it kept watching
    # the drive rather than exiting.
    assert calls["n"] == 1
    assert "stdin closed" in capsys.readouterr().out


def test_drive_is_still_watched_after_stdin_closes(monkeypatch, tmp_path, capsys):
    """The point of not just exiting on EOF: a disc inserted afterwards
    must still get ripped."""
    mod = _load(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "disc_audio_track_count", lambda dev: 3)
    ripped = []
    monkeypatch.setattr(mod, "rip_session", lambda dev: ripped.append(dev) or True)
    _bounded_sleep(mod, monkeypatch, rounds=4)

    with pytest.raises(_Stop):
        mod.main()
    assert ripped == [mod.DEV], "a disc present after EOF should still be ripped"


def test_partial_disc_prompt_does_not_traceback_on_eof(monkeypatch, tmp_path, capsys):
    mod = _load(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "disc_audio_track_count", lambda dev: 3)
    # A disc that never fully rips: without the EOFError guard this loops
    # into input() and dies.
    monkeypatch.setattr(mod, "rip_session", lambda dev: False)

    def no_stdin(_prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", no_stdin)
    _bounded_sleep(mod, monkeypatch, rounds=4)

    with pytest.raises(_Stop):
        mod.main()
    out = capsys.readouterr().out
    assert "leaving the disc in the drive" in out
