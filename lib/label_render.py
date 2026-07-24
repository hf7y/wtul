"""Render a CD/case label image for the Phomemo M02 thermal printer
(ROADMAP #3). `print_label()` in this module is the only piece that
touches real BLE hardware (via `~/.local/bin/catprint`, which wraps
`~/.local/share/catprinter/m02print.py`) - everything else is pure
image rendering, safely unit-testable without the printer present.

Text layout: artist/album/tracklist top to bottom, word-wrapped to the
printer's fixed 384px width, followed by a QR code (when a disc ID is
given) encoding a `wtul:<discid>` URI for later `fix <discid>` lookups.
"""
import os
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont

PRINTER_WIDTH = 384
_FONT_PATHS = {
    "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
}


def _font(kind, size):
    """Falls back to PIL's built-in bitmap font if DejaVu isn't
    installed on this machine - never raises, since a slightly uglier
    label beats a crashed print job."""
    path = _FONT_PATHS.get(kind, _FONT_PATHS["regular"])
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _draw_wrapped(draw, y, text, font, width_chars, fill="black", line_spacing=4):
    """Word-wraps `text` to `width_chars` and draws each line centered,
    returning the y position just below the last line drawn."""
    for line in textwrap.wrap(text, width=width_chars) or [""]:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]
        x = max(0, (PRINTER_WIDTH - line_width) // 2)
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height + line_spacing
    return y


def render_label(artist, album, tracklist=None, discid=None, width=PRINTER_WIDTH):
    """Renders a label image for one ripped disc. `artist`/`album` are
    required; `tracklist` (a list of track title strings) and `discid`
    are both optional and simply omitted from the layout if not given.
    Returns a PIL Image in mode "1" (1-bit), matching what
    `m02print.py`'s `build_commands` converts to anyway - doing it here
    means what this function returns is exactly what would print.
    """
    artist = artist or "Unknown Artist"
    album = album or "Unknown Album"
    tracklist = tracklist or []

    title_font = _font("bold", 28)
    body_font = _font("regular", 20)
    track_font = _font("regular", 16)

    qr_img = None
    if discid:
        import qrcode
        qr_img = qrcode.make(f"wtul:{discid}", border=2)
        qr_img = qr_img.resize((width, width))

    # Estimate height with a throwaway draw context first (PIL needs an
    # image to measure text against), then render for real onto an image
    # sized to fit everything without leftover blank space.
    probe = Image.new("1", (width, 10), 1)
    probe_draw = ImageDraw.Draw(probe)
    y = 10
    y = _draw_wrapped(probe_draw, y, artist, title_font, width_chars=20) + 6
    y = _draw_wrapped(probe_draw, y, album, body_font, width_chars=26) + 10
    for track in tracklist:
        y = _draw_wrapped(probe_draw, y, track, track_font, width_chars=32, line_spacing=2)
    y += 10
    if qr_img:
        y += qr_img.height + 10

    image = Image.new("1", (width, int(y)), 1)
    draw = ImageDraw.Draw(image)
    y = 10
    y = _draw_wrapped(draw, y, artist, title_font, width_chars=20) + 6
    y = _draw_wrapped(draw, y, album, body_font, width_chars=26) + 10
    for track in tracklist:
        y = _draw_wrapped(draw, y, track, track_font, width_chars=32, line_spacing=2)
    y += 10
    if qr_img:
        image.paste(qr_img, (0, int(y)))

    return image


def print_label(image, catprint_bin=None, timeout=30):
    """Shells out to `catprint` (the BLE thermal-printer CLI) with the
    rendered image. Returns (True, None) on a clean exit, or
    (False, reason) on any failure - never raises, since a missing
    printer/BLE adapter must not abort a rip session. `catprint_bin`
    defaults to `~/.local/bin/catprint`, overridable for testing.
    """
    catprint_bin = catprint_bin or os.path.join(
        os.path.expanduser("~"), ".local", "bin", "catprint")
    if not os.path.isfile(catprint_bin):
        return False, f"catprint not found at {catprint_bin}"
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        image.save(tmp.name)
        tmp_path = tmp.name
    try:
        proc = subprocess.run([catprint_bin, tmp_path], capture_output=True,
                               timeout=timeout, text=True)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)
    finally:
        os.unlink(tmp_path)
    if proc.returncode != 0:
        return False, proc.stderr.strip() or f"catprint exited {proc.returncode}"
    return True, None
