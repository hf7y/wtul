"""Simulated optical drive - rehearse a whole rip with no disc and no drive.

Why this exists: every hardware-gated item on this project's backlog has
sat unverifiable across many unattended batch runs for the same reason -
`rip_session()` in `bin/wtul-rip` can only be exercised with a real disc
in a real drive, so its actual control flow (metadata scrape -> tracklist
-> per-track rip -> live retag -> partial-disc retry -> eject -> catalog
write-back) gets no coverage at all between show nights. Unit tests cover
the leaf parsers; nothing covered the shape of a session.

This module answers the four commands `bin/wtul-rip` uses to talk to
hardware - `udevadm info`, `cdparanoia -Q`, `abcde -a cddb`, and
`abcde -a read,encode,tag,move N` - from a JSON disc spec, writing the
same scratch files (`cddbdiscid`, `cddbread.1`) and emitting the same
shape of output lines the real tools do.

**This is a REHEARSAL, not verification.** It proves wtul-rip's own logic
handles a disc-shaped interaction; it proves nothing about whether a real
drive, a real scratched CD, or the real abcde behave the way a spec here
claims they do. A green rehearsal does NOT clear anything that FOCUS.md
marks as needing hands-on hardware verification - it only means the
session logic was already wrong-free before the disc goes in, so a scarce
real-disc session isn't spent finding a bug that could have been found
here.

It never touches `DEV`, and it refuses to write into the real music
library (see `sandbox_root`) - a rehearsal that polluted
`~/Music/mixes/<today>` with fake tracks would corrupt the very thing the
real ritual produces.

Activated only by the `WTUL_SIMULATE_DRIVE` env var, which is never set in
normal use. If it IS set but points at something unusable, loading raises
`SpecError` and `bin/wtul-rip` exits - it deliberately does not fall back
to the real drive, since silently ripping a real disc when you asked for a
rehearsal (or vice versa) is the one failure mode worth being loud about.
"""
import json
import os
import re
import time

ENV_SPEC = "WTUL_SIMULATE_DRIVE"
ENV_ROOT = "WTUL_SIMULATE_ROOT"

# 75 CD frames (sectors) per second, per the Red Book spec - used to turn a
# spec's human "3:55" length into the sector counts cdparanoia prints.
FRAMES_PER_SEC = 75
# Sectors of lead-in before track 1's data starts, as cd-discid reports it.
LEADIN_FRAMES = 150


class SpecError(Exception):
    """A simulation was requested but the disc spec is unusable."""


# A built-in spec so `WTUL_SIMULATE_DRIVE=demo` works with no file to write.
# Deliberately not a real album: a rehearsal transcript that looks like a
# genuine rip in the logs would be worse than one that's obviously fake.
DEMO_SPEC = {
    "discid": "abcd1234",
    "artist": "Rehearsal Artist",
    "album": "Simulated Disc",
    "match": True,
    "read_speed": "4.2",
    "tracks": [
        {"title": "Simulated Track One", "length": "3:12"},
        {"title": "Simulated Track Two", "length": "4:05"},
        {"title": "Simulated Track Three", "length": "2:48"},
    ],
}


def _parse_length(text):
    """'3:55' or '3:55.20' -> whole seconds. Raises SpecError on junk."""
    m = re.fullmatch(r"\s*(\d+):([0-5]?\d)(?:\.(\d+))?\s*", str(text))
    if not m:
        raise SpecError(f"track length {text!r} is not M:SS")
    return int(m.group(1)) * 60 + int(m.group(2))


def load_spec(value):
    """Resolve the `WTUL_SIMULATE_DRIVE` value into a validated spec dict.

    `value` is either the literal "demo" or a path to a JSON file. Every
    failure here is loud on purpose - see the module docstring.
    """
    if not value or not str(value).strip():
        raise SpecError(f"{ENV_SPEC} is set but empty")
    value = str(value).strip()

    if value == "demo":
        raw = json.loads(json.dumps(DEMO_SPEC))  # deep copy, never mutate the constant
    else:
        if not os.path.isfile(value):
            raise SpecError(f"{ENV_SPEC}={value!r} is not 'demo' and not a readable file")
        try:
            with open(value, "r", errors="replace") as f:
                raw = json.load(f)
        except (OSError, ValueError) as e:
            raise SpecError(f"could not read disc spec {value!r}: {e}")

    if not isinstance(raw, dict):
        raise SpecError(f"disc spec must be a JSON object, got {type(raw).__name__}")

    tracks_raw = raw.get("tracks")
    if not isinstance(tracks_raw, list) or not tracks_raw:
        raise SpecError("disc spec needs a non-empty 'tracks' list")

    tracks = []
    for i, t in enumerate(tracks_raw, start=1):
        if isinstance(t, str):
            t = {"title": t}
        if not isinstance(t, dict):
            raise SpecError(f"track {i} must be an object or a title string")
        title = str(t.get("title") or f"Track {i}").strip() or f"Track {i}"
        tracks.append({
            "num": i,
            "title": title,
            "seconds": _parse_length(t.get("length", "3:30")),
            # A track the simulated drive cannot read - rehearses the
            # per-track failure/retry path, which a clean disc never reaches.
            "fails": bool(t.get("fails", False)),
        })

    discid = str(raw.get("discid") or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{8}", discid):
        raise SpecError(f"disc spec 'discid' must be 8 hex digits, got {discid!r}")

    return {
        "discid": discid.lower(),
        "artist": str(raw.get("artist") or "Unknown Artist").strip(),
        "album": str(raw.get("album") or "").strip(),
        # match=False rehearses the no-CDDB/MusicBrainz-hit path (the
        # "Unknown Album (discid)" fallback), which is the exact case #2's
        # metadata-fix flow exists to clean up.
        "match": bool(raw.get("match", True)),
        # disc_present=False rehearses the idle poll loop with an empty drive.
        "disc_present": bool(raw.get("disc_present", True)),
        "read_speed": str(raw.get("read_speed") or "4.2").strip(),
        "tracks": tracks,
    }


def sandbox_root(explicit=None):
    """Where a rehearsal is allowed to write its fake tracks.

    Never the real mix folder: `~/.cache/wtul/rehearsal` by default,
    overridable with `WTUL_SIMULATE_ROOT` for tests. A rehearsal that wrote
    into `~/Music/mixes/<today>` would put fake mp3s in the folder that
    actually gets burned to a CD.

    This is the MIXES_ROOT equivalent, not the dated per-day folder - the
    caller adds the date, so the sandbox keeps the same
    `<root>/<date>/` + `<root>/.logs/` shape production uses.
    """
    root = explicit or os.environ.get(ENV_ROOT, "").strip()
    if root:
        return root
    return os.path.join(os.path.expanduser("~"), ".cache", "wtul", "rehearsal")


def _strip_timeout(cmd):
    """Drop a leading `timeout --flags 900` wrapper so the real command shows.

    `rip_track()` wraps abcde in the external `timeout` utility; without
    this the simulator would see argv[0]=="timeout" and decline to handle
    a command it actually knows.
    """
    if not cmd or os.path.basename(str(cmd[0])) != "timeout":
        return [str(c) for c in cmd]
    i = 1
    while i < len(cmd):
        arg = str(cmd[i])
        if arg.startswith("-") or re.fullmatch(r"\d+(\.\d+)?[smhd]?", arg):
            i += 1
            continue
        break
    return [str(c) for c in cmd[i:]]


def _abcde_actions(cmd):
    """The value of abcde's `-a` flag, or "" if absent."""
    for i, arg in enumerate(cmd):
        if arg == "-a" and i + 1 < len(cmd):
            return cmd[i + 1]
    return ""


def _silent_mp3(seconds):
    """A small but genuinely valid MPEG-1 Layer III file of silence.

    Not a zero-byte stub: `retag_mp3()`/`history()` both read these back
    with mutagen, so a rehearsal has to produce something mutagen can
    actually parse or it would "fail" on its own placeholder rather than on
    anything real. 32kbps mono 44.1kHz - header bytes are fixed for that
    combination; frame payload is zeroes, which decodes as silence.
    """
    header = bytes([0xFF, 0xFB, 0x10, 0xC4])
    frame = header + b"\x00" * 100          # 144*32000//44100 == 104 bytes
    frame_secs = 1152 / 44100.0
    # Cap the file size: a 5-minute track at real length is pointless bulk
    # for a rehearsal, and the tag/length plumbing is identical either way.
    # Floor of 32 frames, not 1: mutagen needs several consecutive frames to
    # sync before it will report a length at all, so a 0:00 track (a spec
    # typo, or a real disc's stub/silent index track) otherwise wrote a
    # 104-byte file that raised HeaderNotFoundError the moment history() or
    # retag_mp3() touched it - the rehearsal failing on its own placeholder
    # rather than on anything real. Found by the 2026-07-25 stress pass.
    count = max(32, min(int(seconds / frame_secs), 400))
    return frame * count


class FakeDrive:
    """Replays one disc spec in place of a real drive.

    `album_dir_fn` is passed in by `bin/wtul-rip` rather than reimplemented
    here on purpose: where abcde lands a track is decided by
    `album_dir_path()` mirroring `abcde.conf`'s OUTPUTFORMAT, and a second
    copy of that rule here would drift from the real one and make the
    rehearsal pass while production broke.
    """

    def __init__(self, spec, ripdir, album_dir_fn, sleep_fn=None):
        self.spec = spec
        self.ripdir = ripdir
        self.album_dir_fn = album_dir_fn
        self.sleep_fn = sleep_fn if sleep_fn is not None else time.sleep
        self.tempdir = None
        self.ripped = []          # track numbers this rehearsal wrote
        self.ejected = False
        self._scrapes = 0         # keeps each scrape's tempdir distinct

    # -- description -----------------------------------------------------

    def banner(self):
        s = self.spec
        shape = "matched" if s["match"] else "NO metadata match (Unknown fallback)"
        return "\n".join([
            "=" * 68,
            "  SIMULATED DRIVE - this is a REHEARSAL, not a real rip.",
            f"  No disc is being read; {ENV_SPEC} is set.",
            f"  Disc: {s['artist']} - {s['album'] or '(no album)'} "
            f"[{s['discid']}], {len(s['tracks'])} tracks, {shape}",
            f"  Fake tracks are written under: {self.ripdir}",
            "  A green rehearsal does NOT count as hardware verification.",
            "=" * 68,
        ])

    # -- dispatch --------------------------------------------------------

    def _classify(self, cmd):
        cmd = _strip_timeout(cmd)
        if not cmd:
            return None, cmd
        prog = os.path.basename(cmd[0])
        if prog == "udevadm" and "info" in cmd:
            return "udev", cmd
        if prog == "cdparanoia" and "-Q" in cmd:
            return "toc", cmd
        if prog == "eject":
            return "eject", cmd
        if prog == "abcde":
            actions = _abcde_actions(cmd)
            if actions == "cddb":
                return "scrape", cmd
            if "read" in actions.split(","):
                return "rip", cmd
        return None, cmd

    def handles(self, cmd):
        kind, _ = self._classify(cmd)
        return kind is not None

    def run(self, cmd):
        """Synchronous equivalent of `sh()`: returns (rc, combined output)."""
        kind, cmd = self._classify(cmd)
        if kind is None:
            raise SpecError(f"simulator asked to run a command it does not handle: {cmd}")
        if kind == "udev":
            return 0, self._udev_output()
        if kind == "toc":
            return 0, self._toc_output()
        if kind == "eject":
            self.ejected = True
            return 0, ""
        if kind == "scrape":
            return 0, "\n".join(self._scrape()) + "\n"
        # A rip streamed through run() rather than stream() still has to work
        # (nothing calls it that way today, but silently doing nothing would
        # be the wrong failure).
        rc, lines = self._rip(cmd)
        return rc, "\n".join(lines) + "\n"

    def stream(self, cmd):
        """Equivalent of `sh_live()`'s subprocess: yields output lines, then
        sets `self.last_rc`. Kept a generator so wtul-rip can print each
        line as it "happens", the way a real rip looks."""
        kind, cmd = self._classify(cmd)
        if kind is None:
            raise SpecError(f"simulator asked to stream a command it does not handle: {cmd}")
        if kind == "rip":
            rc, lines = self._rip(cmd)
        else:
            rc, out = self.run(cmd)
            lines = out.splitlines()
        self.last_rc = rc
        return rc, lines

    # -- individual commands ---------------------------------------------

    def _udev_output(self):
        s = self.spec
        present = "1" if s["disc_present"] else "0"
        ntracks = len(s["tracks"]) if s["disc_present"] else 0
        return "\n".join([
            "DEVNAME=/dev/sr0",
            "ID_CDROM=1",
            f"ID_CDROM_MEDIA={present}",
            f"ID_CDROM_MEDIA_TRACK_COUNT_AUDIO={ntracks}",
            "ID_CDROM_MEDIA_CD=1",
            "WTUL_SIMULATED=1",
        ]) + "\n"

    def _toc_output(self):
        """cdparanoia -Q's table, in the exact columns `track_durations()`
        regexes against."""
        lines = [
            "Table of contents (audio tracks only):",
            "track        length               begin        copy pre ch",
            "===========================================================",
        ]
        begin = LEADIN_FRAMES
        for t in self.spec["tracks"]:
            frames = t["seconds"] * FRAMES_PER_SEC
            lines.append(
                f"{t['num']:3d}. {frames:8d} [{self._mmssff(frames)}]  "
                f"{begin:8d} [{self._mmssff(begin)}]    no   no  2"
            )
            begin += frames
        lines.append("")
        lines.append("TOTAL  %d [%s]    (audio only)" % (begin - LEADIN_FRAMES,
                                                          self._mmssff(begin - LEADIN_FRAMES)))
        return "\n".join(lines) + "\n"

    @staticmethod
    def _mmssff(frames):
        secs, rem = divmod(int(frames), FRAMES_PER_SEC)
        mm, ss = divmod(secs, 60)
        return f"{mm:02d}:{ss:02d}.{rem:02d}"

    def _scrape(self):
        """Create abcde's scratch dir the way `-a cddb` does, and return the
        output lines it prints while doing it."""
        os.makedirs(self.ripdir, exist_ok=True)
        # Real abcde names this abcde.<random> and makes a fresh one per
        # scrape; mtime is what newest_abcde_tempdir() sorts on, so the names
        # only have to be distinct. The counter matters because two discs
        # rehearsed in one process would otherwise share one scratch dir and
        # the second would silently inherit the first's cddbread.
        self._scrapes += 1
        self.tempdir = os.path.join(
            self.ripdir, f"abcde.sim{os.getpid()}-{self._scrapes}")
        os.makedirs(self.tempdir, exist_ok=True)

        s = self.spec
        offsets = []
        begin = LEADIN_FRAMES
        for t in s["tracks"]:
            offsets.append(str(begin))
            begin += t["seconds"] * FRAMES_PER_SEC
        total_secs = (begin - LEADIN_FRAMES) // FRAMES_PER_SEC

        # cd-discid's format: discid ntracks off1..offN total_seconds. abcde
        # always writes this before attempting any lookup, which is why
        # read_toc_discid() can rely on it even on an unmatched disc.
        with open(os.path.join(self.tempdir, "cddbdiscid"), "w") as f:
            f.write(f"{s['discid']} {len(s['tracks'])} {' '.join(offsets)} {total_secs}\n")

        lines = [f"Getting CD track info... (simulated, {ENV_SPEC} set)"]
        if s["match"]:
            with open(os.path.join(self.tempdir, "cddbread.1"), "w") as f:
                f.write("# xmcd CD database file (simulated)\n")
                f.write(f"DISCID={s['discid']}\n")
                f.write(f"DTITLE={s['artist']} / {s['album']}\n")
                f.write("DYEAR=\n")
                f.write("DGENRE=\n")
                for t in s["tracks"]:
                    f.write(f"TTITLE{t['num'] - 1}={t['title']}\n")
            lines.append(f"Simulated match: {s['artist']} / {s['album']}")
        else:
            # No cddbread at all - exactly what an unmatched disc leaves
            # behind, and what drives the Unknown Artist/Album fallback.
            lines.append("Simulated lookup: no match found (cddb: none)")
        return lines

    def _rip(self, cmd):
        """`abcde -a read,encode,tag,move N` for one track."""
        track_num = None
        for arg in reversed(cmd):
            if re.fullmatch(r"\d+", arg):
                track_num = int(arg)
                break
        if track_num is None:
            return 1, ["[ERROR] simulated rip: no track number in command"]

        track = next((t for t in self.spec["tracks"] if t["num"] == track_num), None)
        if track is None:
            return 1, [f"[ERROR] simulated rip: disc has no track {track_num}"]

        speed = self.spec["read_speed"]
        lines = [
            f"Grabbing track {track_num}: {track['title']}...",
            "cdparanoia III release 10.2 (simulated)",
            f"  ... reading track {track_num} at {speed}x",
        ]
        if track["fails"]:
            lines += [
                f"[ERROR] scsi_read error on track {track_num} (simulated failure)",
                "[ERROR] Unable to extract track - giving up",
            ]
            return 1, lines

        s = self.spec
        # Mirror rip_session()'s own Unknown fallback: on an unmatched disc
        # it rips as Unknown Artist with a blank album, and album_dir_fn
        # applies the "(discid)" disambiguation itself.
        artist = s["artist"] if s["match"] else "Unknown Artist"
        album = s["album"] if s["match"] else ""
        album_dir = self.album_dir_fn(artist, album, s["discid"])
        os.makedirs(album_dir, exist_ok=True)

        safe_title = re.sub(r"[\'\"?]", "", track["title"].replace(":", "-"))
        path = os.path.join(album_dir, f"{track_num:02d}-{safe_title}.mp3")
        with open(path, "wb") as f:
            f.write(_silent_mp3(track["seconds"]))
        self._tag(path, artist, album or "Unknown Album", track["title"], track_num)
        self.ripped.append(track_num)

        lines += [
            f"  encoding track {track_num} (simulated silence, {track['seconds']}s)",
            f"  tagging and moving to {path}",
            f"Finished track {track_num}.",
        ]
        return 0, lines

    @staticmethod
    def _tag(path, artist, album, title, track_num):
        """Write real ID3 tags, so `history()` and live `artist=` retags have
        something genuine to read back. Best-effort: mutagen missing is not
        a reason to fail a rehearsal."""
        try:
            import mutagen.id3
            from mutagen.easyid3 import EasyID3
        except ImportError:
            return
        try:
            mutagen.id3.ID3().save(path)     # a bare file has no ID3 header yet
            tags = EasyID3(path)
            tags["artist"] = artist
            tags["album"] = album
            tags["title"] = title
            tags["tracknumber"] = str(track_num)
            tags.save()
        except Exception:
            return


def from_env(ripdir, album_dir_fn, sleep_fn=None):
    """Build a FakeDrive if `WTUL_SIMULATE_DRIVE` is set, else None.

    Raises SpecError if the var is set but unusable - the caller is expected
    to exit rather than quietly fall through to the real drive.
    """
    value = os.environ.get(ENV_SPEC, "").strip()
    if not value:
        return None
    return FakeDrive(load_spec(value), ripdir, album_dir_fn, sleep_fn=sleep_fn)
