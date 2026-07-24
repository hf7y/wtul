"""Unit tests for lib/ocr_metadata.py (ROADMAP #7). All subprocess calls
are mocked - no real tesseract binary needed to exercise this logic (it
isn't installed on this machine as of 2026-07-24, see the module
docstring), same convention as test_metadata_lookup.py before fpcalc was
installed for ROADMAP #2.

Run with:  python3 -m pytest tests/ -q
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import ocr_metadata


# --- find_cover_image ---

def test_find_cover_image_missing_dir(tmp_path):
    assert ocr_metadata.find_cover_image(str(tmp_path / "nope")) is None


def test_find_cover_image_no_cover(tmp_path):
    (tmp_path / "01-track.mp3").write_bytes(b"")
    assert ocr_metadata.find_cover_image(str(tmp_path)) is None


def test_find_cover_image_finds_jpg(tmp_path):
    (tmp_path / "cover.jpg").write_bytes(b"fake")
    assert ocr_metadata.find_cover_image(str(tmp_path)) == str(tmp_path / "cover.jpg")


def test_find_cover_image_case_insensitive(tmp_path):
    (tmp_path / "COVER.PNG").write_bytes(b"fake")
    found = ocr_metadata.find_cover_image(str(tmp_path))
    assert found == str(tmp_path / "COVER.PNG")


def test_find_cover_image_prefers_first_match_in_list(tmp_path):
    (tmp_path / "cover.jpg").write_bytes(b"fake")
    (tmp_path / "cover.png").write_bytes(b"fake")
    found = ocr_metadata.find_cover_image(str(tmp_path))
    assert found == str(tmp_path / "cover.jpg")


# --- ocr_image ---

def test_ocr_image_missing_file(tmp_path):
    assert ocr_metadata.ocr_image(str(tmp_path / "nope.jpg")) is None


def test_ocr_image_missing_binary(tmp_path, monkeypatch):
    image = tmp_path / "cover.jpg"
    image.write_bytes(b"fake")

    def fake_run(*a, **k):
        raise FileNotFoundError("no tesseract")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert ocr_metadata.ocr_image(str(image)) is None


def test_ocr_image_timeout(tmp_path, monkeypatch):
    image = tmp_path / "cover.jpg"
    image.write_bytes(b"fake")

    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="tesseract", timeout=30)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert ocr_metadata.ocr_image(str(image)) is None


def test_ocr_image_nonzero_exit(tmp_path, monkeypatch):
    image = tmp_path / "cover.jpg"
    image.write_bytes(b"fake")

    class FakeProc:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc())
    assert ocr_metadata.ocr_image(str(image)) is None


def test_ocr_image_success(tmp_path, monkeypatch):
    image = tmp_path / "cover.jpg"
    image.write_bytes(b"fake")

    class FakeProc:
        returncode = 0
        stdout = "Some Artist\nSome Album\n"

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    text = ocr_metadata.ocr_image(str(image), tesseract_bin="tesseract")
    assert text == "Some Artist\nSome Album\n"
    assert captured["cmd"] == ["tesseract", str(image), "stdout"]


# --- clean_ocr_lines ---

def test_clean_ocr_lines_none():
    assert ocr_metadata.clean_ocr_lines(None) == []


def test_clean_ocr_lines_empty_string():
    assert ocr_metadata.clean_ocr_lines("") == []


def test_clean_ocr_lines_strips_and_drops_short_noise():
    text = "  Radiohead  \n\n.\nab\nOK Computer\n \n"
    assert ocr_metadata.clean_ocr_lines(text) == ["Radiohead", "OK Computer"]


def test_clean_ocr_lines_collapses_consecutive_duplicates():
    text = "Radiohead\nRadiohead\nOK Computer"
    assert ocr_metadata.clean_ocr_lines(text) == ["Radiohead", "OK Computer"]


def test_clean_ocr_lines_keeps_nonconsecutive_duplicates():
    text = "Radiohead\nOK Computer\nRadiohead"
    assert ocr_metadata.clean_ocr_lines(text) == ["Radiohead", "OK Computer", "Radiohead"]


def test_clean_ocr_lines_caps_length():
    text = "\n".join(f"line{i}" for i in range(50))
    lines = ocr_metadata.clean_ocr_lines(text, max_lines=5)
    assert lines == ["line0", "line1", "line2", "line3", "line4"]


# --- ocr_cover_candidates (integration of the above three) ---

def test_ocr_cover_candidates_no_cover(tmp_path):
    assert ocr_metadata.ocr_cover_candidates(str(tmp_path)) == []


def test_ocr_cover_candidates_tesseract_missing(tmp_path, monkeypatch):
    (tmp_path / "cover.jpg").write_bytes(b"fake")

    def fake_run(*a, **k):
        raise FileNotFoundError("no tesseract")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert ocr_metadata.ocr_cover_candidates(str(tmp_path)) == []


def test_ocr_cover_candidates_success(tmp_path, monkeypatch):
    (tmp_path / "cover.jpg").write_bytes(b"fake")

    class FakeProc:
        returncode = 0
        stdout = "Radiohead\n\nOK Computer\nOK Computer\n"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeProc())
    assert ocr_metadata.ocr_cover_candidates(str(tmp_path)) == ["Radiohead", "OK Computer"]
