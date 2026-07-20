"""Google Sheets catalog write-back via a bound Apps Script endpoint
(ROADMAP #8) - no OAuth/service account, just POST JSON to a deployed
`/exec` URL. See `gas/catalog-writeback.gs.js` for the endpoint itself,
which matches incoming keys to the sheet's actual column headers by name.
"""
import json
import urllib.error
import urllib.parse
import urllib.request


def post_row(url, fields, timeout=15):
    """POST a {column_name: value} dict as a new catalog row. Returns the
    endpoint's parsed JSON response, or None on any network/parse
    failure. Live-verified 2026-07-20: a real write against this endpoint
    came back as Apps Script's own redirect/"Page Not Found" HTML, not
    JSON - exactly the gotcha the scheduler's `INTAKE.md` documents
    ("never trust the raw HTTP response from a POST against an
    Apps-Script-backed endpoint") - the write itself still landed. So a
    None return here does NOT mean the write failed; `write_row` below is
    the function that actually knows.
    """
    data = json.dumps(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                  headers={"Content-Type": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def confirm_row(url, fields, limit=3, timeout=15):
    """Re-GET the most recent rows and check whether one matches `fields`
    on ARTIST+ALBUM - the only reliable way to know a write against this
    endpoint actually landed, since its own POST response can't be
    trusted (see `post_row`'s docstring). Returns True/False, never
    raises."""
    get_url = f"{url}?{urllib.parse.urlencode({'scope': 'rows', 'limit': limit})}"
    req = urllib.request.Request(get_url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return False
    want_artist = str(fields.get("ARTIST", "")).strip()
    want_album = str(fields.get("ALBUM", "")).strip()
    for row in data.get("rows", []) or []:
        if (str(row.get("ARTIST", "")).strip() == want_artist
                and str(row.get("ALBUM", "")).strip() == want_album):
            return True
    return False


def write_row(url, fields, timeout=15):
    """POST `fields` as a new catalog row, then re-GET to confirm it
    actually landed - the POST's own response is documented-unreliable
    against this kind of endpoint (see `post_row`). Returns True if
    confirmed present, False otherwise. Never raises - a catalog-write
    failure must never abort a rip that already succeeded.
    """
    post_row(url, fields, timeout=timeout)
    return confirm_row(url, fields, timeout=timeout)
