"""album_dir_path() must predict the folder abcde actually writes into.

The bug this file exists to stop coming back (found 2026-07-25): abcde.conf
defines a `mungefilename()` that maps ":" to "-" and deletes `'`, `"`, `?`
and control characters from every path component, and abcde applies it to
ARTISTFILE/ALBUMFILE before writing. `album_dir_path()` didn't, so for any
disc whose metadata contained one of those characters - "It's Alive",
"Songs: Ohia", "Who's Next" - wtul-rip looked for the ripped files in a
folder that had never existed. Nothing crashed; resume-skip, live retagging
and the post-fix move all just quietly did the wrong thing.

The first test here doesn't re-type the munging rule as an expected string:
it runs the real shell function out of abcde.conf and compares. If someone
edits the conf, this fails rather than drifting.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import os
import shutil
import subprocess
from importlib.machinery import SourceFileLoader

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "bin", "wtul-rip")
_CONF = os.path.join(_HERE, "..", "abcde.conf")

# Every character class the conf's mungefilename touches, plus the ordinary
# names that must survive it untouched.
SAMPLES = [
    "It's Alive",
    "Songs: Ohia",
    "Who's Next?",
    'The "Great" Escape',
    "Belong",
    "October Language",
    "Unknown Album",
    "Sunn O)))",
    "AC/DC",
    "Godspeed You! Black Emperor",
    "  padded  ",
    "Anti-Cimex",
    "múm",
    "1000 Hurts",
]


def _load(monkeypatch):
    monkeypatch.setattr("sys.argv", ["wtul-rip"])
    loader = SourceFileLoader("wtul_rip_munge_test", _MODPATH)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _shell_munge(value):
    """Run abcde.conf's own mungefilename() on `value`."""
    script = f'. "{os.path.abspath(_CONF)}" >/dev/null 2>&1; mungefilename "$1"'
    p = subprocess.run(["sh", "-c", script, "sh", value],
                       stdout=subprocess.PIPE, text=True, timeout=30)
    assert p.returncode == 0, f"sourcing abcde.conf failed for {value!r}"
    # Command substitution/echo semantics: the trailing newline is not part
    # of the name abcde ends up using.
    return p.stdout.rstrip("\n")


@pytest.mark.skipif(shutil.which("sh") is None, reason="no POSIX sh available")
@pytest.mark.parametrize("value", SAMPLES)
def test_python_munge_matches_the_shell_function_in_abcde_conf(monkeypatch, value):
    mod = _load(monkeypatch)
    assert mod.munge_filename(value) == _shell_munge(value)


def test_munge_strips_control_characters(monkeypatch):
    # `tr -d [:cntrl:]` covers these; a CDDB field really can carry a stray
    # newline or tab, and a newline in a directory name is its own disaster.
    mod = _load(monkeypatch)
    assert mod.munge_filename("Bad\nName\tHere\x7f") == "BadNameHere"


def test_munge_leaves_slash_alone_like_abcde_does(monkeypatch):
    # Deliberate: abcde's mungefilename doesn't strip "/" either, so "AC/DC"
    # nests a directory in BOTH. Mirroring the real behaviour is the point;
    # if this is ever "fixed" it has to be fixed in abcde.conf first.
    mod = _load(monkeypatch)
    assert mod.munge_filename("AC/DC") == "AC/DC"


def test_album_dir_path_munges_both_components(monkeypatch):
    mod = _load(monkeypatch)
    path = mod.album_dir_path("Guns N' Roses", "Appetite: Destruction?", "700a8608")
    assert path == os.path.join(mod.RIPDIR, "Guns N Roses", "Appetite- Destruction")


def test_unknown_album_suffix_is_appended_after_munging(monkeypatch):
    # OUTPUTFORMAT appends " (${CDDBDISCID})" outside ${ALBUMFILE}, and tests
    # the RAW "$DALBUM" for the fallback - so the parens/space in the suffix
    # itself are never munged, and the check can't be done post-munge.
    mod = _load(monkeypatch)
    assert mod.album_dir_path("Unknown Artist", "", "700a8608") == os.path.join(
        mod.RIPDIR, "Unknown Artist", "Unknown Album (700a8608)")
    assert mod.album_dir_path("Unknown Artist", "Unknown Album", "700a8608") == os.path.join(
        mod.RIPDIR, "Unknown Artist", "Unknown Album (700a8608)")


def test_a_real_album_named_unknown_album_is_not_special_cased_away(monkeypatch):
    # A disc whose CDDB entry really says "Unknown Album" is indistinguishable
    # from the fallback here - abcde does exactly the same thing, so wtul-rip
    # agreeing with it is correct even though the folder name is a bit odd.
    mod = _load(monkeypatch)
    assert mod.album_dir_path("Real Artist", "Unknown Album", "aabbccdd").endswith(
        os.path.join("Real Artist", "Unknown Album (aabbccdd)"))


def test_existing_track_numbers_finds_tracks_in_the_munged_folder(monkeypatch, tmp_path):
    """The end-to-end shape of the bug: files land in the munged folder, and
    resume-skip has to find them there on reinsert."""
    mod = _load(monkeypatch)
    monkeypatch.setattr(mod, "RIPDIR", str(tmp_path))
    where = mod.album_dir_path("Belong", "It's Alive", "700a8608")
    os.makedirs(where)
    for name in ("01-One.mp3", "02-Two.mp3"):
        open(os.path.join(where, name), "wb").close()

    assert os.path.basename(where) == "Its Alive"      # what abcde wrote
    assert mod.existing_track_numbers(
        mod.album_dir_path("Belong", "It's Alive", "700a8608")) == {1, 2}
    assert mod.find_track_file(where, 2).endswith("02-Two.mp3")
