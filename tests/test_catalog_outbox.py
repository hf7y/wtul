"""Unit tests for the catalog retry outbox (FOCUS.md #8,
lib/catalog_outbox.py).

No network anywhere: `flush` takes its two HTTP callables as arguments
precisely so the retry policy - the part with the duplicate-row hazard in
it - is testable without touching the station's live sheet.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "lib", "catalog_outbox.py")
_spec = importlib.util.spec_from_file_location("catalog_outbox", _MODPATH)
ob = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ob)

ROW = {"ARTIST": "Belong", "ALBUM": "October Language", "DATE": "2026-07-27",
       "LOCAL": True, "DJ NAME": "Guy"}


def _path(tmp_path):
    return str(tmp_path / ".catalog-outbox.json")


# -- queueing -----------------------------------------------------------


def test_missing_file_reads_as_empty(tmp_path):
    assert ob.load(_path(tmp_path)) == []


def test_queue_then_load_round_trips_the_row(tmp_path):
    p = _path(tmp_path)
    assert ob.queue(p, ROW) == "queued"
    items = ob.load(p)
    assert len(items) == 1
    assert items[0]["row"] == ROW
    assert items[0]["attempts"] == 1
    assert items[0]["queued_at"]


def test_queueing_the_same_disc_twice_does_not_duplicate_the_row(tmp_path):
    """The asymmetry this whole module is built around: a duplicate row in
    the live catalog comes out by hand (#8 built no delete endpoint), so
    re-ripping the same disc on a bad-network night must queue once."""
    p = _path(tmp_path)
    assert ob.queue(p, ROW) == "queued"
    assert ob.queue(p, dict(ROW)) == "duplicate"
    items = ob.load(p)
    assert len(items) == 1
    assert items[0]["attempts"] == 2


def test_same_disc_ripped_on_a_different_day_is_a_different_row(tmp_path):
    p = _path(tmp_path)
    ob.queue(p, ROW)
    ob.queue(p, dict(ROW, DATE="2026-08-03"))
    assert len(ob.load(p)) == 2


def test_identity_ignores_case_and_surrounding_space(tmp_path):
    p = _path(tmp_path)
    ob.queue(p, ROW)
    ob.queue(p, dict(ROW, ARTIST="  belong  ", ALBUM="OCTOBER LANGUAGE"))
    assert len(ob.load(p)) == 1


def test_a_corrected_dj_name_does_not_queue_a_second_row(tmp_path):
    """DJ NAME is deliberately outside the identity key - two attempts at
    the same disc on the same day are one catalog entry."""
    p = _path(tmp_path)
    ob.queue(p, ROW)
    ob.queue(p, dict(ROW, **{"DJ NAME": "Someone Else"}))
    assert len(ob.load(p)) == 1


def test_queue_records_the_error_it_was_given(tmp_path):
    p = _path(tmp_path)
    ob.queue(p, ROW, error="unconfirmed")
    assert ob.load(p)[0]["last_error"] == "unconfirmed"


# -- damaged / hostile files -------------------------------------------


def test_corrupt_file_reads_as_empty_and_is_quarantined_not_overwritten(tmp_path):
    """A parse error must not be how the only record of an unlogged rip
    disappears - the bad file is moved aside, not clobbered."""
    p = _path(tmp_path)
    with open(p, "w") as f:
        f.write("{ this is not json")
    assert ob.load(p) == []
    assert os.path.isfile(p + ".corrupt")
    with open(p + ".corrupt") as f:
        assert f.read() == "{ this is not json"


def test_repeated_corruption_does_not_overwrite_the_first_quarantine(tmp_path):
    p = _path(tmp_path)
    for text in ("first bad file", "second bad file"):
        with open(p, "w") as f:
            f.write(text)
        assert ob.load(p) == []
    assert open(p + ".corrupt").read() == "first bad file"
    assert open(p + ".corrupt.1").read() == "second bad file"


def test_valid_json_that_is_not_a_list_reads_as_empty(tmp_path):
    p = _path(tmp_path)
    for body in ({"row": ROW}, "rows", 7, None):
        with open(p, "w") as f:
            json.dump(body, f)
        assert ob.load(p) == []


def test_entries_without_a_row_dict_are_skipped(tmp_path):
    p = _path(tmp_path)
    with open(p, "w") as f:
        json.dump(["not an entry", {"no_row": 1}, {"row": "not a dict"},
                   {"row": ROW}], f)
    items = ob.load(p)
    assert len(items) == 1
    assert items[0]["row"] == ROW


def test_save_failure_is_reported_not_raised(tmp_path):
    # A path whose parent is a file, not a directory: makedirs fails.
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    assert ob.save(str(blocker / "sub" / "outbox.json"), []) is False
    assert ob.queue(str(blocker / "sub" / "outbox.json"), ROW) == "error"


# -- flushing -----------------------------------------------------------


def test_flush_on_an_empty_outbox_touches_nothing(tmp_path):
    def boom(*a, **k):
        raise AssertionError("flush must not call out on an empty outbox")

    result = ob.flush(_path(tmp_path), "https://example.invalid/exec",
                      write_row=boom, confirm_row=boom)
    assert result == {"sent": 0, "already": 0, "failed": 0, "remaining": 0}


def test_flush_writes_a_missing_row_and_clears_it(tmp_path):
    p = _path(tmp_path)
    ob.queue(p, ROW)
    written = []
    result = ob.flush(p, "https://example.invalid/exec",
                      write_row=lambda url, row: written.append(row) or True,
                      confirm_row=lambda url, row, limit=None: False)
    assert written == [ROW]
    assert result["sent"] == 1
    assert result["remaining"] == 0
    assert ob.load(p) == []


def test_flush_confirms_before_it_reposts(tmp_path):
    """The duplicate-row hazard, pinned. `write_row` returns False when the
    POST landed but its confirming GET failed - a flaky network fails both
    halves the same way - so a queued row may already be in the sheet.
    Re-POSTing it blind is how one blip becomes a hand-deleted duplicate."""
    p = _path(tmp_path)
    ob.queue(p, ROW)

    def must_not_post(url, row):
        raise AssertionError("re-POSTed a row that was already in the sheet")

    result = ob.flush(p, "https://example.invalid/exec",
                      write_row=must_not_post,
                      confirm_row=lambda url, row, limit=None: True)
    assert result["already"] == 1
    assert result["sent"] == 0
    assert ob.load(p) == []


def test_flush_confirm_reads_further_back_than_a_fresh_write_does(tmp_path):
    """`confirm_row`'s own default of 3 rows is right after a write and
    useless for a row queued days ago that other DJs have written past."""
    p = _path(tmp_path)
    ob.queue(p, ROW)
    limits = []
    ob.flush(p, "https://example.invalid/exec",
             write_row=lambda url, row: True,
             confirm_row=lambda url, row, limit=None: limits.append(limit) or False)
    assert limits == [ob.CONFIRM_LIMIT]
    assert ob.CONFIRM_LIMIT >= 20


def test_flush_keeps_a_row_that_still_fails_and_counts_the_attempt(tmp_path):
    p = _path(tmp_path)
    ob.queue(p, ROW)
    result = ob.flush(p, "https://example.invalid/exec",
                      write_row=lambda url, row: False,
                      confirm_row=lambda url, row, limit=None: False)
    assert result["failed"] == 1
    assert result["remaining"] == 1
    items = ob.load(p)
    assert len(items) == 1
    assert items[0]["attempts"] == 2


def test_flush_partial_success_keeps_only_the_failures(tmp_path):
    p = _path(tmp_path)
    ob.queue(p, ROW)
    ob.queue(p, dict(ROW, ALBUM="Common Era"))
    ob.queue(p, dict(ROW, ALBUM="Colorloss Record"))
    result = ob.flush(
        p, "https://example.invalid/exec",
        write_row=lambda url, row: row["ALBUM"] != "Common Era",
        confirm_row=lambda url, row, limit=None: False)
    assert (result["sent"], result["failed"], result["remaining"]) == (2, 1, 1)
    assert [e["row"]["ALBUM"] for e in ob.load(p)] == ["Common Era"]


def test_a_raising_client_is_a_failure_not_a_crash(tmp_path):
    """Both callables are documented never-raising, but a flush that dies
    partway would lose every row behind the one that threw - the exact
    loss this module exists to prevent."""
    p = _path(tmp_path)
    ob.queue(p, ROW)
    ob.queue(p, dict(ROW, ALBUM="Common Era"))

    def explode(*a, **k):
        raise RuntimeError("urllib went sideways")

    result = ob.flush(p, "https://example.invalid/exec",
                      write_row=explode,
                      confirm_row=lambda url, row, limit=None: False)
    assert result["failed"] == 2
    assert result["remaining"] == 2
    assert len(ob.load(p)) == 2


def test_a_raising_confirm_falls_through_to_a_real_write(tmp_path):
    p = _path(tmp_path)
    ob.queue(p, ROW)

    def explode(*a, **k):
        raise RuntimeError("GET went sideways")

    result = ob.flush(p, "https://example.invalid/exec",
                      write_row=lambda url, row: True, confirm_row=explode)
    assert result["sent"] == 1


# -- describe -----------------------------------------------------------


def test_describe_names_each_waiting_disc(tmp_path):
    p = _path(tmp_path)
    ob.queue(p, ROW)
    lines = ob.describe(ob.load(p))
    assert len(lines) == 1
    assert "Belong - October Language" in lines[0]
    assert "1 attempt(s)" in lines[0]


def test_describe_survives_a_row_missing_its_fields(tmp_path):
    assert "? - ?" in ob.describe([{"row": {}}])[0]
