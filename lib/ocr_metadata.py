"""OCR on the phone-photo cover-art layer (ROADMAP #7) - a text-source
fallback for discs where AcoustID/Discogs (ROADMAP #2) found nothing, but
a cover photo exists (ROADMAP #4's `photo_capture.associate_photo`
already saves one to `<album_dir>/cover.jpg`).

Deliberately does NOT try to auto-classify OCR'd text into artist/album/
tracklist fields - stylized cover fonts make that unreliable, and
ROADMAP.md #7 itself calls for "present to the user as a suggestion they
confirm/edit rather than trusting it blindly" (same discipline
`metadata_lookup.py` already applies to AcoustID/Discogs guesses). So
this module only gets OCR'd text to clean, readable candidate lines;
`fix_by_discid` in `bin/wtul-rip` shows those lines to the user alongside
the existing manual artist/album prompt, never auto-fills from them.

Calls the `tesseract` CLI directly via subprocess (same shape as
`metadata_lookup.fingerprint_file`'s `fpcalc` call) rather than depending
on the `pytesseract` wrapper package, which isn't installable in this
environment without overriding the OS's externally-managed-Python guard.

The `tesseract-ocr` apt package needs root to install the normal way, and
this machine has no sudo password in an unattended session. It can still
be had without root, though: `apt-get download` fetches the .deb without
installing it, and `dpkg-deb -x` extracts it like any other archive -
`scripts/install-tesseract-local.sh` does exactly that, into
`~/.local/opt/tesseract-user`, self-contained and reversible (`rm -rf` on
that one directory undoes it). `find_tesseract()` below checks a real
`tesseract` on `PATH` first (the normal apt-installed case, e.g. once a
future session has sudo) and falls back to that local install directory
- the local build ships its `tessdata` under a path other than the
default, so it needs `TESSDATA_PREFIX` set explicitly, which `find_tesseract()`
returns alongside the binary path for the caller to pass through as the
subprocess `env`. Every function still degrades to None/[] rather than
raising when no tesseract is available at all, same discipline
`metadata_lookup.py` uses for `fpcalc`.
"""
import glob
import os
import shutil
import subprocess

COVER_FILENAMES = ("cover.jpg", "cover.jpeg", "cover.png")
# OCR noise line filter: cover art frequently OCRs single stray
# characters/punctuation from logos, borders, or barcode text - not
# useful as a candidate artist/album line.
MIN_LINE_LENGTH = 3
MAX_CANDIDATE_LINES = 15

LOCAL_INSTALL_DIR = os.path.expanduser("~/.local/opt/tesseract-user")
LOCAL_TESSERACT_BIN = os.path.join(LOCAL_INSTALL_DIR, "usr/bin/tesseract")


def find_tesseract():
    """Locate a usable `tesseract` binary: a real one on `PATH` first (the
    normal apt-installed case), else the sudo-less local install under
    `LOCAL_INSTALL_DIR` (see `scripts/install-tesseract-local.sh`), else
    None. Returns `(bin_path, env_overrides)` - `env_overrides` is None
    for the `PATH` case (default environment already works) or a dict
    with `TESSDATA_PREFIX` set for the local-install case (its tessdata
    lives outside tesseract's compiled-in default search path)."""
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path, None
    if os.path.isfile(LOCAL_TESSERACT_BIN):
        tessdata_dirs = glob.glob(
            os.path.join(LOCAL_INSTALL_DIR, "usr/share/tesseract-ocr/*/tessdata")
        )
        if tessdata_dirs:
            env = dict(os.environ, TESSDATA_PREFIX=tessdata_dirs[0])
            return LOCAL_TESSERACT_BIN, env
    return None, None


def find_cover_image(album_dir):
    """First existing cover image in `album_dir` matching the filename
    `photo_capture.associate_photo` saves to, or None if there isn't one
    (no photo was ever captured for this disc, or #4's capture step never
    ran) - case-insensitive since filesystems vary."""
    if not os.path.isdir(album_dir):
        return None
    lower_to_real = {name.lower(): name for name in os.listdir(album_dir)}
    for candidate in COVER_FILENAMES:
        if candidate in lower_to_real:
            return os.path.join(album_dir, lower_to_real[candidate])
    return None


def ocr_image(image_path, tesseract_bin="tesseract", timeout=30, env=None):
    """Run `tesseract` on an image file, return the raw extracted text, or
    None if the binary is missing, times out, fails, or the image doesn't
    exist - never raises, since this is a best-effort fallback that must
    not abort `fix_by_discid`'s manual-entry path either way. `stdout` as
    the second CLI arg tells tesseract to print text to stdout rather than
    writing a `<arg>.txt` file next to the image. `env` is passed straight
    to `subprocess.run` - `None` means inherit the current process
    environment as normal; `find_tesseract()`'s local-install fallback
    needs `TESSDATA_PREFIX` set, so callers that used it pass that dict
    through here."""
    if not os.path.isfile(image_path):
        return None
    try:
        proc = subprocess.run(
            [tesseract_bin, image_path, "stdout"],
            capture_output=True, timeout=timeout, text=True, env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def clean_ocr_lines(text, min_length=MIN_LINE_LENGTH, max_lines=MAX_CANDIDATE_LINES):
    """Turn raw OCR text into a short list of plausible candidate lines:
    strips whitespace, drops blank/too-short noise lines, collapses
    consecutive duplicates (tesseract often repeats a line it OCR'd twice
    off overlapping cover art regions), and caps the total so a busy cover
    doesn't dump dozens of lines on the user. Returns [] for None/empty
    input - never raises."""
    if not text:
        return []
    lines = []
    prev = None
    for raw in text.splitlines():
        line = raw.strip()
        if len(line) < min_length:
            continue
        if line == prev:
            continue
        lines.append(line)
        prev = line
        if len(lines) >= max_lines:
            break
    return lines


def ocr_cover_candidates(album_dir, tesseract_bin=None, timeout=30):
    """Best-effort candidate text lines from `album_dir`'s cover photo, for
    `fix_by_discid` to show the user as an unverified suggestion. Returns
    [] if there's no cover image, tesseract is missing/fails, or OCR found
    nothing usable - the caller's existing manual prompt is the real
    fallback regardless.

    `tesseract_bin=None` (the default) auto-resolves via `find_tesseract()`
    - `PATH` first, then the sudo-less local install. Pass an explicit
    `tesseract_bin` (as the tests do) to bypass resolution entirely."""
    image_path = find_cover_image(album_dir)
    if not image_path:
        return []
    env = None
    if tesseract_bin is None:
        tesseract_bin, env = find_tesseract()
        if tesseract_bin is None:
            return []
    text = ocr_image(image_path, tesseract_bin=tesseract_bin, timeout=timeout, env=env)
    return clean_ocr_lines(text)
