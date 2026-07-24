"""Unit tests for phone photo capture (ROADMAP #4).

Network and eyeD3 subprocess calls are mocked throughout - no real HTTP
calls, no real phone, no real audio files.

Run with:  python3 -m pytest tests/ -q
"""
import importlib.util
import json
import os
from unittest.mock import patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODPATH = os.path.join(_HERE, "..", "lib", "photo_capture.py")
_spec = importlib.util.spec_from_file_location("photo_capture", _MODPATH)
pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pc)


class _FakeResponse:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class _FakeCompletedProcess:
    def __init__(self, returncode=0):
        self.returncode = returncode


def test_new_pairing_code_is_url_safe_and_varies():
    a = pc.new_pairing_code()
    b = pc.new_pairing_code()
    assert a != b
    assert len(a) == 8
    assert all(c in "0123456789abcdef" for c in a)


def test_pairing_url_includes_code_and_disc_id():
    url = pc.pairing_url("https://example.com/exec", "abc123", "disc-9")
    assert url.startswith("https://example.com/exec?")
    assert "pairing_code=abc123" in url
    assert "disc_id=disc-9" in url


def test_check_photo_found():
    body = {"found": True, "url": "https://drive.example/x", "disc_id": "disc-9"}
    with patch.object(pc.urllib.request, "urlopen", return_value=_FakeResponse(body)) as mock_open:
        result = pc.check_photo("https://example.com/exec", "abc123")
    assert result == body
    req = mock_open.call_args[0][0]
    assert "scope=photo" in req.full_url
    assert "pairing_code=abc123" in req.full_url


def test_check_photo_not_found():
    with patch.object(pc.urllib.request, "urlopen", return_value=_FakeResponse({"found": False})):
        result = pc.check_photo("https://example.com/exec", "abc123")
    assert result == {"found": False}


def test_check_photo_network_error_returns_none():
    with patch.object(pc.urllib.request, "urlopen", side_effect=OSError("boom")):
        assert pc.check_photo("https://example.com/exec", "abc123") is None


def test_wait_for_photo_returns_immediately_when_found():
    body = {"found": True, "url": "https://drive.example/x"}
    sleeps = []
    with patch.object(pc, "check_photo", return_value=body):
        result = pc.wait_for_photo("https://example.com/exec", "abc123",
                                    timeout=30, interval=5, sleep=sleeps.append)
    assert result == body
    assert sleeps == []


def test_wait_for_photo_polls_until_found():
    responses = [{"found": False}, {"found": False}, {"found": True, "url": "u"}]
    sleeps = []
    with patch.object(pc, "check_photo", side_effect=responses):
        result = pc.wait_for_photo("https://example.com/exec", "abc123",
                                    timeout=30, interval=5, sleep=sleeps.append)
    assert result == {"found": True, "url": "u"}
    assert sleeps == [5, 5]


def test_wait_for_photo_gives_up_after_timeout():
    call_count = {"n": 0}
    fake_time = [0]

    def fake_monotonic():
        return fake_time[0]

    def fake_sleep(secs):
        fake_time[0] += secs

    with patch.object(pc, "check_photo", return_value={"found": False}), \
         patch.object(pc.time, "monotonic", side_effect=fake_monotonic):
        result = pc.wait_for_photo("https://example.com/exec", "abc123",
                                    timeout=12, interval=5, sleep=fake_sleep)
    assert result is None


def test_download_image_success(tmp_path):
    dest = tmp_path / "cover.jpg"
    with patch.object(pc.urllib.request, "urlopen", return_value=_FakeResponse(b"\xff\xd8fakejpeg")):
        assert pc.download_image("https://drive.example/x", str(dest)) is True
    assert dest.read_bytes() == b"\xff\xd8fakejpeg"


def test_download_image_network_error_returns_false(tmp_path):
    dest = tmp_path / "cover.jpg"
    with patch.object(pc.urllib.request, "urlopen", side_effect=OSError("boom")):
        assert pc.download_image("https://drive.example/x", str(dest)) is False
    assert not dest.exists()


def test_embed_album_art_all_succeed():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _FakeCompletedProcess(returncode=0)

    ok, failed = pc.embed_album_art("/tmp/cover.jpg", ["/tmp/1.mp3", "/tmp/2.mp3"], run=fake_run)
    assert ok == ["/tmp/1.mp3", "/tmp/2.mp3"]
    assert failed == []
    assert calls[0] == ["eyeD3", "--add-image", "/tmp/cover.jpg:FRONT_COVER", "/tmp/1.mp3"]


def test_embed_album_art_partial_failure():
    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(returncode=0 if cmd[-1] == "/tmp/1.mp3" else 1)

    ok, failed = pc.embed_album_art("/tmp/cover.jpg", ["/tmp/1.mp3", "/tmp/2.mp3"], run=fake_run)
    assert ok == ["/tmp/1.mp3"]
    assert failed == ["/tmp/2.mp3"]


def test_embed_album_art_subprocess_error_counts_as_failure():
    def fake_run(cmd, **kwargs):
        raise OSError("eyeD3 not found")

    ok, failed = pc.embed_album_art("/tmp/cover.jpg", ["/tmp/1.mp3"], run=fake_run)
    assert ok == []
    assert failed == ["/tmp/1.mp3"]


def test_associate_photo_no_photo_found():
    with patch.object(pc, "wait_for_photo", return_value=None):
        result = pc.associate_photo("https://example.com/exec", "abc123", "/tmp", ["/tmp/1.mp3"],
                                     sleep=lambda s: None)
    assert result == {"status": "no_photo", "pairing_code": "abc123"}


def test_associate_photo_download_fails():
    with patch.object(pc, "wait_for_photo", return_value={"found": True, "url": "https://drive.example/x"}), \
         patch.object(pc, "download_image", return_value=False):
        result = pc.associate_photo("https://example.com/exec", "abc123", "/tmp", ["/tmp/1.mp3"],
                                     sleep=lambda s: None)
    assert result == {"status": "download_failed", "pairing_code": "abc123"}


def test_associate_photo_embeds_successfully(tmp_path):
    with patch.object(pc, "wait_for_photo", return_value={"found": True, "url": "https://drive.example/x"}), \
         patch.object(pc, "download_image", return_value=True) as mock_dl, \
         patch.object(pc, "embed_album_art", return_value=(["/tmp/1.mp3"], [])) as mock_embed:
        result = pc.associate_photo("https://example.com/exec", "abc123", str(tmp_path), ["/tmp/1.mp3"],
                                     sleep=lambda s: None)
    assert result["status"] == "embedded"
    assert result["embedded"] == ["/tmp/1.mp3"]
    assert result["failed"] == []
    mock_dl.assert_called_once()
    mock_embed.assert_called_once()


def test_associate_photo_partial_embed():
    with patch.object(pc, "wait_for_photo", return_value={"found": True, "url": "https://drive.example/x"}), \
         patch.object(pc, "download_image", return_value=True), \
         patch.object(pc, "embed_album_art", return_value=([], ["/tmp/1.mp3"])):
        result = pc.associate_photo("https://example.com/exec", "abc123", "/tmp", ["/tmp/1.mp3"],
                                     sleep=lambda s: None)
    assert result["status"] == "partial"
    assert result["failed"] == ["/tmp/1.mp3"]
