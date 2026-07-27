"""Preflight checks for `wtul-rip doctor`.

The point: before show night, answer "is this rig actually ready to rip a
disc?" *without* needing a disc — every failure mode that has bitten a
real rip so far (missing encoder, a ~/.abcde.conf whose OUTPUTDIR has
drifted from wtul-rip's RIPDIR, a stale lockfile from a killed session,
a full disk, an unreachable metadata service) is visible from the
machine alone.

Everything the checks touch comes in through a Context, so the whole
suite runs against synthetic state in tests — no drive, no network, no
installed abcde.
"""
import os
import time
import urllib.error
import urllib.request

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"

# Ordering for "worst status wins" — a single FAIL decides the exit code.
_RANK = {OK: 0, WARN: 1, FAIL: 2}

# A CD's worth of wav+mp3 with LOWDISK=y (one track at a time) is well
# under a GB, but a show night is several discs into the same dated mix
# folder.
DISK_WARN_KB = 2 * 1024 * 1024
DISK_FAIL_KB = 500 * 1024

NET_TIMEOUT = 6

# Reachability probes. Spinitron is the on-air signal (#1), the other
# three are the metadata-fix fallback chain (#2). None of them stop a
# rip, so they only ever WARN.
NET_TARGETS = [
    ("Spinitron", "https://spinitron.com/WTUL/"),
    ("AcoustID", "https://api.acoustid.org/v2/lookup"),
    ("Discogs", "https://api.discogs.com/database/search"),
    ("MusicBrainz", "https://musicbrainz.org/ws/2/release/"),
]


class Check:
    def __init__(self, name, status, detail, fix=None):
        self.name = name
        self.status = status
        self.detail = detail
        self.fix = fix

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"Check({self.name!r}, {self.status!r}, {self.detail!r})"


def _default_run(cmd, timeout=15):
    import subprocess
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, stdin=subprocess.DEVNULL)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 1, str(e)


def _default_fetch(url, timeout=NET_TIMEOUT):
    """True if the host answered at all. A 4xx (Discogs without a token,
    MusicBrainz without query args) still proves reachability, which is
    all this check claims — so only a transport-level failure counts."""
    req = urllib.request.Request(url, headers={"User-Agent": "wtul-rip-doctor/1.0"})
    try:
        urllib.request.urlopen(req, timeout=timeout).read(1)
        return True, ""
    except urllib.error.HTTPError as e:
        return True, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


def _default_free_kb(path):
    try:
        st = os.statvfs(path)
    except OSError:
        return None
    return int(st.f_bavail * st.f_frsize / 1024)


class Context:
    """Everything the checks are allowed to know about the machine."""

    def __init__(self, dev, home, mixes_root, ripdir, abcde_conf,
                 noeject_conf, lockfile, environ=None, simulating=False,
                 check_net=True, stale_tempdir_secs=6 * 3600,
                 which=None, run=None, fetch=None, free_kb=None,
                 exists=None, isdir=None, isfile=None, access=None,
                 glob_=None, mtime=None, now=None, import_ok=None,
                 lock_is_stale=None, outbox_pending=None):
        self.dev = dev
        self.home = home
        self.mixes_root = mixes_root
        self.ripdir = ripdir
        self.abcde_conf = abcde_conf
        self.noeject_conf = noeject_conf
        self.lockfile = lockfile
        self.environ = environ if environ is not None else os.environ
        self.simulating = simulating
        self.check_net = check_net
        self.stale_tempdir_secs = stale_tempdir_secs

        import shutil
        import glob as globmod
        self.which = which or shutil.which
        self.run = run or _default_run
        self.fetch = fetch or _default_fetch
        self.free_kb = free_kb or _default_free_kb
        self.exists = exists or os.path.exists
        self.isdir = isdir or os.path.isdir
        self.isfile = isfile or os.path.isfile
        self.access = access or os.access
        self.glob = glob_ or globmod.glob
        self.mtime = mtime or os.path.getmtime
        self.now = now or time.time
        self.import_ok = import_ok or _default_import_ok
        # Injected by wtul-rip, which owns the Lock class. None means
        # "can't tell" and the check degrades to a WARN rather than
        # claiming a stale lock it didn't verify.
        self.lock_is_stale = lock_is_stale
        # Injected by wtul-rip: a zero-arg callable returning the queued
        # catalog rows (lib/catalog_outbox.py). None means the caller
        # didn't wire it, and the check reports that rather than claiming
        # an empty queue it never looked at.
        self.outbox_pending = outbox_pending


def _default_import_ok(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False


# --- individual checks -------------------------------------------------
#
# Each returns a Check or a list of them. Adding one here is the only
# thing needed to add it to the report.

# (binary, required?, what breaks without it)
BINARIES = [
    ("abcde", True, "the ripper itself - no rip can start"),
    ("cdparanoia", True, "abcde's CD reader"),
    ("cd-discid", True, "disc ID lookup; abcde can't identify a disc"),
    ("eyeD3", True, "id3 tagging; abcde fails before touching the disc"),
    ("lame", True, "mp3 encoder (MAKEMP3ENCODERSYNTAX=lame)"),
    ("udevadm", True, "how wtul-rip sees a disc get inserted"),
    ("eject", False, "the post-rip eject; rips still work, disc stays in"),
]


def check_binaries(ctx):
    out = []
    for name, required, why in BINARIES:
        path = ctx.which(name)
        if path:
            out.append(Check(f"binary: {name}", OK, path))
        else:
            out.append(Check(
                f"binary: {name}", FAIL if required else WARN,
                f"not on PATH - {why}",
                fix=f"apt-get install {name}"))
    return out


def check_mutagen(ctx):
    if ctx.import_ok("mutagen"):
        return Check("python: mutagen", OK, "importable")
    return Check(
        "python: mutagen", WARN,
        "missing - `h` history view and the fix flow's retagging are off",
        fix="apt-get install python3-mutagen")


def check_drive(ctx):
    if ctx.simulating:
        return Check("drive", OK, f"rehearsal mode - {ctx.dev} not consulted")
    if not ctx.exists(ctx.dev):
        return Check(
            "drive", FAIL, f"{ctx.dev} does not exist - no optical drive attached",
            fix="plug the drive in, or pass the right device: wtul-rip sr1")
    if not ctx.access(ctx.dev, os.R_OK):
        return Check(
            "drive", FAIL, f"{ctx.dev} exists but is not readable by this user",
            fix="add yourself to the cdrom group: sudo usermod -aG cdrom $USER")
    return Check("drive", OK, f"{ctx.dev} present and readable")


def check_conf_files(ctx):
    out = []
    for label, path, why in (
        ("~/.abcde.conf", ctx.abcde_conf,
         "abcde falls back to its own defaults - wrong output dir, wrong format"),
        ("~/.abcde-noeject.conf", ctx.noeject_conf,
         "every abcde call uses `-c` on it; without it the metadata scrape "
         "ejects the disc before a single track is ripped"),
    ):
        if ctx.isfile(path):
            out.append(Check(f"config: {label}", OK, path))
        else:
            out.append(Check(f"config: {label}", FAIL, f"missing - {why}",
                             fix="bash install.sh"))
    return out


def check_outputdir_matches_ripdir(ctx):
    """The known foot-gun: wtul-rip computes where a disc's files *will*
    land (album_dir_path) independently of where abcde actually writes
    them. If ~/.abcde.conf's OUTPUTDIR has drifted from RIPDIR, the rip
    succeeds and every downstream step - the tracklist, retagging, the
    catalog write-back - looks at an empty directory."""
    if not ctx.isfile(ctx.abcde_conf):
        return Check("config: OUTPUTDIR vs RIPDIR", WARN,
                     "skipped - ~/.abcde.conf missing (see above)")
    script = ('. "$1" >/dev/null 2>&1; printf "%s\\n%s\\n" '
              '"$OUTPUTDIR" "$WAVOUTPUTDIR"')
    rc, out = ctx.run(["bash", "-c", script, "bash", ctx.abcde_conf])
    # Deliberately not out.strip(): both vars being *unset* is a real
    # (and bad) configuration, and it prints as two empty lines - which
    # strip() would collapse into "couldn't evaluate the file".
    lines = out.split("\n")
    if rc != 0 or len(lines) < 2:
        return Check("config: OUTPUTDIR vs RIPDIR", FAIL,
                     f"could not evaluate {ctx.abcde_conf}: {out.strip()[:200]}",
                     fix="check ~/.abcde.conf is valid shell")
    outputdir, wavoutputdir = lines[0].strip(), lines[1].strip()
    want = ctx.ripdir
    problems = []
    if outputdir != want:
        problems.append(f"OUTPUTDIR={outputdir or '(unset)'}")
    if wavoutputdir != want:
        problems.append(f"WAVOUTPUTDIR={wavoutputdir or '(unset)'}")
    if problems:
        return Check(
            "config: OUTPUTDIR vs RIPDIR", FAIL,
            f"drifted from wtul-rip's RIPDIR ({want}): " + ", ".join(problems),
            fix="re-copy this repo's abcde.conf to ~/.abcde.conf")
    return Check("config: OUTPUTDIR vs RIPDIR", OK, f"both resolve to {want}")


def check_disk(ctx):
    # Check the deepest directory that already exists: today's RIPDIR is
    # created at rip time, so on a fresh morning it legitimately isn't
    # there yet and its parent is the right thing to measure.
    path = ctx.ripdir
    while path and not ctx.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    free = ctx.free_kb(path)
    if free is None:
        return Check("disk space", FAIL, f"cannot stat {path}")
    gb = free / 1024 / 1024
    if free < DISK_FAIL_KB:
        status = FAIL
    elif free < DISK_WARN_KB:
        status = WARN
    else:
        status = OK
    detail = f"{gb:.1f} GB free on {path}"
    if status != OK:
        detail += " - a rip needs room for wav + mp3 per track"
    return Check("disk space", status, detail)


def check_writable(ctx):
    path = ctx.mixes_root
    while path and not ctx.isdir(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    if not ctx.isdir(path):
        return Check("mix folder", FAIL, f"{ctx.mixes_root} has no existing parent")
    if not ctx.access(path, os.W_OK):
        return Check("mix folder", FAIL, f"{path} is not writable by this user")
    return Check("mix folder", OK, f"{path} writable")


def check_lock(ctx):
    if not ctx.exists(ctx.lockfile):
        return Check("lockfile", OK, "no rip in progress")
    if ctx.lock_is_stale is None:
        return Check("lockfile", WARN,
                     f"{ctx.lockfile} exists; could not test whether it is held")
    if ctx.lock_is_stale(ctx.lockfile):
        return Check("lockfile", WARN,
                     f"{ctx.lockfile} is stale (left by a killed session) - "
                     "harmless, wtul-rip will take it",
                     fix=f"rm {ctx.lockfile}")
    return Check("lockfile", WARN,
                 f"another wtul-rip is holding {ctx.lockfile} right now")


def check_stale_tempdirs(ctx):
    dirs = ctx.glob(os.path.join(ctx.ripdir, "abcde.*"))
    now = ctx.now()
    stale = []
    for d in dirs:
        try:
            age = now - ctx.mtime(d)
        except OSError:
            continue
        if age > ctx.stale_tempdir_secs:
            stale.append(d)
    if not stale:
        return Check("abcde scratch dirs", OK,
                     f"{len(dirs)} in today's folder, none stale")
    return Check("abcde scratch dirs", WARN,
                 f"{len(stale)} abandoned scratch dir(s) older than "
                 f"{ctx.stale_tempdir_secs // 3600}h - wtul-rip prunes these "
                 "at rip time, but a stale one can confuse a resume",
                 fix="rm -rf " + " ".join(stale[:3]))


# (env var, what it enables, hard-required?)
CREDENTIALS = [
    ("ACOUSTID_API_KEY", "fingerprint lookup, step 1 of `fix <discid>`"),
    ("DISCOGS_TOKEN", "Discogs metadata lookup, step 2 of `fix <discid>`"),
    ("CATALOG_WRITEBACK_URL", "auto-logging rips to the rotation catalog (#8)"),
    ("PHOTO_CAPTURE_URL", "the phone cover-photo hand-off (#4)"),
]


def check_credentials(ctx):
    out = []
    for var, what in CREDENTIALS:
        if ctx.environ.get(var, "").strip():
            out.append(Check(f"env: {var}", OK, f"set - {what} enabled"))
        else:
            out.append(Check(
                f"env: {var}", WARN, f"unset - {what} is off",
                fix=f"add {var}=... to ~/.config/wtul/secrets.env"))
    return out


def check_network(ctx):
    if not ctx.check_net:
        return [Check("network", OK, "skipped (--no-net)")]
    out = []
    for name, url in NET_TARGETS:
        ok, note = ctx.fetch(url)
        if ok:
            out.append(Check(f"net: {name}", OK, note or "reachable"))
        else:
            out.append(Check(
                f"net: {name}", WARN,
                f"unreachable ({note[:120]}) - rips still work, "
                "metadata lookup degrades"))
    return out


def check_catalog_outbox(ctx):
    """Rips that finished but never made it into the rotation catalog.
    A preflight is the one moment someone is already looking at this
    tool's output before a show, so it's where a queue nobody typed
    'catalog' to drain should surface."""
    if ctx.outbox_pending is None:
        return [Check("catalog outbox", WARN,
                      "not wired - can't tell whether any rip is unlogged")]
    pending = ctx.outbox_pending()
    if not pending:
        return [Check("catalog outbox", OK,
                      "empty - every completed rip reached the sheet")]
    labels = ", ".join(
        f"{(e.get('row') or {}).get('ARTIST', '?')} - "
        f"{(e.get('row') or {}).get('ALBUM', '?')}" for e in pending[:3])
    more = f" (+{len(pending) - 3} more)" if len(pending) > 3 else ""
    return [Check("catalog outbox", WARN,
                  f"{len(pending)} rip(s) never reached the catalog: "
                  f"{labels}{more}",
                  fix="run `wtul-rip catalog` to retry them")]


CHECKS = [
    check_binaries,
    check_mutagen,
    check_drive,
    check_conf_files,
    check_outputdir_matches_ripdir,
    check_writable,
    check_disk,
    check_lock,
    check_stale_tempdirs,
    check_catalog_outbox,
    check_credentials,
    check_network,
]


def run_checks(ctx, checks=None):
    results = []
    for fn in (checks if checks is not None else CHECKS):
        try:
            got = fn(ctx)
        except Exception as e:
            # A check that crashes is itself a finding — never let it take
            # the whole preflight down, and never let it pass silently.
            results.append(Check(fn.__name__, FAIL, f"check raised {e!r}"))
            continue
        results.extend(got if isinstance(got, list) else [got])
    return results


def worst_status(checks):
    return max((c.status for c in checks), key=lambda s: _RANK[s], default=OK)


def format_report(checks):
    lines = []
    for c in checks:
        lines.append(f"  [{c.status:>4}] {c.name}: {c.detail}")
        if c.fix and c.status != OK:
            lines.append(f"         fix: {c.fix}")
    n_fail = sum(1 for c in checks if c.status == FAIL)
    n_warn = sum(1 for c in checks if c.status == WARN)
    lines.append("")
    if n_fail:
        lines.append(f"NOT READY: {n_fail} failure(s), {n_warn} warning(s). "
                     "A rip will not work until the failures above are fixed.")
    elif n_warn:
        lines.append(f"Ready to rip, with {n_warn} warning(s) - degraded "
                     "features are named above.")
    else:
        lines.append("Ready to rip - all checks passed.")
    return "\n".join(lines)
