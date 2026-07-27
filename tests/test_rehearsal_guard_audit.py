"""Every entry point, run under rehearsal, against poisoned side effects.

Five times now, a new code path has reached the outside world from inside a
rehearsal: the catalog write-back and the label print (2026-07-25), the
harness's own label print (run 19), the photo pairing (run 20), and the
`catalog` subcommand POSTing a simulated album at the station's live sheet
(run 25). Every one was caught by *running* it, never by reading it, and
each was then fixed with a test pinning that one site.

Per-site tests can only cover the sites that exist. This file covers the
ones that don't yet: it enumerates wtul-rip's entry points from the source
itself, so a command added next month joins the audit whether or not
anybody remembers this file exists, and drives each one with the three
real-world side effects replaced by tripwires that raise on contact.

The rule it enforces, stated once: *a rehearsal may read the outside world
(Spinitron, Discogs, AcoustID - a lookup changes nothing) but may never
write to it.* The three writes are the rotation-catalog POST, the M02 label
print, and the phone-pairing endpoint.

What this is not: hardware verification. It says nothing about a real drive
or a real disc. It says that no entry point can spend real label tape, put a
fake album in the station's catalog, or invite a phone upload for a disc
that doesn't exist.
"""
import importlib.util
import json
import os
import re
import sys
from importlib.machinery import SourceFileLoader

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "bin", "wtul-rip")

# Deliberately look real. A tripwire that fires on an unreachable hostname
# proves only that the network is down; these are the shapes the guard is
# supposed to stop, and nothing below is ever allowed to be dialled.
FAKE_CATALOG_URL = "https://script.google.com/macros/s/FAKE-CATALOG/exec"
FAKE_PHOTO_URL = "https://script.google.com/macros/s/FAKE-PHOTO/exec"

SPEC = {
    "discid": "700a8608",
    "artist": "Belong",
    "album": "October Language",
    "read_speed": "4.2",
    "tracks": [{"title": "I Never Lose", "length": "3:00"}],
}


class SideEffectEscaped(BaseException):
    """Raised by a tripwire when something reached the outside world.

    Deliberately a BaseException, not an AssertionError. The code under
    audit is full of correct, deliberate `except Exception` blocks - a
    network problem must never be able to stop a rip, so `catalog_retry()`
    swallows everything and prints. That discipline would also swallow a
    tripwire, and the audit would pass while the leak it was built to catch
    happened in front of it. Found exactly that way: the first version of
    this file could not fail.
    """


def _tripwire(what):
    def fire(*a, **k):
        raise SideEffectEscaped(
            f"{what} was reached from inside a rehearsal (args={a!r})")
    return fire


def _load(monkeypatch, tmp_path, argv=("wtul-rip",), seed=True):
    """Load bin/wtul-rip in rehearsal mode with every write-side effect
    replaced by a tripwire, and enough state seeded that each entry point
    has real work to do.

    The seeding is the part that's easy to get wrong: `catalog_retry()`
    returns early when the outbox is empty, so an unseeded audit would pass
    against a guard that does not exist.
    """
    home = tmp_path / "home"
    home.mkdir()
    spec_path = tmp_path / "disc.json"
    spec_path.write_text(json.dumps(SPEC))

    monkeypatch.setattr("sys.argv", list(argv))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("WTUL_SIMULATE_DRIVE", str(spec_path))
    monkeypatch.setenv("WTUL_SIMULATE_ROOT", str(tmp_path / "sandbox"))
    monkeypatch.setenv("CATALOG_WRITEBACK_URL", FAKE_CATALOG_URL)
    monkeypatch.setenv("PHOTO_CAPTURE_URL", FAKE_PHOTO_URL)
    # The suite-only escape hatch must not be inherited from whoever is
    # running pytest - it would disable the very guard under audit.
    monkeypatch.delenv("WTUL_SIMULATE_ALLOW_CATALOG", raising=False)

    loader = SourceFileLoader("wtul_rip_guard_audit", _MODPATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = mod
    try:
        loader.exec_module(mod)
    finally:
        sys.modules.pop(loader.name, None)

    # The three writes, at the library boundary rather than at the call site,
    # so a new caller is covered without naming it here.
    monkeypatch.setattr(mod.catalog_writeback, "write_row",
                        _tripwire("catalog write_row (POST to the live sheet)"))
    monkeypatch.setattr(mod.catalog_writeback, "confirm_row",
                        _tripwire("catalog confirm_row (GET against the live sheet)"))
    monkeypatch.setattr(mod.label_render, "print_label",
                        _tripwire("label print_label (real M02 over BLE)"))
    monkeypatch.setattr(mod.photo_capture, "new_pairing_code",
                        _tripwire("photo pairing (invites a real phone upload)"))
    monkeypatch.setattr(mod.photo_capture, "check_photo",
                        _tripwire("photo check_photo (hits the real GAS endpoint)"))
    # Read-only lookups are explicitly allowed, but a rehearsal shouldn't
    # need the network to run - stub them quiet rather than tripwired.
    monkeypatch.setattr(mod.spinitron, "fetch_recent_spins_public",
                        lambda *a, **k: [])

    if seed:
        _seed_work(mod)
    return mod


def _seed_work(mod):
    """Give every entry point something it would have to reach out for."""
    os.makedirs(mod.MIXES_ROOT, exist_ok=True)
    with open(mod.CATALOG_OUTBOX_FILE, "w") as f:
        json.dump([{
            "row": {"ARTIST": "Belong", "ALBUM": "October Language",
                    "DATE": "2026-07-27", "LOCAL": True, "DJ NAME": "Guy"},
            "queued_at": "2026-07-27T00:00:00", "attempts": 1, "error": "",
        }], f)
    album_dir = os.path.join(mod.RIPDIR, "Belong", "October Language (700a8608)")
    os.makedirs(album_dir, exist_ok=True)
    os.makedirs(os.path.dirname(mod.PENDING_PHOTOS_FILE), exist_ok=True)
    with open(mod.PENDING_PHOTOS_FILE, "w") as f:
        json.dump([{
            "pairing_code": "ABC123", "disc_id": "700a8608", "dir": album_dir,
            "mp3s": [], "artist": "Belong", "album": "October Language",
            "created_at": "2026-07-27T00:00:00",
        }], f)


# --------------------------------------------------------------------------
# Enumeration: the entry points come from the source, not from this list.
# --------------------------------------------------------------------------

def _watch_loop_commands():
    """Every interactive command main()'s dispatch chain accepts.

    Parsed out of the source rather than typed here, for the same reason the
    audit exists at all: a command added to that chain and not to a hand-kept
    list would be exactly the path nobody checked.
    """
    src = open(_MODPATH).read()
    body = src[src.index("\ndef main():"):src.index('\nif __name__ ==')]
    names = set()
    names.update(re.findall(r'low == "([a-z]+)"', body))
    for group in re.findall(r'low in \(([^)]*)\)', body):
        names.update(re.findall(r'"([^"!]+)"', group))
    names.update(n.strip() for n in re.findall(r'low\.startswith\("([a-z]+) "\)', body))
    return names


# How to drive each one, and whether it is expected to touch the outside
# world at all. Adding a command to main() without adding it here fails
# test_every_watch_loop_command_is_audited below - which is the whole point:
# the failure arrives at build time, not on a show night.
WATCH_COMMANDS = {
    "q": None,        # returns from the loop, runs nothing
    "!q": None,
    "h": lambda m: m.history(),
    "s": lambda m: m.status(),
    "e": None,        # `eject`, a local hardware call, not an outside write
    "spins": lambda m: m.check_for_new_spins(None),
    "photos": lambda m: m.check_pending_photos(),
    "speed": lambda m: m.speed_report(),
    "catalog": lambda m: m.catalog_retry(),
    "fix": lambda m: m.fix_by_discid("700a8608"),
    # argv-only: no watch-loop key, but it is still an entry point that runs
    # before init_simulation(), so it belongs in the audit.
    "doctor": lambda m: m.doctor(check_net=False),
}


@pytest.fixture(autouse=True)
def _no_blocking_prompts(monkeypatch):
    """`fix` is interactive. Feed it blanks (which accept whatever suggestion
    it found) and then EOF, so the audit drives it all the way through the
    move/retag path instead of stopping at the first prompt."""
    answers = iter([""] * 4)

    def fake_input(prompt=""):
        try:
            return next(answers)
        except StopIteration:
            raise EOFError
    monkeypatch.setattr("builtins.input", fake_input)


def test_every_watch_loop_command_is_audited():
    missing = _watch_loop_commands() - set(WATCH_COMMANDS)
    assert not missing, (
        f"new watch-loop command(s) {sorted(missing)} are not in this file's "
        "WATCH_COMMANDS table. Add each one, decide whether it can reach the "
        "sheet/printer/phone endpoint, and let the audit run it.")


def test_every_subcommand_is_audited(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path, seed=False)
    missing = set(mod.SUBCOMMANDS) - set(WATCH_COMMANDS)
    assert not missing, (
        f"new argv subcommand(s) {sorted(missing)} are not audited. Every "
        "subcommand so far is also a watch-loop command; if that stops being "
        "true, give this file its own table for them.")


def test_subcommands_and_handlers_cannot_drift(monkeypatch, tmp_path):
    """`catalog` was added to the dispatch and not to SUBCOMMANDS, so
    `wtul-rip catalog` parsed its own subcommand name as a device and ran
    against /dev/catalog with a bogus lockfile. One list, pinned here."""
    mod = _load(monkeypatch, tmp_path, seed=False)
    assert set(mod.SUBCOMMANDS) == set(mod._SUBCOMMAND_HANDLERS)
    for name in mod.SUBCOMMANDS:
        assert mod._parse_device(["wtul-rip", name]) == "/dev/sr0", (
            f"'{name}' is being read as a device name")


# --------------------------------------------------------------------------
# The audit itself: run each entry point, assert nothing escaped.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(k for k, v in WATCH_COMMANDS.items()
                                        if v is not None))
def test_entry_point_touches_nothing_outside_this_machine(name, monkeypatch,
                                                          tmp_path, capsys):
    mod = _load(monkeypatch, tmp_path)
    WATCH_COMMANDS[name](mod)
    # Reaching here means no tripwire fired. Nothing to assert about output:
    # the tripwires raise, and the next test proves they aren't swallowed.


@pytest.mark.parametrize("name", sorted(WATCH_COMMANDS))
def test_argv_subcommand_dispatch_reaches_nothing_outside(name, monkeypatch,
                                                          tmp_path):
    """The same commands again, through the argv path rather than the watch
    loop - the distinction that caused run 25's leak, since only the watch
    loop calls init_simulation() and so only it has a FakeDrive to check."""
    mod = _load(monkeypatch, tmp_path, argv=("wtul-rip", name))
    handler = mod._SUBCOMMAND_HANDLERS.get(name)
    if handler is None:
        pytest.skip(f"'{name}' is not an argv subcommand")
    assert mod.SIM is None, "init_simulation() must not have run"
    handler([name])


def test_a_complete_rip_touches_nothing_outside_this_machine(monkeypatch,
                                                             tmp_path, capsys):
    """The main entry point, and the one all three side effects actually
    live on: a rehearsal disc ripped end to end.

    Added after a mutation check found the audit's own blind spot - deleting
    the label-print guard left every test above green, because a command
    table enumerated from main()'s dispatch chain does not include "insert a
    disc". The commands are the paths that grow; the rip is the path that
    matters.
    """
    mod = _load(monkeypatch, tmp_path)
    # A real selectable stdin at EOF: rip_session() select()s on it, and
    # pytest's captured stdin has no fileno.
    monkeypatch.setattr(mod.sys, "stdin", open(os.devnull))
    mod.init_simulation()
    assert mod.rip_session(mod.DEV) is True, "the rehearsal disc should complete"
    out = capsys.readouterr().out
    for expected in ("Catalog: write-back SUPPRESSED",
                     "Label: print SUPPRESSED",
                     "Photo capture: pairing SUPPRESSED"):
        assert expected in out, f"missing suppression notice: {expected}"


def test_the_tripwires_actually_fire(monkeypatch, tmp_path):
    """A guard audit that can't fail is worse than none - it reads as
    coverage. Drop the guard and the catalog entry point must trip."""
    mod = _load(monkeypatch, tmp_path)
    monkeypatch.setattr(mod, "rehearsing", lambda: False)
    with pytest.raises(SideEffectEscaped):
        mod.catalog_retry()


def test_a_rehearsal_is_rehearsing_on_every_entry_point(monkeypatch, tmp_path):
    """`rehearsing()` must not depend on init_simulation() having run -
    that dependency is precisely what leaked a simulated album into the
    station's live catalog from `wtul-rip catalog`."""
    mod = _load(monkeypatch, tmp_path, argv=("wtul-rip", "catalog"), seed=False)
    assert mod.SIM is None
    assert mod.rehearsing() is True


def test_not_rehearsing_when_the_env_var_is_absent(monkeypatch, tmp_path):
    """The mirror case, and the one that matters on show night: without
    WTUL_SIMULATE_DRIVE nothing is suppressed."""
    monkeypatch.setattr("sys.argv", ["wtul-rip"])
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("WTUL_SIMULATE_DRIVE", raising=False)
    loader = SourceFileLoader("wtul_rip_guard_audit_real", _MODPATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = mod
    try:
        loader.exec_module(mod)
    finally:
        sys.modules.pop(loader.name, None)
    assert mod.rehearsing() is False


def test_no_side_effect_site_still_asks_the_wrong_question():
    """The suppression sites must gate on rehearsing(), never on `SIM is not
    None` - SIM is built by init_simulation(), which three of the four entry
    points never call. Checked against the source because the whole failure
    mode is a site nobody thought to run."""
    src = open(_MODPATH).read()
    offenders = []
    in_doc = False
    for line_no, line in enumerate(src.splitlines(), 1):
        # Prose says what it likes - including, in rehearsing()'s own
        # docstring, the wrong question spelled out as the wrong question.
        if line.count('"""') == 1:
            in_doc = not in_doc
            continue
        if in_doc or line.lstrip().startswith("#"):
            continue
        if "SIM is not None" not in line:
            continue
        # The legitimate uses: dispatching a command at the fake drive, and
        # replaying its output. Those need the object, not the question.
        if re.search(r"SIM(\.| is not None and SIM\.)", line) or \
           "SIM.handles(cmd)" in line:
            continue
        offenders.append(f"{line_no}: {line.strip()}")
    assert not offenders, (
        "these lines decide something with `SIM is not None`; if any of them "
        "gates a real-world side effect it is wrong on every entry point but "
        "the watch loop - use rehearsing():\n  " + "\n  ".join(offenders))
