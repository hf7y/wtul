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
import re
import subprocess
import textwrap

from PIL import Image, ImageDraw, ImageFont

_GENERIC_TITLE_RE = re.compile(r"^Track\s*\d+$", re.IGNORECASE)
ENTRY_GAP = 40  # px of vertical breathing room between mix-label track entries

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


def _wrap_to_pixel_width(draw, text, font, max_width_px):
    """Word-wraps by measured pixel width rather than character count -
    textwrap.wrap's char-count wrapping doesn't track a real column width
    once margins carve down the usable area, so long words/lines miss the
    actual edge. Falls back to one line if a single word alone is wider
    than max_width_px (never splits mid-word)."""
    words = text.split()
    if not words:
        return [""]
    lines, current = [], words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width_px:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_left(draw, x, y, text, font, max_width_px, fill="black", line_spacing=6):
    """Left-aligned text at (x, y), pixel-width-wrapped to max_width_px.
    Returns the y position just below the last line drawn."""
    for line in _wrap_to_pixel_width(draw, text, font, max_width_px):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_height = bbox[3] - bbox[1]
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height + line_spacing
    return y


def render_mix_label(tracks, header_line=None, discid=None, width=PRINTER_WIDTH,
                      margin_frac=0.15, font_size=32):
    """Renders a compilation-mix label: a numbered, left-aligned,
    newline-separated entry per track (no per-album "Track N" filler
    title, no bold station/artist header - see live feedback
    2026-07-24 on the first print of this session). `tracks` is
    mix_label.collect_mix_tracks()'s output (title/artist/album/
    duration/genre/year dicts) so the numbering matches burn order
    exactly - that's the actual point of the label, indexing into the
    burned disc's file order, not song identification.

    Per-track entry, one field per line (blank fields simply don't get a
    line - never printed as a placeholder):
        N. Title - Artist      (or "N. Artist" if title is the generic
                                 "Track N" abcde falls back to - not a
                                 real title, so it's dropped rather than
                                 printed as noise)
        Album - m:ss
        Genre
        Year
    `header_line` (e.g. "Local Show 2026-07-24") is optional and, unlike
    render_label(), has no separate artist/station line above it - that
    line was cut entirely per the same feedback, not merged into this
    one.
    """
    margin = int(width * margin_frac)
    usable = width - 2 * margin
    font = _font("regular", font_size)

    qr_img = None
    if discid:
        import qrcode
        qr_size = usable
        qr_img = qrcode.make(f"wtul:{discid}", border=2).resize((qr_size, qr_size))

    def entry_lines(t):
        lines = []
        title = (t.get("title") or "").strip()
        if title and not _GENERIC_TITLE_RE.match(title):
            lines.append(f"{t['n']}. {title} - {t['artist']}")
        else:
            lines.append(f"{t['n']}. {t['artist']}")
        mins, secs = divmod(int(t["duration"]), 60)
        lines.append(f"{t['album']} - {mins}:{secs:02d}")
        if t.get("genre"):
            lines.append(t["genre"])
        if t.get("year"):
            lines.append(str(t["year"]))
        return lines

    numbered = [{"n": i + 1, **t} for i, t in enumerate(tracks)]

    def draw_entries(draw, y):
        for i, t in enumerate(numbered):
            for line in entry_lines(t):
                y = _draw_left(draw, margin, y, line, font, usable, line_spacing=10)
            if i < len(numbered) - 1:
                # Generous gap + a ruled line between entries - tight spacing with
                # no visual break between tracks was flagged live 2026-07-24 as
                # "terrible, not usable" on the first print of this layout.
                y += ENTRY_GAP // 2
                draw.line([(margin, y), (margin + usable, y)], fill="black", width=2)
                y += ENTRY_GAP // 2
            else:
                y += ENTRY_GAP
        return y

    def render_pass(draw):
        y = 20
        if header_line:
            y = _draw_left(draw, margin, y, header_line, font, usable, line_spacing=10) + ENTRY_GAP
        y = draw_entries(draw, y)
        if qr_img:
            y += qr_img.height + 20
        return y

    probe = Image.new("1", (width, 10), 1)
    total_height = render_pass(ImageDraw.Draw(probe))

    image = Image.new("1", (width, int(total_height)), 1)
    draw = ImageDraw.Draw(image)
    y = 20
    if header_line:
        y = _draw_left(draw, margin, y, header_line, font, usable, line_spacing=10) + ENTRY_GAP
    y = draw_entries(draw, y)
    if qr_img:
        image.paste(qr_img, (margin, int(y)))

    return image


def render_mix_label_columns(tracks, header_line=None, discid=None, width=PRINTER_WIDTH,
                              margin_frac=0.15, font_size=32):
    """render_mix_label(), split into two strips to print separately and
    tape side-by-side (same reasoning as render_label_columns() - see
    that docstring). Track numbering stays continuous across both
    strips (burn-order index, not restarted per strip); only the second
    strip carries the QR code."""
    half = -(-len(tracks) // 2)
    chunks = [tracks[:half], tracks[half:]] if tracks else [[]]
    strips = []
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        offset = sum(len(c) for c in chunks[:i])
        numbered_chunk = [dict(t, n=offset + j + 1) for j, t in enumerate(chunk)]
        strip_header = header_line if i == 0 else (f"{header_line} (cont'd)" if header_line else None)
        strips.append(render_mix_label(
            [dict(t) for t in numbered_chunk], header_line=strip_header,
            discid=discid if is_last else None, width=width,
            margin_frac=margin_frac, font_size=font_size))
    return strips


def render_label_columns(artist, album, tracklist=None, discid=None, width=PRINTER_WIDTH):
    """Same content as render_label(), split into multiple narrow strips
    meant to be printed separately and taped side-by-side - the M02's
    print width is fixed at 384px, so a long tracklist (e.g. a 14-track
    mix compilation) prints as one very long, awkward strip rather than
    something that fits a CD case. Returns a list of PIL Images, one per
    strip: strip 1 carries the artist/album header plus roughly the
    first half of the tracklist; strip 2+ carry the rest (a "(cont'd)"
    marker instead of repeating the header) and the QR code (if any) on
    the last strip. Alignment when pasting is manual - this only splits
    the content, it doesn't attempt to align cut lines physically.
    """
    tracklist = tracklist or []
    half = -(-len(tracklist) // 2)  # ceil division - first half gets the extra track on an odd count
    chunks = [tracklist[:half], tracklist[half:]] if tracklist else [[]]

    strips = []
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        if i == 0:
            strips.append(render_label(artist, album, tracklist=chunk,
                                        discid=discid if is_last else None, width=width))
        else:
            strips.append(render_label(f"{artist} (cont'd)", album, tracklist=chunk,
                                        discid=discid if is_last else None, width=width))
    return strips


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
