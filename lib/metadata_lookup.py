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

When both come back empty, `musicbrainz_search_release()` is the third,
human-driven fallback: a free-text release search (no key needed) over
whatever the user types at the fix prompt - usually words read off the
physical cover, or #7's OCR candidate lines. It returns candidates for
the user to pick from, never an automatic answer.
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
MUSICBRAINZ_SEARCH_URL = "https://musicbrainz.org/ws/2/release/"
# MusicBrainz rejects generic User-Agents and rate-limits anonymous clients
# to ~1 req/s. Searches here are typed by a human at the fix prompt one at a
# time (never fired per-track in a loop the way AcoustID is), so no
# client-side throttle is needed - a human can't out-type 1 req/s.
MUSICBRAINZ_USER_AGENT = "wtul-rip/1.0 (+https://github.com/hf7y/wtul)"
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
    if not isinstance(data, dict):
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
    if not isinstance(data, dict) or data.get("status") != "ok":
        return []
    guesses = []
    for result in data.get("results", []) or []:
        if not isinstance(result, dict):
            continue
        score = result.get("score", 0)
        for rec in result.get("recordings", []) or []:
            if not isinstance(rec, dict):
                continue
            artists = rec.get("artists", []) or []
            artist = " & ".join(a.get("name", "") for a in artists
                                 if isinstance(a, dict)) or None
            title = rec.get("title")
            album = None
            for rg in rec.get("releasegroups", []) or []:
                if isinstance(rg, dict) and rg.get("title"):
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
    if not isinstance(data, dict):
        return None
    results = data.get("results", []) or []
    top = results[0] if results else None
    return top.get("title") if isinstance(top, dict) else None


def musicbrainz_search_release(query, base_url=MUSICBRAINZ_SEARCH_URL, timeout=15, limit=5):
    """Free-text release search against MusicBrainz - the third identification
    fallback (after AcoustID and Discogs) for a disc neither service could
    match, and the only one that needs no key or token at all. The query is
    whatever the user typed at the fix prompt - typically words read off the
    physical cover (or #7's OCR candidate lines) - so it's a plain full-text
    search, not a fielded one.

    Returns up to `limit` dicts {"artist", "album", "year", "score"},
    best-scored first, de-duplicated on (artist, album) since one release
    commonly appears once per pressing/country; [] on no match or any
    network/shape error - same never-raise discipline as the Discogs client,
    the manual prompt is always the real fallback."""
    if not query or not query.strip():
        return []
    # Over-fetch so pressing-duplicates still leave `limit` distinct rows.
    params = urllib.parse.urlencode({"query": query.strip(), "fmt": "json",
                                     "limit": max(limit * 2, 10)})
    req = urllib.request.Request(f"{base_url}?{params}",
                                  headers={"User-Agent": MUSICBRAINZ_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    releases = data.get("releases", []) or []
    if not isinstance(releases, list):
        return []
    out, seen = [], set()
    for rel in releases:
        if not isinstance(rel, dict):
            continue
        title = rel.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        credits = rel.get("artist-credit") or []
        if not isinstance(credits, list):
            continue
        names = [c.get("name").strip() for c in credits
                 if isinstance(c, dict) and isinstance(c.get("name"), str)
                 and c.get("name").strip()]
        if not names:
            continue
        artist = " & ".join(names)
        date = rel.get("date")
        year = date[:4] if isinstance(date, str) and len(date) >= 4 \
            and date[:4].isdigit() else None
        key = (artist.lower(), title.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        score = rel.get("score")
        out.append({"artist": artist, "album": title.strip(), "year": year,
                    "score": score if isinstance(score, int) else None})
        if len(out) >= limit:
            break
    return out


def discogs_genre_year(token, artist, album=None, base_url=DISCOGS_SEARCH_URL, timeout=15):
    """Best-effort (genre, year) for a label, not disc identification -
    genre/year aren't tagged by abcde's CDDB/MusicBrainz scrape at all, so
    this is the only source for them. Searches by artist+release_title
    when an album is already known (far more specific than artist alone -
    e.g. "belong"+"October Language" only matches that release, not
    whichever of an artist's releases Discogs ranks first), falling back
    to artist-only if that finds nothing (matches
    `discogs_search_by_artist`'s existing fallback shape) - **except for a
    self-titled album** (album == artist, common for a debut), where the
    artist-only fallback is skipped entirely: it's no more specific than
    the release_title search that already failed, but still returns a
    top result with false confidence - real collision hit live 2026-07-24
    (an obscure local "Morgan Lane" self-titled release matched an
    unrelated same-named artist's 1971 country record). Returns
    (None, None) on no match/error - a blank label field beats a
    confidently-wrong or generic one, so callers should leave the field
    blank (for a human to write in by hand) rather than substitute a
    placeholder."""
    self_titled = bool(album) and album.strip().lower() == artist.strip().lower()
    searches = []
    if album:
        searches.append({"artist": artist, "release_title": album, "type": "release", "token": token})
    if not self_titled:
        searches.append({"artist": artist, "type": "release", "token": token})
    for params in searches:
        req = urllib.request.Request(f"{base_url}?{urllib.parse.urlencode(params)}",
                                      headers={"User-Agent": "wtul-rip/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        results = data.get("results", []) or []
        if not results:
            continue
        top = results[0]
        if not isinstance(top, dict):
            continue
        genre = ", ".join((top.get("style") or top.get("genre") or [])[:2]) or None
        year = top.get("year") or None
        if genre or year:
            return genre, year
    return None, None


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
