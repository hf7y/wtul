"""Unit tests for `wtul-rip doctor` (lib/preflight.py).

Everything the preflight touches arrives through a Context, so this whole
file runs with no optical drive, no network, no installed abcde - which is
the point: the check that tells you the rig is broken must itself be
verifiable on a machine where the rig isn't present.

Run with:  python3 -m pytest tests/ -q
"""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "lib"))
import preflight  # noqa: E402


def make_ctx(**over):
    """A Context where every check passes, so each test can break exactly
    one thing and assert on that one thing."""
    base = dict(
        dev="/dev/sr0",
        home="/home/zach",
        mixes_root="/home/zach/Music/mixes",
        ripdir="/home/zach/Music/mixes/2026-07-26",
        abcde_conf="/home/zach/.abcde.conf",
        noeject_conf="/home/zach/.abcde-noeject.conf",
        lockfile="/tmp/cd-autorip-sr0.lock",
        environ={var: "set" for var, _ in preflight.CREDENTIALS},
        which=lambda n: f"/usr/bin/{n}",
        run=lambda cmd, timeout=15: (
            0, "/home/zach/Music/mixes/2026-07-26\n"
               "/home/zach/Music/mixes/2026-07-26\n"),
        fetch=lambda url, timeout=6: (True, ""),
        free_kb=lambda p: 50 * 1024 * 1024,
        exists=lambda p: p != "/tmp/cd-autorip-sr0.lock",
        isdir=lambda p: p.startswith("/home/zach"),
        isfile=lambda p: p.endswith(".conf"),
        access=lambda p, mode: True,
        glob_=lambda pat: [],
        mtime=lambda p: 0,
        now=lambda: 1_000_000,
        import_ok=lambda m: True,
        lock_is_stale=lambda p: True,
        outbox_pending=lambda: [],
    )
    base.update(over)
    return preflight.Context(**base)


def by_name(checks, name):
    matches = [c for c in checks if c.name == name]
    assert matches, f"no check named {name!r} in {[c.name for c in checks]}"
    return matches[0]


def test_all_green_rig_is_ready():
    checks = preflight.run_checks(make_ctx())
    bad = [(c.name, c.status, c.detail) for c in checks if c.status != preflight.OK]
    assert bad == []
    assert preflight.worst_status(checks) == preflight.OK
    assert "Ready to rip - all checks passed." in preflight.format_report(checks)


def test_missing_required_binary_fails_loud():
    ctx = make_ctx(which=lambda n: None if n == "lame" else f"/usr/bin/{n}")
    checks = preflight.run_checks(ctx)
    assert by_name(checks, "binary: lame").status == preflight.FAIL
    assert preflight.worst_status(checks) == preflight.FAIL
    assert "NOT READY" in preflight.format_report(checks)


def test_missing_optional_binary_only_warns():
    ctx = make_ctx(which=lambda n: None if n == "eject" else f"/usr/bin/{n}")
    checks = preflight.run_checks(ctx)
    assert by_name(checks, "binary: eject").status == preflight.WARN
    assert preflight.worst_status(checks) == preflight.WARN


def test_missing_mutagen_warns():
    ctx = make_ctx(import_ok=lambda m: m != "mutagen")
    assert by_name(preflight.run_checks(ctx),
                   "python: mutagen").status == preflight.WARN


def test_absent_drive_fails():
    ctx = make_ctx(exists=lambda p: False)
    assert by_name(preflight.run_checks(ctx), "drive").status == preflight.FAIL


def test_unreadable_drive_fails_differently_from_absent():
    ctx = make_ctx(access=lambda p, mode: not (p == "/dev/sr0" and mode == os.R_OK))
    check = by_name(preflight.run_checks(ctx), "drive")
    assert check.status == preflight.FAIL
    assert "not readable" in check.detail


def test_rehearsal_mode_does_not_demand_a_drive():
    ctx = make_ctx(simulating=True, exists=lambda p: False)
    check = by_name(preflight.run_checks(ctx), "drive")
    assert check.status == preflight.OK
    assert "rehearsal" in check.detail


def test_outputdir_drift_is_a_failure():
    """The regression this check exists for: abcde writes somewhere
    wtul-rip isn't looking, so the rip 'succeeds' into a folder nothing
    downstream ever reads."""
    ctx = make_ctx(run=lambda cmd, timeout=15: (
        0, "/home/zach/Music/ripped\n/home/zach/Music/ripped\n"))
    check = by_name(preflight.run_checks(ctx), "config: OUTPUTDIR vs RIPDIR")
    assert check.status == preflight.FAIL
    assert "/home/zach/Music/ripped" in check.detail
    assert "/home/zach/Music/mixes/2026-07-26" in check.detail


def test_outputdir_drift_alone_is_caught():
    """Each variable is checked on its own: a suite that only ever drifts
    both at once passes even if one comparison is dead code."""
    ctx = make_ctx(run=lambda cmd, timeout=15: (
        0, "/home/zach/Music/ripped\n/home/zach/Music/mixes/2026-07-26\n"))
    check = by_name(preflight.run_checks(ctx), "config: OUTPUTDIR vs RIPDIR")
    assert check.status == preflight.FAIL
    assert "WAVOUTPUTDIR" not in check.detail
    assert check.detail.count("OUTPUTDIR=") == 1


def test_wavoutputdir_drift_alone_is_caught():
    ctx = make_ctx(run=lambda cmd, timeout=15: (
        0, "/home/zach/Music/mixes/2026-07-26\n/\n"))
    check = by_name(preflight.run_checks(ctx), "config: OUTPUTDIR vs RIPDIR")
    assert check.status == preflight.FAIL
    assert "WAVOUTPUTDIR" in check.detail
    # ...and the correct OUTPUTDIR is not also listed as a problem
    assert check.detail.count("OUTPUTDIR=") == 1


def test_unset_outputdir_reads_as_unset_not_empty_match():
    ctx = make_ctx(run=lambda cmd, timeout=15: (0, "\n\n"))
    check = by_name(preflight.run_checks(ctx), "config: OUTPUTDIR vs RIPDIR")
    assert check.status == preflight.FAIL
    assert "(unset)" in check.detail


def test_unparseable_abcde_conf_fails_rather_than_passing_quietly():
    ctx = make_ctx(run=lambda cmd, timeout=15: (2, "syntax error near line 3"))
    check = by_name(preflight.run_checks(ctx), "config: OUTPUTDIR vs RIPDIR")
    assert check.status == preflight.FAIL
    assert "syntax error" in check.detail


def test_missing_conf_files_fail():
    ctx = make_ctx(isfile=lambda p: False)
    checks = preflight.run_checks(ctx)
    assert by_name(checks, "config: ~/.abcde.conf").status == preflight.FAIL
    assert by_name(checks, "config: ~/.abcde-noeject.conf").status == preflight.FAIL
    # The drift check can't run without the file; it must say so, not pass.
    assert by_name(checks, "config: OUTPUTDIR vs RIPDIR").status == preflight.WARN


def test_disk_thresholds():
    for free, want in (
        (50 * 1024 * 1024, preflight.OK),
        (preflight.DISK_WARN_KB - 1, preflight.WARN),
        (preflight.DISK_FAIL_KB - 1, preflight.FAIL),
    ):
        ctx = make_ctx(free_kb=lambda p, f=free: f)
        assert by_name(preflight.run_checks(ctx), "disk space").status == want


def test_disk_check_walks_up_to_an_existing_dir():
    """Today's RIPDIR doesn't exist until the first rip of the day - the
    check must measure its nearest existing parent, not give up."""
    seen = []

    def free_kb(p):
        seen.append(p)
        return 50 * 1024 * 1024

    ctx = make_ctx(
        isdir=lambda p: p == "/home/zach/Music/mixes",
        free_kb=free_kb)
    assert by_name(preflight.run_checks(ctx), "disk space").status == preflight.OK
    assert seen[0] == "/home/zach/Music/mixes"


def test_unwritable_mix_folder_fails():
    ctx = make_ctx(access=lambda p, mode: mode != os.W_OK)
    assert by_name(preflight.run_checks(ctx), "mix folder").status == preflight.FAIL


def test_stale_lockfile_warns_and_says_it_is_takeable():
    ctx = make_ctx(exists=lambda p: True, lock_is_stale=lambda p: True)
    check = by_name(preflight.run_checks(ctx), "lockfile")
    assert check.status == preflight.WARN
    assert "stale" in check.detail


def test_held_lockfile_reports_a_live_rip_not_a_stale_file():
    ctx = make_ctx(exists=lambda p: True, lock_is_stale=lambda p: False)
    check = by_name(preflight.run_checks(ctx), "lockfile")
    assert check.status == preflight.WARN
    assert "holding" in check.detail
    assert "stale" not in check.detail


def test_lock_check_without_a_tester_does_not_claim_staleness():
    ctx = make_ctx(exists=lambda p: True, lock_is_stale=None)
    check = by_name(preflight.run_checks(ctx), "lockfile")
    assert check.status == preflight.WARN
    assert "could not test" in check.detail


def test_stale_abcde_tempdirs_warn_but_fresh_ones_do_not():
    fresh = make_ctx(glob_=lambda pat: ["/r/abcde.111"],
                     mtime=lambda p: 1_000_000 - 60)
    assert by_name(preflight.run_checks(fresh),
                   "abcde scratch dirs").status == preflight.OK
    stale = make_ctx(glob_=lambda pat: ["/r/abcde.111"],
                     mtime=lambda p: 0)
    assert by_name(preflight.run_checks(stale),
                   "abcde scratch dirs").status == preflight.WARN


def test_missing_credentials_warn_but_never_block_a_rip():
    ctx = make_ctx(environ={})
    checks = preflight.run_checks(ctx)
    for var, _ in preflight.CREDENTIALS:
        assert by_name(checks, f"env: {var}").status == preflight.WARN
    assert preflight.worst_status(checks) == preflight.WARN


def test_blank_credential_counts_as_unset():
    ctx = make_ctx(environ={"DISCOGS_TOKEN": "   "})
    assert by_name(preflight.run_checks(ctx),
                   "env: DISCOGS_TOKEN").status == preflight.WARN


def test_unreachable_service_warns_only():
    ctx = make_ctx(fetch=lambda url, timeout=6: (False, "Name or service not known"))
    checks = preflight.run_checks(ctx)
    assert by_name(checks, "net: Discogs").status == preflight.WARN
    assert preflight.worst_status(checks) == preflight.WARN


def test_http_error_still_counts_as_reachable():
    """Discogs 401s without a token and MusicBrainz 400s without a query -
    both prove the host answered, which is all this check claims."""
    ctx = make_ctx(fetch=lambda url, timeout=6: (True, "HTTP 401"))
    check = by_name(preflight.run_checks(ctx), "net: Discogs")
    assert check.status == preflight.OK
    assert check.detail == "HTTP 401"


def test_no_net_flag_skips_the_probes_entirely():
    def explode(url, timeout=6):
        raise AssertionError("network probed despite check_net=False")

    ctx = make_ctx(check_net=False, fetch=explode)
    checks = preflight.run_checks(ctx)
    assert by_name(checks, "network").status == preflight.OK
    assert not [c for c in checks if c.name.startswith("net: ")]


def test_a_crashing_check_becomes_a_failure_not_a_traceback():
    def boom(ctx):
        raise RuntimeError("kaboom")

    checks = preflight.run_checks(make_ctx(), checks=[boom])
    assert checks[0].status == preflight.FAIL
    assert "kaboom" in checks[0].detail


def test_report_prints_the_fix_line_only_for_problems():
    ctx = make_ctx(which=lambda n: None if n == "lame" else f"/usr/bin/{n}")
    text = preflight.format_report(preflight.run_checks(ctx))
    assert "fix: apt-get install lame" in text
    assert text.count("fix:") == 1


# -- catalog outbox (FOCUS.md #8) ---------------------------------------


def test_empty_catalog_outbox_is_ok():
    checks = preflight.run_checks(make_ctx(), checks=[preflight.check_catalog_outbox])
    assert checks[0].status == preflight.OK


def test_queued_catalog_rows_warn_and_name_the_discs():
    pending = [{"row": {"ARTIST": "Belong", "ALBUM": "October Language"}}]
    checks = preflight.run_checks(make_ctx(outbox_pending=lambda: pending),
                                  checks=[preflight.check_catalog_outbox])
    assert checks[0].status == preflight.WARN
    assert "Belong - October Language" in checks[0].detail
    assert "wtul-rip catalog" in checks[0].fix


def test_many_queued_rows_are_summarised_not_dumped():
    pending = [{"row": {"ARTIST": f"A{i}", "ALBUM": f"B{i}"}} for i in range(5)]
    check = preflight.run_checks(make_ctx(outbox_pending=lambda: pending),
                                 checks=[preflight.check_catalog_outbox])[0]
    assert "5 rip(s)" in check.detail
    assert "+2 more" in check.detail
    assert "A4" not in check.detail


def test_unwired_outbox_says_so_rather_than_claiming_empty():
    """A check that can't see the queue must not report a clean rig - that
    is how "all green" stops meaning anything."""
    check = preflight.run_checks(make_ctx(outbox_pending=None),
                                 checks=[preflight.check_catalog_outbox])[0]
    assert check.status == preflight.WARN
    assert "not wired" in check.detail
