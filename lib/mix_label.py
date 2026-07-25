"""Assembles the ordered per-track label content for a dated mix folder
(~/Music/mixes/YYYY-MM-DD/), for printing via label_render.render_label().
Not disc identification - reads whatever's already tagged (from the
CDDB/MusicBrainz scrape at rip time) and only reaches out to Discogs for
genre/year, which nothing upstream tags at all.
"""
import glob
import os
import time

DISCOGS_MIN_INTERVAL = 1.1  # matches Discogs's documented ~60/min authenticated rate limit


def _read_tags(path):
    from mutagen.easyid3 import EasyID3
    from mutagen.mp3 import MP3
    tags = EasyID3(path)
    audio = MP3(path)
    return {
        "title": (tags.get("title") or [None])[0],
        "artist": (tags.get("artist") or [None])[0],
        "album": (tags.get("album") or [None])[0],
        "duration": int(audio.info.length),
    }


def _format_duration(seconds):
    return f"{seconds // 60}:{seconds % 60:02d}"


def collect_mix_tracks(mix_dir, discogs_token=None, genre_year_lookup=None,
                        min_interval=DISCOGS_MIN_INTERVAL, sleep_fn=time.sleep, clock=time.monotonic):
    """Returns a list of track dicts (title/artist/album/duration/genre/
    year), one per mp3 under mix_dir, sorted by (album folder, track
    number prefix). genre_year_lookup defaults to
    metadata_lookup.discogs_genre_year but is overridable for tests -
    called once per unique (artist, album) pair, not once per track, to
    avoid hammering Discogs with duplicate lookups for a multi-track
    album. Throttled to min_interval between those calls (same pattern
    as metadata_lookup.resolve_disc_metadata's AcoustID throttle) - a
    real mix of 8+ albums fired requests fast enough to get silently
    rate-limited by Discogs mid-batch, 2026-07-24 (every lookup after
    the first few came back empty even though a single isolated lookup
    for the same artist/album worked fine moments later)."""
    if genre_year_lookup is None:
        import metadata_lookup
        def genre_year_lookup(artist, album):
            return metadata_lookup.discogs_genre_year(discogs_token, artist, album=album)

    paths = sorted(glob.glob(os.path.join(mix_dir, "*", "*", "*.mp3")))
    genre_year_cache = {}
    tracks = []
    last_call = None
    for path in paths:
        tags = _read_tags(path)
        artist = tags["artist"] or "Unknown Artist"
        album = tags["album"] or "Unknown Album"
        key = (artist, album)
        if key not in genre_year_cache:
            if last_call is not None:
                wait = min_interval - (clock() - last_call)
                if wait > 0:
                    sleep_fn(wait)
            genre_year_cache[key] = genre_year_lookup(artist, album)
            last_call = clock()
        genre, year = genre_year_cache[key]
        tracks.append({
            "title": tags["title"] or os.path.basename(path),
            "artist": artist,
            "album": album,
            "duration": tags["duration"],
            "genre": genre,
            "year": year,
        })
    return tracks


def format_tracklist_lines(tracks):
    """One label line per track: "Title — Artist (Album, Year) [Genre] m:ss".
    Year/genre are omitted (not printed as blank/placeholder text) when
    not found - a missing field disappears rather than showing "?" or
    "None", leaving that much less for a human to have to mentally filter
    on the printed label."""
    lines = []
    for t in tracks:
        year_part = f", {t['year']}" if t["year"] else ""
        genre_part = f" [{t['genre']}]" if t["genre"] else ""
        dur = _format_duration(t["duration"])
        lines.append(f"{t['title']} — {t['artist']} ({t['album']}{year_part}){genre_part} {dur}")
    return lines
