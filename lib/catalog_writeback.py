"""Google Sheets catalog write-back via a bound Apps Script endpoint
(ROADMAP #8) - no OAuth/service account, just POST JSON to a deployed
`/exec` URL. See `gas/catalog-writeback.gs.js` for the endpoint itself,
which matches incoming keys to the sheet's actual column headers by name.
"""
import json
import urllib.error
import urllib.parse
import urllib.request


def normalize_header(text):
    """The GAS endpoint's own key-to-column rule, in one place.

    `gas/catalog-writeback.gs.js`'s `doPost` matches an incoming JSON key
    to a header cell by `String(h).trim().toLowerCase()` on both sides -
    trimmed and case-folded, but NOT whitespace-collapsed. That last part
    is the trap: `DJNAME` and `DJ  NAME` both fail to match the header
    `DJ NAME`, and an unmatched key is *ignored, not errored* (the
    endpoint reports it in `unmatchedKeys`, but a POST response against
    this endpoint is documented-untrustworthy - see `post_row` - so
    nothing reads it). The row still appends, with that column blank.

    Mirrored here rather than re-typed as a rule so `unmatched_keys`
    below predicts the real endpoint's behaviour instead of an
    approximation of it - the same lesson `album_dir_path` learned from
    `abcde.conf`'s `mungefilename`.
    """
    return str(text).strip().lower()


def build_row(artist, album, date, dj_name="", local=True):
    """The catalog row wtul sends, as one definition.

    `rip_session()` in `bin/wtul-rip` writes this, and `doctor`'s schema
    check reads its keys to know what to validate against the live
    sheet's headers - so the column names live here, not in both.

    An empty `dj_name` omits the DJ NAME column entirely rather than
    writing a blank over it, so a second DJ running this tool doesn't get
    their rips attributed to Guy (see `CATALOG_DJ_NAME` in bin/wtul-rip).
    """
    row = {
        "ARTIST": str(artist).strip(),
        "ALBUM": str(album).strip(),
        "DATE": date,
        "LOCAL": local,
    }
    # "DJ NAME" carries the sheet's header text verbatim, space included.
    if str(dj_name).strip():
        row["DJ NAME"] = str(dj_name).strip()
    return row


def fetch_schema(url, timeout=15):
    """GET the sheet's detected header row (`?scope=schema`).

    Read-only - it appends nothing and is safe to call from a preflight.
    Returns the list of header cells, or None if the endpoint was
    unreachable, returned non-JSON, or returned JSON without a usable
    `headers` list. None means "couldn't tell", never "no headers".
    """
    get_url = f"{url}?{urllib.parse.urlencode({'scope': 'schema'})}"
    try:
        with urllib.request.urlopen(urllib.request.Request(get_url),
                                    timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    # A GAS misconfiguration returns valid JSON that isn't an object (or
    # an object carrying {"error": ...} instead of headers) - neither is
    # a parse failure, so the except above never sees them.
    if not isinstance(data, dict):
        return None
    headers = data.get("headers")
    if not isinstance(headers, list):
        return None
    return headers


def unmatched_keys(headers, fields):
    """Which keys of `fields` the endpoint would silently drop.

    Returns them sorted, so a caller's message is stable. An empty
    `headers` list means the sheet has no detectable header row, in which
    case the endpoint refuses the whole POST rather than dropping keys -
    so every key is reported, which is the honest answer.
    """
    known = {normalize_header(h) for h in headers}
    return sorted(k for k in fields if normalize_header(k) not in known)


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
    if not isinstance(data, dict):
        # A GAS error/misconfiguration can return valid JSON that isn't
        # an object (bare string, null, list) - not a parse failure, so
        # the except clause above never catches it. `.get("rows", ...)`
        # would raise AttributeError on anything non-dict otherwise.
        return False
    want_artist = str(fields.get("ARTIST", "")).strip()
    want_album = str(fields.get("ALBUM", "")).strip()
    for row in data.get("rows", []) or []:
        if not isinstance(row, dict):
            continue
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
