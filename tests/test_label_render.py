"""Unit tests for the Phomemo M02 label renderer (ROADMAP #3).

`render_label()` is pure PIL image generation - no BLE/network, safe to
exercise fully without the printer present. `print_label()`'s actual BLE
call is mocked via a stub `catprint_bin`; never touches real hardware.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import os
import stat

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "lib", "label_render.py")
_spec = importlib.util.spec_from_file_location("label_render", _MODPATH)
lr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lr)


def test_render_label_basic_width():
    image = lr.render_label("Radiohead", "OK Computer")
    assert image.width == lr.PRINTER_WIDTH
    assert image.height > 0


def test_render_label_with_tracklist_and_discid():
    image = lr.render_label(
        "Radiohead", "OK Computer",
        tracklist=["Airbag", "Paranoid Android", "Subterranean Homesick Alien"],
        discid="abc12345")
    assert image.width == lr.PRINTER_WIDTH
    # QR code (width x width) plus the text block above it.
    assert image.height > lr.PRINTER_WIDTH


def test_render_label_without_discid_has_no_qr_block():
    with_qr = lr.render_label("A", "B", discid="deadbeef")
    without_qr = lr.render_label("A", "B")
    assert with_qr.height > without_qr.height


def test_render_label_handles_missing_metadata():
    image = lr.render_label(None, None)
    assert image.width == lr.PRINTER_WIDTH
    assert image.height > 0


def test_render_label_handles_long_track_titles():
    image = lr.render_label(
        "Artist", "Album",
        tracklist=["A " * 60])  # forces wrapping across many lines
    assert image.width == lr.PRINTER_WIDTH


def test_render_label_columns_splits_tracklist_in_half():
    tracks = [f"Track {n}" for n in range(1, 15)]  # 14 tracks, matches tonight's real mix count
    strips = lr.render_label_columns("WTUL", "Local Show 2026-07-24", tracklist=tracks, discid="mix-1")
    assert len(strips) == 2
    for strip in strips:
        assert strip.width == lr.PRINTER_WIDTH
        assert strip.height > 0


def test_render_label_columns_qr_only_on_last_strip():
    tracks = ["A", "B", "C", "D"]
    with_discid = lr.render_label_columns("Artist", "Album", tracklist=tracks, discid="deadbeef")
    without_discid_last = lr.render_label("Artist (cont'd)", "Album", tracklist=tracks[2:])
    # last strip should be taller than the no-QR equivalent (it's carrying the QR block).
    assert with_discid[-1].height > without_discid_last.height


def test_render_label_columns_no_tracklist_returns_one_strip():
    strips = lr.render_label_columns("Artist", "Album")
    assert len(strips) == 1


def test_print_label_missing_catprint_binary(tmp_path):
    image = lr.render_label("Artist", "Album")
    ok, reason = lr.print_label(image, catprint_bin=str(tmp_path / "no-such-binary"))
    assert ok is False
    assert "not found" in reason


def test_print_label_success_with_stub_binary(tmp_path):
    stub = tmp_path / "fake-catprint"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    image = lr.render_label("Artist", "Album")
    ok, reason = lr.print_label(image, catprint_bin=str(stub))
    assert ok is True
    assert reason is None


def test_print_label_failure_with_stub_binary(tmp_path):
    stub = tmp_path / "fake-catprint-fail"
    stub.write_text("#!/bin/sh\necho 'no bluetooth adapter' >&2\nexit 1\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    image = lr.render_label("Artist", "Album")
    ok, reason = lr.print_label(image, catprint_bin=str(stub))
    assert ok is False
    assert "bluetooth" in reason
