"""Unit tests for the Apps Script catalog write-back client (ROADMAP #8).

Network is mocked throughout - no real HTTP calls.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import json
import os
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "lib", "catalog_writeback.py")
_spec = importlib.util.spec_from_file_location("catalog_writeback", _MODPATH)
cw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cw)


class _FakeResponse:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_post_row_returns_parsed_response():
    body = {"ok": True, "rowWritten": 42}
    with patch.object(cw.urllib.request, "urlopen", return_value=_FakeResponse(body)) as mock_open:
        result = cw.post_row("https://example.com/exec", {"ARTIST": "Fela Kuti"})
    assert result == body
    req = mock_open.call_args[0][0]
    assert req.get_method() == "POST"
    assert req.get_header("Content-type") == "text/plain"
    assert json.loads(req.data.decode("utf-8")) == {"ARTIST": "Fela Kuti"}


def test_post_row_network_error_returns_none():
    with patch.object(cw.urllib.request, "urlopen", side_effect=OSError("boom")):
        assert cw.post_row("https://example.com/exec", {"ARTIST": "X"}) is None


def test_post_row_non_json_response_returns_none():
    # Real-world case: Apps Script's POST redirect chain can return HTML
    # even on a write that actually landed - post_row alone can't tell.
    with patch.object(cw.urllib.request, "urlopen", return_value=_FakeResponse(b"<html>Page Not Found</html>")):
        assert cw.post_row("https://example.com/exec", {"ARTIST": "X"}) is None


def test_confirm_row_finds_matching_artist_and_album():
    body = {"rows": [{"ARTIST": "Someone Else", "ALBUM": "Other"},
                      {"ARTIST": "Fela Kuti", "ALBUM": "Expensive Shit"}]}
    with patch.object(cw.urllib.request, "urlopen", return_value=_FakeResponse(body)):
        assert cw.confirm_row("https://example.com/exec",
                               {"ARTIST": "Fela Kuti", "ALBUM": "Expensive Shit"}) is True


def test_confirm_row_no_match_returns_false():
    body = {"rows": [{"ARTIST": "Someone Else", "ALBUM": "Other"}]}
    with patch.object(cw.urllib.request, "urlopen", return_value=_FakeResponse(body)):
        assert cw.confirm_row("https://example.com/exec",
                               {"ARTIST": "Fela Kuti", "ALBUM": "Expensive Shit"}) is False


def test_confirm_row_network_error_returns_false():
    with patch.object(cw.urllib.request, "urlopen", side_effect=OSError("boom")):
        assert cw.confirm_row("https://example.com/exec", {"ARTIST": "X", "ALBUM": "Y"}) is False


def test_confirm_row_non_dict_json_returns_false():
    # A GAS error/misconfiguration can return valid JSON that isn't an
    # object (bare string, null, list) - not a parse failure, so the
    # except clause alone doesn't catch it.
    for body in ["error", None, [], False]:
        with patch.object(cw.urllib.request, "urlopen", return_value=_FakeResponse(body)):
            assert cw.confirm_row("https://example.com/exec", {"ARTIST": "X", "ALBUM": "Y"}) is False


def test_confirm_row_non_dict_rows_entries_are_skipped():
    body = {"rows": ["not a row", {"ARTIST": "Fela Kuti", "ALBUM": "Expensive Shit"}]}
    with patch.object(cw.urllib.request, "urlopen", return_value=_FakeResponse(body)):
        assert cw.confirm_row("https://example.com/exec",
                               {"ARTIST": "Fela Kuti", "ALBUM": "Expensive Shit"}) is True


def test_write_row_posts_then_confirms():
    with patch.object(cw, "post_row") as mock_post, \
         patch.object(cw, "confirm_row", return_value=True) as mock_confirm:
        fields = {"ARTIST": "Fela Kuti", "ALBUM": "Expensive Shit"}
        assert cw.write_row("https://example.com/exec", fields) is True
    mock_post.assert_called_once_with("https://example.com/exec", fields, timeout=15)
    mock_confirm.assert_called_once_with("https://example.com/exec", fields, timeout=15)


def test_write_row_returns_false_when_unconfirmed():
    with patch.object(cw, "post_row"), patch.object(cw, "confirm_row", return_value=False):
        assert cw.write_row("https://example.com/exec", {"ARTIST": "X", "ALBUM": "Y"}) is False


# --- schema drift detection -------------------------------------------

def test_normalize_header_matches_the_gas_rule():
    # Trimmed and case-folded on both sides...
    assert cw.normalize_header("  DJ NAME ") == cw.normalize_header("dj name")
    assert cw.normalize_header("Artist") == cw.normalize_header("ARTIST")
    # ...but NOT whitespace-collapsed. This is the whole trap: the GAS
    # endpoint would drop both of these against the header "DJ NAME",
    # silently, and still append the row.
    assert cw.normalize_header("DJNAME") != cw.normalize_header("DJ NAME")
    assert cw.normalize_header("DJ  NAME") != cw.normalize_header("DJ NAME")


def test_normalize_header_survives_non_string_cells():
    # A sheet header row can hand back numbers/blanks/dates, not just text.
    assert cw.normalize_header(3) == "3"
    assert cw.normalize_header(None) == "none"


def test_build_row_carries_the_columns_a_rip_writes():
    row = cw.build_row("Some Band", "Some Record", "2026-07-27", dj_name="Guy")
    assert row == {
        "ARTIST": "Some Band",
        "ALBUM": "Some Record",
        "DATE": "2026-07-27",
        "LOCAL": True,
        "DJ NAME": "Guy",
    }


def test_build_row_strips_but_omits_an_empty_dj_name():
    # An empty DJ NAME writes no column at all rather than blanking one -
    # a second DJ's rips must not land attributed to Guy.
    row = cw.build_row("  A  ", "  B  ", "2026-07-27", dj_name="   ")
    assert "DJ NAME" not in row
    assert row["ARTIST"] == "A" and row["ALBUM"] == "B"


def test_unmatched_keys_finds_the_renamed_column():
    headers = ["#", "ARTIST", "ALBUM", "DATE", "LOCAL", "DJ"]
    row = cw.build_row("a", "b", "2026-07-27", dj_name="Guy")
    assert cw.unmatched_keys(headers, row) == ["DJ NAME"]


def test_unmatched_keys_is_empty_against_the_real_sheet_schema():
    headers = ["#", "ARTIST", "ALBUM", "LABEL", "YEAR", "Rating", "GENRE",
               "MERIT", "LOCAL", "COMMENT", "DATE", "DJ NAME", "HOME"]
    row = cw.build_row("a", "b", "2026-07-27", dj_name="Guy")
    assert cw.unmatched_keys(headers, row) == []


def test_unmatched_keys_reports_everything_when_no_header_row():
    row = cw.build_row("a", "b", "2026-07-27", dj_name="Guy")
    assert cw.unmatched_keys([], row) == sorted(row)


def test_fetch_schema_reads_headers():
    with patch.object(cw.urllib.request, "urlopen",
                      return_value=_FakeResponse({"headers": ["ARTIST", "ALBUM"]})):
        assert cw.fetch_schema("https://x/exec") == ["ARTIST", "ALBUM"]


def test_fetch_schema_asks_for_the_read_only_scope():
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        return _FakeResponse({"headers": []})

    with patch.object(cw.urllib.request, "urlopen", fake_urlopen):
        cw.fetch_schema("https://x/exec")
    assert "scope=schema" in seen["url"]
    # A preflight must never append a row: this has to stay a GET.
    assert seen["method"] == "GET"


def test_fetch_schema_returns_none_on_network_failure():
    with patch.object(cw.urllib.request, "urlopen",
                      side_effect=cw.urllib.error.URLError("down")):
        assert cw.fetch_schema("https://x/exec") is None


def test_fetch_schema_returns_none_on_non_json_and_odd_shapes():
    # Apps Script's "Page Not Found" HTML, a bare JSON scalar, a GAS
    # {"error": ...} object, and a non-list headers value are all
    # "couldn't tell" - none of them may read as "the sheet has no
    # columns", which would fire a bogus drift warning on every rip.
    for body in (b"<html>Page Not Found</html>", b'"nope"', b"null",
                 {"error": "SHEET_NAME not found"}, {"headers": "ARTIST"}):
        with patch.object(cw.urllib.request, "urlopen",
                          return_value=_FakeResponse(body)):
            assert cw.fetch_schema("https://x/exec") is None
