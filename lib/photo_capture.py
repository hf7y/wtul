"""Phone photo capture for album art (ROADMAP #4) - a small Apps Script
web app (`gas/photo-capture.gs.js`) serves an upload page keyed by a
short-lived pairing code, the phone snaps a photo there, and this module
polls the same endpoint from the ripping machine to pull the image back
down and embed it as ID3 cover art on the just-ripped tracks.

Deliberately its own bespoke doGet/doPost shape rather than the bug/
feature/resolve contract documented in the scheduler's `INTAKE.md` (which
`vkv-inventory`/`chezz` share) - that contract models status-tracked
reports (open/resolved, a note field, reclassification) which don't map
onto "one photo, tied to one disc, consumed once." Reusing its verb names
for a shape that doesn't fit would be surface-level consistency, not real
consistency. Same underlying gotcha still applies though (see
`check_photo`'s docstring): never trust a POST's own response against an
Apps-Script-backed endpoint, always re-GET to confirm.

Network and subprocess calls are the only untested-by-real-hardware edges
here - no CD drive or phone needed to exercise the polling/download/embed
logic itself (mocked in tests/test_photo_capture.py), but the actual
"open this URL on a phone and take a photo" flow has never been run for
real. See ROADMAP.md #4 and .claude/QUESTIONS.md for the open question
this still needs a human answer on (fold into the existing GAS project
backing the sheet in ROADMAP.md #4, or deploy standalone as built here).
"""
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


def new_pairing_code():
    """A short, URL-safe code the phone's upload page is keyed by - not a
    secret, just enough entropy that two pairing codes issued around the
    same time can't collide (8 base32-ish chars, ~40 bits)."""
    return secrets.token_hex(4)


def pairing_url(exec_url, pairing_code, disc_id):
    """The URL to show/print/QR-code at rip time - opening it on a phone
    loads the GAS-hosted upload form (see `gas/photo-capture.gs.js`'s
    doGet), pre-filled with both values so the phone never has to type
    either one in."""
    query = urllib.parse.urlencode({"pairing_code": pairing_code, "disc_id": disc_id})
    return f"{exec_url}?{query}"


def check_photo(exec_url, pairing_code, timeout=15):
    """GET ?scope=photo&pairing_code=... once. Returns the endpoint's
    {found, url, disc_id, created_at} dict, or None on any network/parse
    failure - never raises. A single check, not a loop; `wait_for_photo`
    below is the polling version. Only the GET side needs the
    never-trust-the-response caution documented in `INTAKE.md` for
    *writes* against Apps-Script-backed endpoints - reads are a plain
    JSON response, not a redirect-chain'd POST, so this one's safe to
    trust directly."""
    query = urllib.parse.urlencode({"scope": "photo", "pairing_code": pairing_code})
    try:
        req = urllib.request.Request(f"{exec_url}?{query}")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def wait_for_photo(exec_url, pairing_code, timeout=180, interval=5, sleep=time.sleep):
    """Poll `check_photo` every `interval` seconds until it reports
    `found`, or give up after `timeout` seconds total. Returns the found
    dict, or None on timeout/failure. `sleep` is injectable so tests don't
    actually wait."""
    deadline = time.monotonic() + timeout
    while True:
        result = check_photo(exec_url, pairing_code, timeout=min(interval, timeout))
        if result and result.get("found"):
            return result
        if time.monotonic() >= deadline:
            return None
        sleep(interval)


def download_image(url, dest_path, timeout=30):
    """Fetch the uploaded photo (a public/anyone-with-link Drive URL, per
    `gas/photo-capture.gs.js`) to `dest_path`. Returns True on success,
    False on any failure - never raises, same non-fatal discipline as the
    rest of this module."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError, ValueError):
        return False
    try:
        with open(dest_path, "wb") as f:
            f.write(data)
    except OSError:
        return False
    return True


def embed_album_art(image_path, mp3_paths, run=subprocess.run):
    """Embed `image_path` as front-cover art on each path in `mp3_paths`
    via eyeD3 (already a system dependency here, see abcde.conf) - chosen
    over re-invoking abcde's EMBEDALBUMART action (ROADMAP.md #4's other
    suggested route) because it's a single, narrow, easily-mocked command
    per file rather than re-triggering abcde's whole pipeline/state
    machine against an album directory it thinks is already finished.
    Returns (ok_paths, failed_paths) - a partial failure (one bad mp3)
    doesn't lose the rest. `run` is injectable for tests."""
    ok, failed = [], []
    for path in mp3_paths:
        try:
            result = run(
                ["eyeD3", "--add-image", f"{image_path}:FRONT_COVER", path],
                capture_output=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            failed.append(path)
            continue
        (ok if result.returncode == 0 else failed).append(path)
    return ok, failed


def associate_photo(exec_url, pairing_code, dest_dir, mp3_paths, timeout=180, interval=5, sleep=time.sleep):
    """One-shot orchestration for a single pending pairing: wait for the
    phone's upload, download it, embed it on `mp3_paths`. Returns a
    summary dict - never raises, so a photo that never arrives (phone
    never used, network down, whatever) can't break anything that calls
    this. `dest_dir` is where the downloaded image is saved (alongside
    the ripped album), not a temp path, so it survives as the album's
    cover.jpg even if embedding fails partway."""
    found = wait_for_photo(exec_url, pairing_code, timeout=timeout, interval=interval, sleep=sleep)
    if not found:
        return {"status": "no_photo", "pairing_code": pairing_code}
    image_path = os.path.join(dest_dir, "cover.jpg")
    if not download_image(found["url"], image_path):
        return {"status": "download_failed", "pairing_code": pairing_code}
    ok, failed = embed_album_art(image_path, mp3_paths)
    return {
        "status": "embedded" if not failed else "partial",
        "pairing_code": pairing_code,
        "image_path": image_path,
        "embedded": ok,
        "failed": failed,
    }
