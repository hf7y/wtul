"""Spinitron play-history matching for rip prioritization (ROADMAP #1).

The idea: when a disc goes in, tracks that the station has *already* played
on air should rip first, so they're available again soonest. This module is
the reusable, hardware-free core of that:

  * a read-only Spinitron source for recent spins - `fetch_recent_spins_public`
    scrapes WTUL's public Spinitron page (no key needed) and is the one
    actually wired into `rip_session()`; `fetch_recent_spins` (the official
    `/api/spins` client) is kept for later in case station-managed API access
    ever materializes, but is unused for now, and
  * the fuzzy artist+title matching + queue reorder (`matched_track_numbers`,
    `reorder_queue`) that turns "these spins were played" into "rip these
    track numbers first" - shared by both sources.

The matching/reorder half is pure and unit-tested. `rip_session()` in
`bin/wtul-rip` calls `fetch_recent_spins_public()` then
`reorder_queue(queue, matched_track_numbers(...))` right after the queue is
built, mirroring apply_live_input's reorder. No API key exists or is needed
for this path - see `.scheduler/QUESTIONS.md` (2026-07-20) for why: the station's
`/api/spins` requires an API key issued by station management, which isn't
available; spinitron.com/WTUL/ is a public page with no login that shows
what's airing right now station-wide, which is enough to know what's
"already played on air" recently. A network/scrape failure at rip time is
caught and logged, never aborts the rip.
"""
import difflib
import html
import json
import re
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://spinitron.com/api"
DEFAULT_PUBLIC_URL = "https://spinitron.com/WTUL/"
# Public page embeds each spin as a JSON blob in a `data-spin="{...}"`
# attribute (HTML-entity-escaped) on each <tr class="spin-item">, e.g.
# data-spin="{&quot;i&quot;:...,&quot;a&quot;:&quot;Artist&quot;,
# &quot;s&quot;:&quot;Song&quot;,&quot;r&quot;:&quot;Release&quot;}" - far
# simpler and more stable than parsing the surrounding markup.
_SPIN_ATTR_RE = re.compile(r'data-spin="([^"]*)"')
# How closely a scraped track has to match a spin to count as "played".
# 0.82 tolerates case/punctuation/whitespace drift (see _normalize and
# _compare_key) without matching merely-similar different songs. No longer a
# bare guess: `tests/test_spin_match_corpus.py` pins it against a labelled
# corpus of real-world credit-style variants (positives that must match,
# negatives that must not), and `scripts/spin-match-eval.py` sweeps the
# threshold over that corpus so moving it is a measured decision. A real rip's
# own spins are still the last word - the corpus is hand-built, not observed.
DEFAULT_THRESHOLD = 0.82

# Trailing guest-credit clause, unbracketed: Spinitron DJs type
# "Kendrick Lamar feat. Zacari" where the disc's own metadata says just
# "Kendrick Lamar". The bracketed form "(feat. Zacari)" is already handled by
# _normalize's qualifier strip; this catches the bare one. Deliberately does
# NOT include "with" or "&" - "Big Freedia & Boyfriend" is a different credit
# from "Big Freedia", and "Sleeping With ..." is an ordinary title.
_FEAT_RE = re.compile(r"\b(?:feat|ft|featuring)\b.*$")
# Tokens whose presence/absence is pure credit-style drift, not identity:
# "The Beatles"/"Beatles", "Rolling Stones, The", "Tank & The Bangas"/"Tank
# and the Bangas". Dropped only for the second, looser comparison below.
_NOISE_TOKENS = frozenset(("the", "and"))
# Number words this treats as their digits, so "Track One"/"Track 1" are the
# same item and "Track One"/"Track Two" are not. Small on purpose: past
# twenty, spelled-out numbers in a title are vanishingly rare and each entry
# is another way to be wrong.
_NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20",
}
# What two strings score once their numbering disagrees. Not 0.0: the eval
# report is more readable when a capped pair still shows it was otherwise
# similar, which is exactly the case worth eyeballing.
NUMBER_MISMATCH_CAP = 0.5


def _normalize(s):
    """Lowercase, drop bracketed qualifiers like "(Radio Edit)"/"[Live]", strip
    punctuation to spaces, and collapse whitespace - so "Do It Right Now
    (Instrumental)" and "do it right now" compare as near-identical."""
    s = (s or "").lower()
    s = re.sub(r"[\(\[].*?[\)\]]", " ", s)   # remove (…) / […] qualifiers
    s = re.sub(r"[^a-z0-9]+", " ", s)        # punctuation -> space
    return re.sub(r"\s+", " ", s).strip()


def _compare_key(s):
    """_normalize, then drop a trailing guest credit and the article/conjunction
    tokens that two catalogues spell differently for the same act. Returns ""
    for a string that is nothing but noise ("The"), which is why callers take
    the max against the plain normalized ratio rather than using this alone -
    two different acts both keyed to "" would otherwise compare as identical."""
    n = _normalize(s)
    n = _FEAT_RE.sub("", n).strip()
    return " ".join(t for t in n.split() if t not in _NOISE_TOKENS)


def _numbers(s):
    """The sequence of numbers a string carries, digits and words alike.

    "Symphony No. 2" -> ["2"]; "Simulated Track Two" -> ["2"]; "Alright" -> [].
    Roman numerals are deliberately not handled - "Part III" is rare enough
    in this station's catalogue that guessing at it would add more wrong
    answers than it removes.
    """
    return [_NUMBER_WORDS.get(t, t) for t in _normalize(s).split()
            if t.isdigit() or t in _NUMBER_WORDS]


def _similarity(a, b):
    """Best of two ratios: the strict normalized one, and the looser
    credit-style-insensitive one. Taking the max can only ever raise a score,
    which is the right direction - every miss this was built to fix is a false
    negative (the disc and the spin naming the same record differently), and
    the negative half of the corpus is what keeps the loosening honest."""
    strict = difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()
    ka, kb = _compare_key(a), _compare_key(b)
    score = strict
    if ka and kb:
        score = max(strict, difflib.SequenceMatcher(None, ka, kb).ratio())
    # Numbering is the one difference a character-ratio systematically
    # under-weights: "Symphony No. 1"/"No. 2" scores 0.923 and "Simulated
    # Track One"/"Track Two" 0.895, both over the line, because one short
    # token differs inside a long shared string. Caught by running the demo
    # rehearsal (2026-07-27), which reported all three tracks as already
    # played from spins naming one. A station that plays this much classical
    # and experimental music hits Symphony No. N and Untitled N constantly,
    # so a disagreement about which number is a disagreement about which
    # piece - not fuzz to absorb.
    if _numbers(a) != _numbers(b):
        return min(score, NUMBER_MISMATCH_CAP)
    return score


def spin_matches_track(spin, track_artist, track_title, threshold=DEFAULT_THRESHOLD):
    """True if a Spinitron spin (dict with 'artist' and 'song' keys, as
    /api/spins returns) fuzzy-matches this track's artist+title.

    Both artist and title must clear the threshold: a station plays many
    songs by an artist whose CD this is, so artist alone would over-match and
    front-load the whole disc.
    """
    s_artist = spin.get("artist", "")
    s_title = spin.get("song", "")
    return (_similarity(s_artist, track_artist) >= threshold
            and _similarity(s_title, track_title) >= threshold)


def matched_track_numbers(titles, disc_artist, spins, threshold=DEFAULT_THRESHOLD,
                          per_track_artist=None):
    """Return the set of track numbers whose artist+title match some spin.

    titles: {track_num: title}. disc_artist is the album-level artist used for
    every track unless per_track_artist ({track_num: artist}) overrides it
    (compilations / various-artist discs, where each track's real artist
    differs from the album artist).
    """
    per_track_artist = per_track_artist or {}
    matched = set()
    for num, title in titles.items():
        artist = per_track_artist.get(num, disc_artist)
        if any(spin_matches_track(sp, artist, title, threshold) for sp in spins):
            matched.add(num)
    return matched


def reorder_queue(queue, matched):
    """Move matched track numbers to the front of queue, preserving the
    relative order of both the matched and unmatched groups. Pure - returns a
    new list, mirroring apply_live_input's `front + rest` reorder so behavior
    is identical to typing the same priority by hand."""
    front = [n for n in queue if n in matched]
    rest = [n for n in queue if n not in matched]
    return front + rest


def fetch_recent_spins(api_key, count=200, base_url=DEFAULT_BASE_URL, timeout=15):
    """GET /api/spins for the station this key belongs to (Spinitron scopes
    the key to one station, so no station id is needed in the query). Returns
    a list of spin dicts. Read-only; needs the user's API key to run.

    Kept deliberately thin - just enough to feed matched_track_numbers - so
    the tested matching logic above is what carries the real complexity.
    """
    params = urllib.parse.urlencode({"count": count})
    url = f"{base_url}/spins?{params}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    # Spinitron wraps the list under "items"; tolerate a bare list too.
    if isinstance(data, dict):
        return data.get("items", [])
    return data


def fetch_recent_spins_public(url=DEFAULT_PUBLIC_URL, timeout=15):
    """Scrape WTUL's public Spinitron page for recent spins - no API key
    needed. Returns a list of {"artist": ..., "song": ...} dicts, same shape
    `fetch_recent_spins` returns, so both feed `matched_track_numbers`
    identically.

    The page only shows spins for whatever show is currently on air (not a
    rolling station-wide history), so coverage is thinner right after a show
    starts - acceptable since the goal is just "was this played recently",
    not a complete log.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    spins = []
    for raw in _SPIN_ATTR_RE.findall(page):
        try:
            spin = json.loads(html.unescape(raw))
        except ValueError:
            continue
        if not isinstance(spin, dict):
            # A page layout tweak could embed a non-object data-spin value
            # (still valid JSON, so the except above wouldn't catch it) -
            # spin.get() would raise AttributeError, which isn't in the
            # caller's caught-exceptions tuple in bin/wtul-rip and would
            # crash rip_session entirely over what's meant to be a
            # best-effort, informational-only lookup.
            continue
        spins.append({"artist": spin.get("a", ""), "song": spin.get("s", "")})
    return spins
