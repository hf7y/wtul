"""Unit tests for the rip-speed parsing/reporting logic in bin/wtul-rip.

These exercise ROADMAP #6 (rip-speed monitoring) against the exact
cdparanoia/abcde log format the tool actually produces. None of this needs
an optical drive or a disc - it's pure text parsing over log fixtures, so it
runs (and means something) in an unattended batch run.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import os

import pytest

# bin/wtul-rip has no .py suffix and a hyphen, so load it by path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "bin", "wtul-rip")
_spec = importlib.util.spec_from_loader(
    "wtul_rip", importlib.machinery.SourceFileLoader("wtul_rip", _MODPATH))
wtul = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wtul)


# A trimmed but format-faithful slice of a real session log: two good tracks
# (track 1 fast, track 2 slower) and one failed track with no speed samples.
SAMPLE_LOG = """\
2026-07-17T12:27:16-0500: metadata scrape

=== track 1 ===
Grabbing track 1: Track 1...
cdparanoia III release 10.2 (September 11, 2008)
     0/5741   ( 0%)|    0:00/    0:00|    0:00/    0:00|   0.0000x|    0:00
   100/5741   ( 2%)|    0:00/    0:06|    0:00/    0:06|   21.912x|    0:06
  5741/5741   (100%)|    0:06/    0:06|    0:06/    0:06|   25.100x|    0:00
Encoding track 1 of 3: Track 1...
.../home/zach/Music/ripped/abcde.67083a08/track1.mp3[ 8.92 MB ]
track 1 ripped OK
=== track 2 ===
Grabbing track 2: Track 2...
   100/9000   ( 1%)|    0:00/    0:20|    0:00/    0:20|   10.000x|    0:20
  9000/9000   (100%)|    0:20/    0:20|    0:20/    0:20|   11.500x|    0:00
.../home/zach/Music/ripped/abcde.67083a08/track2.mp3[ 5.90 MB ]
track 2 ripped OK
=== track 3 ===
Grabbing track 3: Track 3...
readtrack-3: cdparanoia  returned code 73
track 3 failed (rc=0)
2026-07-17T12:36:19-0500: session finished - 2/3 tracks ripped, disc left in drive for retry
"""


def test_parse_basic_records():
    recs = wtul.parse_rip_speeds(SAMPLE_LOG)
    assert [r["track"] for r in recs] == [1, 2, 3]
    r1, r2, r3 = recs
    assert r1["status"] == "ok"
    assert r1["final"] == 25.1          # last non-zero sample, not the 0.0000x
    assert r1["peak"] == 25.1
    assert r1["size_mb"] == 8.92
    assert r2["status"] == "ok"
    assert r2["final"] == 11.5
    assert r3["status"] == "failed"
    assert r3["final"] is None          # no speed samples on a failed grab
    assert r3["size_mb"] is None


def test_zero_speed_sample_ignored_for_final_and_peak():
    log = ("=== track 4 ===\n"
           "     0/100 ( 0%)|0:00/0:00|0:00/0:00|   0.0000x|    0:00\n"
           "track 4 failed (rc=0)\n")
    (r,) = wtul.parse_rip_speeds(log)
    assert r["samples"] == 1            # the 0.0000x line still counts as a sample
    assert r["final"] is None
    assert r["peak"] is None


def test_truncated_section_is_unknown_not_dropped():
    # A log cut off mid-track (no note line) must still surface the track.
    log = ("=== track 9 ===\n"
           "   100/5000 ( 2%)|0:00/0:06|0:00/0:06|   18.000x|    0:06\n")
    (r,) = wtul.parse_rip_speeds(log)
    assert r["track"] == 9
    assert r["status"] == "unknown"
    assert r["final"] == 18.0


def test_note_for_other_track_does_not_bleed():
    # A stray "track 1 ripped OK" inside track 2's section must not retag it.
    log = ("=== track 2 ===\n"
           "  100/100 (100%)|0:01/0:01|0:01/0:01|   12.000x|    0:00\n"
           "track 1 ripped OK\n")
    (r,) = wtul.parse_rip_speeds(log)
    assert r["track"] == 2
    assert r["status"] == "unknown"     # only a matching-track note sets status


def test_timeout_and_interrupted_statuses():
    log = ("=== track 5 ===\n"
           "track 5 TIMED OUT after 900s\n"
           "=== track 6 ===\n"
           "track 6 interrupted by '!q'\n")
    a, b = wtul.parse_rip_speeds(log)
    assert a["status"] == "timeout"
    assert b["status"] == "interrupted"


def test_median_helper():
    assert wtul._median([]) is None
    assert wtul._median([5]) == 5
    assert wtul._median([1, 3]) == 2
    assert wtul._median([3, 1, 2]) == 2


def test_format_report_empty():
    assert "No extraction-speed data" in wtul.format_speed_report([])
    # Sessions that parsed but have no ok+speed tracks are also "empty".
    recs = wtul.parse_rip_speeds("=== track 1 ===\ntrack 1 failed (rc=0)\n")
    assert "No extraction-speed data" in wtul.format_speed_report([("only-fails.log", recs)])


def test_format_report_stats_and_median():
    recs = wtul.parse_rip_speeds(SAMPLE_LOG)
    out = wtul.format_speed_report([("s.log", recs)])
    assert "2 tracks with speed data" in out
    # median of {25.1, 11.5} = 18.3
    assert "18.3x" in out
    assert "max 25.1x" in out


def test_slow_track_flagged():
    recs = wtul.parse_rip_speeds(SAMPLE_LOG)  # 25.1 and 11.5; median 18.3, cut 9.15
    slow = wtul.parse_rip_speeds(
        "=== track 7 ===\n"
        "  10/10 (100%)|0:05/0:05|0:05/0:05|   3.000x|    0:00\n"
        ".../x/track7.mp3[ 1.00 MB ]\n"
        "track 7 ripped OK\n")
    out = wtul.format_speed_report([("a.log", recs), ("b.log", slow)])
    assert "Slow tracks" in out
    assert "track 7: 3.0x" in out


def test_degradation_note_when_recent_session_collapses():
    fast = wtul.parse_rip_speeds(
        "=== track 1 ===\n  10/10 (100%)|0:00/0:00|0:00/0:00|  24.000x|0:00\n"
        "track 1 ripped OK\n")
    also_fast = wtul.parse_rip_speeds(
        "=== track 1 ===\n  10/10 (100%)|0:00/0:00|0:00/0:00|  22.000x|0:00\n"
        "track 1 ripped OK\n")
    crawl = wtul.parse_rip_speeds(
        "=== track 1 ===\n  10/10 (100%)|0:00/0:00|0:00/0:00|   2.000x|0:00\n"
        "track 1 ripped OK\n")
    out = wtul.format_speed_report(
        [("old1.log", fast), ("old2.log", also_fast), ("new.log", crawl)])
    assert "possible drive/media" in out


def test_real_logs_parse_without_error():
    # Belt-and-suspenders: parse whatever real logs exist on this machine to
    # make sure the format assumptions hold against production output, not just
    # the hand-written fixture. Skips cleanly on a machine with no logs.
    logdir = os.path.expanduser("~/Music/ripped/.logs")
    if not os.path.isdir(logdir):
        pytest.skip("no rip logs on this machine")
    sessions = wtul.load_speed_sessions(logdir)
    for name, recs in sessions:
        for r in recs:
            assert r["status"] in ("ok", "failed", "timeout", "interrupted", "unknown")
            assert r["final"] is None or r["final"] > 0
