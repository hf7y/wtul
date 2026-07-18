# Roadmap — deeper integrations

Not implemented yet. Each needs research/design/hardware access before
building, unlike the easy fixes that went straight into `bin/wtul-rip`.

## 1. Spinitron integration - prioritize already-played tracks

**Status (2026-07-18, branch `spinitron-priority-matching`):** the
hardware-free core is built and unit-tested in `lib/spinitron.py`
(`tests/test_spinitron.py`): fuzzy artist+title matching (difflib, with
qualifier/punctuation normalization), the queue reorder that mirrors
`apply_live_input`'s `front + rest`, and a thin read-only `/api/spins`
client. NOT yet wired into `rip_session()` and never run against the live
API - that needs the station's Spinitron API key + station ID, which only
the user can supply (flagged in `.claude/QUESTIONS.md`). Once the key
exists, wiring is: after the metadata scrape, `spins = fetch_recent_spins(key)`
then `queue = reorder_queue(queue, matched_track_numbers(titles, artist, spins))`.
The 0.82 match threshold is a first guess to tune against real spin data.

Idea: check a disc's tracks against Spinitron's play history for the
station; if a track was already logged as played on air, prioritize
ripping it first (same mechanism as the manual `5 2` live-priority
command, just auto-populated instead of typed).

Needs before starting:
- Station's Spinitron API key + station ID (Settings > API in Spinitron).
- Spinitron's public read API is documented at `developer.spinitron.com` -
  `GET /api/spins` returns play history with artist/song/release fields.
- Matching strategy: fuzzy artist+title match between Spinitron spins and
  the CDDB/MusicBrainz-scraped tracklist (exact string match will miss
  punctuation/case differences - probably want something like
  `difflib.SequenceMatcher` or a proper fuzzy-match library).
- Where it plugs in: after the metadata scrape in `rip_session()`, before
  building the initial `queue` - reorder tracks whose artist+title match a
  recent spin to the front, same as `apply_live_input`'s reorder logic.

## 2. External API to fix metadata on already-ripped unidentified discs

Idea: extend the `fix <discid>` command so it can look up the correct
metadata automatically instead of only accepting manual artist/album entry.

Needs before starting:
- Decide the identification method - CDDB/MusicBrainz disc-TOC lookup
  already failed once for these (that's why they're "unidentified"), so
  this needs a different approach:
  - AcoustID/Chromaprint audio fingerprinting (identifies from the actual
    audio content, not just track lengths) - needs `fpcalc` installed and
    an AcoustID API key.
  - Or Discogs API as a secondary catalog lookup by disc/release search.
- Rate limits and API keys for whichever service is chosen.
- Reuse `fix_by_discid()`'s retag/move logic once a name is found - only
  the "ask the user" step gets replaced with an API call.

## 3. Label printer integration - seamless tagging

Idea: once a disc finishes ripping, automatically print a physical label
(artist/album/tracklist, maybe a QR code encoding the disc ID for
`fix <discid>` lookups later) for the CD/case.

Needs before starting:
- Which printer/hardware - model matters a lot (Dymo LabelWriter vs
  Brother QL vs a dedicated CD/DVD label printer like a Primera have
  completely different driver/SDK situations on Linux).
- CUPS availability and driver support for whatever's chosen.
- Label template/layout design once the hardware is known.

## 4. Web app + phone photo capture for album art

Idea: a small web app you open on your phone that lets you snap a photo
of the physical CD/album art and associates it with the current or a past
rip (embedded as album art in the mp3s, matched by disc ID).

Needs before starting:
- Hosting: something reachable from a phone on the same network as this
  machine (a small Flask/FastAPI server bound to the LAN, or reuse the
  Artifact tool's capabilities if a hosted approach is preferred).
- Association mechanism: simplest is probably a short-lived pairing code
  or QR code shown by `wtul-rip` at rip time, scanned by the phone to
  link the upload to that disc ID.
- Embedding: abcde already supports `EMBEDALBUMART`/`GETALBUMART` actions -
  once a photo lands as a file, it can likely reuse that pipeline instead
  of hand-rolling ID3 APIC frame writes.

## 5. Instrumental intro/outro detection

Idea: detect the instrumental-only sections at the start/end of each
track (useful for on-air talk-over timing).

Needs before starting:
- An actual detection approach - this is a real DSP/audio-analysis
  problem, not a metadata one. Candidates: vocal-activity detection via
  a library like `librosa` (spectral features) or a pretrained
  vocal/instrumental separation model (e.g. Spleeter, Demucs) run just
  long enough to get an activity envelope rather than a full separation.
  Both are heavier dependencies than anything else in this project.
- Where results would live - presumably written into an ID3 comment tag,
  a sidecar file, or Spinitron cue-in notes; needs a decision once the
  detection approach is picked.
- Compute cost: worth checking whether this runs per-track at rip time
  (adds real time per track) or as a separate offline batch pass over
  the library later.

## 6. Monitor and improve ripping speed

Idea: surface actual rip throughput (cdparanoia reports an extraction
speed multiplier, e.g. "4.2x") so slow rips are visible instead of just
"it's taking a while," and use that to decide whether the bottleneck is
worth fixing via hardware (a faster/better drive) or software (a lower
encode quality/bitrate trades CPU+time for size).

Needs before starting:
- Parse cdparanoia's speed output per track (it prints a running
  extraction-speed multiplier - need to check exact format across the
  runs already logged in `~/Music/ripped/.logs/` for the regex to match).
- Decide what "monitoring" means concretely: live display during the
  existing `sh_live` streaming (cheap - just surface a number that's
  already in the output), vs. persisted stats across rips to spot
  degradation over time (needs a small stats log/store).
- If it turns out software-side, `LAMEOPTS` in `abcde.conf` is the knob
  (currently `-V 2`; a faster preset or lower quality trades encode time
  for size/quality) - but drive read speed (cdparanoia) is likely the
  actual bottleneck, not LAME encode speed, so measure before assuming
  which one to change.

## 7. OCR on the photo-scan layer for metadata generation

Idea: extend the phone-photo album art feature (#4 above) so the photo
isn't just embedded art - OCR the cover for artist/title/tracklist text
as another metadata source, useful especially for unidentified discs
where CDDB/MusicBrainz have nothing.

Needs before starting:
- Depends on #4 existing first (the photo capture/association pipeline).
- An OCR engine - Tesseract (`tesseract-ocr` + `pytesseract`) is the
  obvious local/offline default; cloud OCR APIs are an alternative if
  accuracy on stylized album-cover fonts turns out to be poor.
- OCR'd text would be messy/unstructured - needs a step to turn raw OCR
  output into actual artist/album/tracklist fields (fuzzy-match against
  MusicBrainz results, or just present it to the user as a suggestion
  they confirm/edit rather than trusting it blindly).

## 8. Auto-update the local music catalog spreadsheet

Idea: there's an existing spreadsheet cataloging the local music
collection. As `wtul-rip` completes discs, automatically add/update rows
for what was just ripped instead of that being a separate manual step.

Needs before starting:
- Where the spreadsheet actually lives and its format (Google Sheets,
  local .xlsx/.csv, something else) - determines the integration
  approach entirely (Google Sheets API + OAuth vs. just writing a local
  file with `openpyxl`/`csv`).
- The spreadsheet's existing column schema, so new rows match rather
  than needing a manual reconciliation pass later.
- Whether updates should happen live per-disc (as each rip finishes) or
  as a periodic batch job scanning `~/Music/ripped/` against the sheet.
