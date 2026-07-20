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
