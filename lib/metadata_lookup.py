"""AcoustID (primary) + Discogs (fallback) metadata lookup for
already-ripped unidentified discs (ROADMAP #2).

`fix_by_discid()` in `bin/wtul-rip` calls `resolve_disc_metadata(...)`
before falling through to its existing manual artist/album prompt, and
uses whatever comes back as a *suggestion* to confirm/edit - never
trusted blindly, since fuzzy audio/catalog matching can be wrong.

AcoustID identifies from the actual ripped audio (fingerprinted via
`fpcalc`/Chromaprint), which is why it's primary: these discs already
failed CDDB/MusicBrainz TOC lookup, so matching on real audio content has
better odds than another metadata-only lookup. Discogs is catalog search
by artist name only (no audio fingerprinting), so it only kicks in when
AcoustID found an artist but not a confident album - it can't identify
anything AcoustID found nothing for. Missing key/token or fpcalc, or any
network/API failure, degrades silently to (None, None) at every stage -
the manual prompt is always the real fallback.
"""
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"
DISCOGS_SEARCH_URL = "https://api.discogs.com/database/search"
# AcoustID's own 0-1 match confidence - a per-track guess below this isn't
# trusted enough to count toward the album majority vote.
DEFAULT_SCORE_THRESHOLD = 0.5
# AcoustID's documented client rate limit is 3 requests/second; resolving a
# disc fires one lookup per track in a loop, so a normal 10-14 track album
# would burst well past that without spacing requests out.
ACOUSTID_MIN_INTERVAL = 0.35


def fingerprint_file(path, fpcalc_bin="fpcalc", timeout=30):
    """Run fpcalc on an audio file. Returns (duration_seconds, fingerprint),
    or (None, None) if fpcalc is missing, times out, or fails - never
    raises, since this runs per-track in a loop that must not abort on one
    bad file."""
    try:
        proc = subprocess.run([fpcalc_bin, "-json", path],
                               capture_output=True, timeout=timeout, text=True)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None, None
    if proc.returncode != 0:
        return None, None
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return None, None
    return data.get("duration"), data.get("fingerprint")


def acoustid_lookup(api_key, duration, fingerprint, base_url=ACOUSTID_URL, timeout=15):
    """Query AcoustID for one fingerprint. Returns a list of
    {"score", "artist", "title", "album"} guesses, best score first, or []
    on no match/error - read-only, never raises."""
    params = urllib.parse.urlencode({
        "client": api_key,
        "duration": int(duration),
        "fingerprint": fingerprint,
        "meta": "recordings+releasegroups",
        "format": "json",
    })
    req = urllib.request.Request(f"{base_url}?{params}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return []
    if data.get("status") != "ok":
        return []
    guesses = []
    for result in data.get("results", []) or []:
        score = result.get("score", 0)
        for rec in result.get("recordings", []) or []:
            artists = rec.get("artists", []) or []
            artist = " & ".join(a.get("name", "") for a in artists) or None
            title = rec.get("title")
            album = None
            for rg in rec.get("releasegroups", []) or []:
                if rg.get("title"):
                    album = rg["title"]
                    break
            if artist or title:
                guesses.append({"score": score, "artist": artist,
                                 "title": title, "album": album})
    guesses.sort(key=lambda g: g["score"], reverse=True)
    return guesses


def best_album_guess(track_guesses, threshold=DEFAULT_SCORE_THRESHOLD):
    """track_guesses: one best-guess dict (or None) per fingerprinted
    track. Returns (artist, album, score) for whichever album name is
    most common among tracks that cleared `threshold` - a majority vote
    across tracks is more reliable than trusting any single track, since
    one mismatched recording (a cover, a compilation entry) shouldn't
    decide the whole disc. Returns (None, None, 0) if nothing qualifies."""
    candidates = [g for g in track_guesses if g and g.get("album") and g["score"] >= threshold]
    if not candidates:
        return None, None, 0
    top_album, _ = Counter(g["album"] for g in candidates).most_common(1)[0]
    matching = [g for g in candidates if g["album"] == top_album]
    best = max(matching, key=lambda g: g["score"])
    return best.get("artist"), top_album, best["score"]


def best_artist_guess(track_guesses, threshold=DEFAULT_SCORE_THRESHOLD):
    """Same majority-vote idea as `best_album_guess`, but over artist name
    alone - needed because a disc can have an artist consensus even when
    no single recording had a releasegroup/album title attached (a common
    AcoustID gap), which `best_album_guess` alone would miss entirely
    since it only counts candidates that already have an album."""
    candidates = [g for g in track_guesses if g and g.get("artist") and g["score"] >= threshold]
    if not candidates:
        return None
    top_artist, _ = Counter(g["artist"] for g in candidates).most_common(1)[0]
    return top_artist


def discogs_search_by_artist(token, artist, base_url=DISCOGS_SEARCH_URL, timeout=15):
    """Fallback when AcoustID found an artist but not a confident album:
    search Discogs's catalog by artist name and return the top result's
    release title, or None on no match/error. A first guess, not
    duration-matched against the disc's actual tracklist - good enough
    for a suggestion the user still confirms, not authoritative."""
    params = urllib.parse.urlencode({"artist": artist, "type": "release", "token": token})
    req = urllib.request.Request(f"{base_url}?{params}",
                                  headers={"User-Agent": "wtul-rip/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    results = data.get("results", []) or []
    return results[0].get("title") if results else None


def resolve_disc_metadata(track_paths, acoustid_key=None, discogs_token=None,
                           fpcalc_bin="fpcalc", min_interval=ACOUSTID_MIN_INTERVAL,
                           sleep_fn=time.sleep, clock=time.monotonic):
    """Best-effort (artist, album) suggestion for an unidentified disc's
    already-ripped tracks. AcoustID first (fingerprints real audio); if
    that finds an artist but no confident album, Discogs searches that
    artist's catalog as a fallback. No key/binary, or total lookup
    failure, returns (None, None) - `fix_by_discid`'s manual prompt is
    the ultimate fallback either way, so this never raises.

    AcoustID lookups are throttled to `min_interval` seconds apart (its
    documented client limit is 3/s) since this fires one request per
    track - a normal album's tracklist would otherwise burst well past
    that. `sleep_fn`/`clock` are injectable so tests don't actually wait.
    """
    if not acoustid_key:
        return None, None
    track_guesses = []
    last_call = None
    for path in track_paths:
        duration, fingerprint = fingerprint_file(path, fpcalc_bin=fpcalc_bin)
        if duration is None:
            track_guesses.append(None)
            continue
        if last_call is not None:
            elapsed = clock() - last_call
            if elapsed < min_interval:
                sleep_fn(min_interval - elapsed)
        guesses = acoustid_lookup(acoustid_key, duration, fingerprint)
        last_call = clock()
        track_guesses.append(guesses[0] if guesses else None)
    artist, album, _score = best_album_guess(track_guesses)
    if not artist:
        artist = best_artist_guess(track_guesses)
    if artist and not album and discogs_token:
        album = discogs_search_by_artist(discogs_token, artist)
    return artist, album
