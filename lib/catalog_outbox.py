"""A durable outbox for catalog rows that failed to reach the sheet
(FOCUS.md #8).

`catalog_writeback.write_row()` already knows the difference between "the
POST landed" and "the POST's response lied" - it re-GETs to confirm. What
it could not do was survive a `False`: `rip_session()` printed one line
("add it to the sheet by hand if it matters") and moved on. On show night
that line scrolls off the top of the terminal behind the next disc's
tracklist, and the row is then gone - there is nothing on disk that
remembers a finished rip never got catalogued. That is exactly the
"trust it without hand-checking" half of the stability milestone.

So a failed row goes here instead: a plain JSON list beside the mix
folder, retried at the next `wtul-rip` startup, on demand via the
`catalog` command, and surfaced by `doctor`.

Two rules this module exists to enforce, both about the same asymmetry -
**a duplicate row in the station's live rotation catalog has to be
deleted by hand (#8 built no delete endpoint), a dropped row only needs
re-queueing**:

1. `queue()` de-duplicates on ARTIST+ALBUM+DATE, so re-ripping the same
   disc twice on a bad-network night queues one row, not five.
2. `flush()` re-confirms *before* it re-POSTs. A row can be queued and
   still be in the sheet: `write_row` returns False when the POST landed
   but the confirming GET failed (a flaky network fails both halves the
   same way). Re-POSTing that blind is how one network blip becomes a
   duplicate somebody deletes by hand later.
"""
import json
import os
import time

# The confirming GET reads the sheet's last N rows. `confirm_row`'s own
# default is 3 - fine right after a write, far too few for a row queued
# days ago that other DJs have since written past. 50 covers a realistic
# backlog without pulling the whole sheet.
CONFIRM_LIMIT = 50


def _identity(row):
    """What makes two queued rows 'the same row'. ARTIST+ALBUM+DATE, not
    the whole dict: two attempts at the same disc on the same day are one
    catalog entry even if a later attempt carries a corrected DJ NAME."""
    if not isinstance(row, dict):
        return ("", "", "")
    return tuple(str(row.get(k, "")).strip().lower()
                 for k in ("ARTIST", "ALBUM", "DATE"))


def _quarantine(path):
    """Move a corrupt outbox aside instead of silently overwriting it -
    it is the only record that some rip never got catalogued, so a parse
    error must not be how it disappears. Best-effort: if even the rename
    fails there is nothing further to try, and load() still degrades to
    empty rather than raising into a rip."""
    for n in range(20):
        dest = f"{path}.corrupt" + (f".{n}" if n else "")
        if os.path.exists(dest):
            continue
        try:
            os.replace(path, dest)
            return dest
        except OSError:
            return None
    return None


def load(path):
    """Every row still waiting to reach the sheet. Missing file, unreadable
    file, or a file holding something that isn't a list of dicts all read
    as empty - never raises. A catalog outbox that throws would abort the
    rip it exists to protect."""
    if not os.path.isfile(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        _quarantine(path)
        return []
    if not isinstance(data, list):
        _quarantine(path)
        return []
    return [e for e in data if isinstance(e, dict) and isinstance(e.get("row"), dict)]


def save(path, items):
    """Atomic replace, not a truncating write: a crash mid-write would
    otherwise leave a half-JSON file, which `load` reads as empty - i.e.
    exactly the silent loss this module exists to stop. Returns True on
    success, False on any OS error (never raises)."""
    tmp = f"{path}.tmp"
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(items, f, indent=2)
        os.replace(tmp, path)
        return True
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return False


def queue(path, row, error="", now=None):
    """Remember a row that didn't reach the sheet.

    Returns "queued" (newly added), "duplicate" (already waiting - its
    attempt count and error are updated in place, no second row), or
    "error" (nothing could be persisted, so the caller must still tell
    the user to add it by hand).
    """
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)) if now \
        else time.strftime("%Y-%m-%dT%H:%M:%S")
    items = load(path)
    want = _identity(row)
    for entry in items:
        if _identity(entry["row"]) == want:
            entry["attempts"] = int(entry.get("attempts", 1) or 1) + 1
            entry["last_attempt"] = stamp
            entry["last_error"] = error
            return "duplicate" if save(path, items) else "error"
    items.append({
        "row": row,
        "queued_at": stamp,
        "last_attempt": stamp,
        "attempts": 1,
        "last_error": error,
    })
    return "queued" if save(path, items) else "error"


def describe(items):
    """One human line per waiting row, for `catalog`/`doctor` output."""
    lines = []
    for entry in items:
        row = entry.get("row", {})
        label = f"{row.get('ARTIST', '?')} - {row.get('ALBUM', '?')}"
        lines.append(f"{label} (queued {entry.get('queued_at', '?')}, "
                     f"{entry.get('attempts', 1)} attempt(s))")
    return lines


def flush(path, url, write_row, confirm_row, confirm_limit=CONFIRM_LIMIT,
          now=None):
    """Try every waiting row against the sheet once.

    Each row is checked with `confirm_row` FIRST - see this module's
    docstring: a queued row may already be in the sheet, and re-POSTing it
    is how a network blip turns into a hand-deleted duplicate. Only rows
    genuinely absent are re-POSTed.

    Rows that succeed (or turn out to be present already) leave the
    outbox; rows that fail stay, with their attempt count bumped. Returns
    {"sent", "already", "failed", "remaining"}. Never raises - both
    injected callables are documented never-raising, and anything they do
    raise is caught and counted as a failure rather than aborting a flush
    partway and losing the rows behind it.
    """
    items = load(path)
    result = {"sent": 0, "already": 0, "failed": 0, "remaining": 0}
    if not items:
        return result
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)) if now \
        else time.strftime("%Y-%m-%dT%H:%M:%S")
    keep = []
    for entry in items:
        row = entry["row"]
        try:
            present = confirm_row(url, row, limit=confirm_limit)
        except Exception:
            present = False
        if present:
            result["already"] += 1
            continue
        try:
            ok = write_row(url, row)
        except Exception:
            ok = False
        if ok:
            result["sent"] += 1
            continue
        result["failed"] += 1
        entry["attempts"] = int(entry.get("attempts", 1) or 1) + 1
        entry["last_attempt"] = stamp
        keep.append(entry)
    result["remaining"] = len(keep)
    save(path, keep)
    return result
