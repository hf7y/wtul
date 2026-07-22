# Roadmap — deeper integrations

Not implemented yet. Each needs research/design/hardware access before
building, unlike the easy fixes that went straight into `bin/wtul-rip`.

## Vision: the full lifecycle (2026-07-20)

The end-to-end loop this backlog is building toward: **play something on
air → it gets auto-ripped right after airplay → later curation pulls
favorites from that pile into a mix → the mix gets burned to a fresh CD
with a printed label → that CD enters the station's rotation catalog.**
Not one feature - a pipeline, and most of the numbered items below are
already a piece of it once unblocked:

- **Capture-on-play** (new, see #9) - the not-yet-designed front end:
  something played during a show gets ripped automatically, without
  someone manually feeding a physical disc into `wtul-rip` the way the
  tool works today. #1's Spinitron spin-matching already gives a
  "this was just played" signal - #9 is figuring out how that turns into
  actual captured audio.
- **Curation** - manual, no roadmap item yet (a person picks favorites
  from the capture pile and assembles a mix) - not blocking anything else.
- **Burn + label** - burning is out of scope for `wtul-rip` (it's a
  ripper, not a burner) but **#3's Phomemo M02 label printer is the label
  half**, once a mix is burned by hand.
- **Re-enter rotation** - **#8's catalog spreadsheet** is where a
  newly-burned mix CD gets logged back in as a real rotation item.

So #3, #8, and (once designed) #9 are the pipeline; #2/#4/#5/#7 are
independent quality-of-life items on the ripping side, not part of this
loop.

## 1. Spinitron integration - prioritize already-played tracks

**Status (2026-07-20, branch `spinitron-priority-matching`):** done and
unblocked without the official API. The station's `/api/spins` needs a key
issued by station management, which turned out not to be obtainable without
going through them directly - confirmed 2026-07-19. Unblocked instead by
`fetch_recent_spins_public()` in `lib/spinitron.py`, which scrapes
`spinitron.com/WTUL/` (the same public, no-login page the WTUL website's
own "currently playing" widget uses) for the JSON blob embedded in each
spin's `data-spin` attribute. Wired unconditionally into `rip_session()` in
`bin/wtul-rip` right after the queue is built - no env var/key needed; a
network/scrape failure is caught and logged, never aborts the rip. Live-
verified against the real page 2026-07-20 (see `tests/test_spinitron.py`
for the parsing tests, `tests/test_wiring.py` for the module-load smoke
test). The 0.82 match threshold is still a first guess - worth tuning once
a real rip has run through it a few times. `fetch_recent_spins(api_key,
...)` (the official API client) is left in place unused, in case the
station ever does grant a key.

Idea: check a disc's tracks against Spinitron's play history for the
station; if a track was already logged as played on air, prioritize
ripping it first (same mechanism as the manual `5 2` live-priority
command, just auto-populated instead of typed).

Needs before starting:
- ~~Station's Spinitron API key + station ID~~ - not needed; see Status
  above.
- Matching strategy: fuzzy artist+title match between Spinitron spins and
  the CDDB/MusicBrainz-scraped tracklist (exact string match will miss
  punctuation/case differences - probably want something like
  `difflib.SequenceMatcher` or a proper fuzzy-match library).
- Where it plugs in: after the metadata scrape in `rip_session()`, before
  building the initial `queue` - reorder tracks whose artist+title match a
  recent spin to the front, same as `apply_live_input`'s reorder logic.

## 2. External API to fix metadata on already-ripped unidentified discs

**Status (2026-07-20): built and wired, partially live.** AcoustID key
obtained (app "Local Show") and stored at `~/.config/wtul/secrets.env`
(gitignored-by-location, never committed - `bin/wtul-rip` loads it at
startup via `os.environ.setdefault`, real env vars still win). Discogs
token not obtained yet - the fallback path is built and tested but a
silent no-op until `DISCOGS_TOKEN` exists, same pattern as the AcoustID
key itself would've been.

`lib/metadata_lookup.py` (new, 15 unit tests, all mocked - no real
network/audio) fingerprints each ripped track with `fpcalc`, queries
AcoustID, takes a majority vote across tracks for the album (and
separately for the artist, since a disc can have artist consensus
without any single track carrying a releasegroup title), then falls back
to a Discogs artist-catalog search if AcoustID found an artist but not a
confident album. `fix_by_discid()` in `bin/wtul-rip` now runs this before
its manual prompt and offers the result as a suggestion (blank input
accepts it) rather than auto-applying it - fuzzy matching stays
confirm/edit, never blind, same principle #7 later calls for on OCR
output.

**Not yet live-verified**: `fpcalc` (Chromaprint) still isn't installed
on this machine - asked the user to run
`sudo apt install -y libchromaprint-tools` (needs an interactive sudo
prompt this session couldn't provide). Until then `resolve_disc_metadata`
degrades to its safe no-op (falls straight through to the existing
manual prompt), same as before this session's work.

Idea: extend the `fix <discid>` command so it can look up the correct
metadata automatically instead of only accepting manual artist/album entry.

Needs before starting:
- ~~`fpcalc` (Chromaprint) installed~~ - still pending, see Status above.
- ~~AcoustID API key~~ - obtained, see Status above.
- A Discogs personal access token (self-serve at discogs.com) - not
  obtained yet; the fallback path is ready and waiting on it.
- Rate limits for both - check before hammering either on a whole backlog
  of unidentified discs at once (not yet exercised against real volume).

## 3. Label printer integration - seamless tagging

**Decision (2026-07-20): Phomemo M02** (BLE thermal receipt/label printer).
Not a fresh integration - it's already been hacked working elsewhere on
this machine: `~/.local/bin/catprint` wraps
`~/.local/share/catprinter/m02print.py` (Bleak BLE client, builds raw
ESC/POS-ish command bytes from a PIL image, `--device` defaults to a
paired MAC `EA:F3:B6:A2:70:33`). `~/.local/bin/phomemo_printer` is a
second, separate `phomemo_printer` pip package's CLI - both exist, pick
whichever is more reliable once actually exercised for this. Ready to
build: no more hardware/driver research needed, just (a) render a label
image (artist/album/tracklist, maybe a QR code encoding the disc ID for
`fix <discid>` lookups later - Pillow can do both the text layout and QR
if a `qrcode` lib is added) sized to the M02's ~384px print width (see
`m02print.py`'s `resize`), then (b) shell out to `catprint <path>` (or
call `m02print.py` directly) once a rip finishes. Per the pipeline vision
above, this printer is also the label half of the "burn a curated mix,
print its label" loop (#8), not just per-disc labels for `wtul-rip`
itself - worth designing the image-render step generically enough to
serve both.

Idea: once a disc finishes ripping, automatically print a physical label
(artist/album/tracklist, maybe a QR code encoding the disc ID for
`fix <discid>` lookups later) for the CD/case.

## 4. Web app + phone photo capture for album art

**Decision (2026-07-20): host in Google Apps Script**, reusing the
existing GAS project already backing
[this sheet](https://docs.google.com/spreadsheets/d/1GzIbZUhn6fF7JPC20kdG2IMomvZlDBidDTy5cDEF3U8/edit?gid=1753821521#gid=1753821521)
and deployed at `hf7y.com/localshow.html` (forwards to the script's `/exec`
link) - not a new Flask/FastAPI service. This is the same
"static-page-that-forwards-to-a-GAS-`/exec`-endpoint" shape `vkv-inventory`
and `chezz` already use (see the scheduler's `INTAKE.md` for the shared
tracker-backend contract those two converged on) - worth checking whether
this GAS project can just implement that same doGet/doPost shape (a
`type=photo` write instead of `bug`/`feature`) rather than inventing a
bespoke one. Read the existing Apps Script source (Extensions > Apps
Script from the sheet) before designing the endpoint, to see what's
already there to extend vs. what's net-new.

Idea: a small web app you open on your phone that lets you snap a photo
of the physical CD/album art and associates it with the current or a past
rip (embedded as album art in the mp3s, matched by disc ID).

Needs before starting:
- Association mechanism: simplest is probably a short-lived pairing code
  or QR code shown by `wtul-rip` at rip time, scanned by the phone to
  link the upload to that disc ID.
- Embedding: abcde already supports `EMBEDALBUMART`/`GETALBUMART` actions -
  once a photo lands as a file, it can likely reuse that pipeline instead
  of hand-rolling ID3 APIC frame writes.
- How the ripping machine pulls the photo back down from GAS (poll the
  sheet/script for a new row matching the disc ID? push via a webhook?) -
  same "never trust the raw POST response, re-GET to confirm" gotcha
  `INTAKE.md` documents applies here too.

## 5. Instrumental intro/outro detection

**Decision (2026-07-20): Demucs**, installed on `dexter` (the Ryzen
mini-PC that already hosts `crt`'s `dexter-whisper-server.py` - Demucs is
GPU/CPU-heavy enough it belongs there, not on this machine). A prior
attempt at getting Demucs running on dexter apparently left files
somewhere on that machine already - **left a cross-project `%%ACTION` note
in `crt`'s `.claude/FOCUS.md`** (2026-07-20) asking whoever next has a
live session on dexter to locate them, since `wtul` itself has no access
to that machine. Once Demucs is confirmed running on dexter, this project
still needs a network path to call it (mirror
`CRT_WHISPER_SERVER`'s pattern - a small HTTP wrapper on dexter, called
from here) - not designed yet.

Idea: detect the instrumental-only sections at the start/end of each
track (useful for on-air talk-over timing).

Needs before starting:
- Confirmation from the dexter-side search above: reusable prior install,
  or starting clean.
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

**Status (2026-07-20): done and live-verified.** The sheet is
[here](https://docs.google.com/spreadsheets/d/19QfbBhZpTJZYFuTkWuerD73z3AN_tGl3n8t5cq3dwKI/edit?gid=591596929#gid=591596929)
(Google Sheets - different sheet than #4's photo-capture one) - real
schema turned out to be the **"LOCAL"** tab (of three: LOCAL, Closers,
SWEEPERS/PROMOS/BUMPS), with a title row ("LOCAL CDS") before the real
header row: `#, ARTIST, ALBUM, LABEL, YEAR, Rating, GENRE, MERIT, LOCAL,
COMMENT, DATE, DJ NAME, HOME`.

No OAuth/service account, per #4's pattern and the scheduler's
`INTAKE.md` contract: `gas/catalog-writeback.gs.js`, an Apps Script bound
to the sheet, deployed as a web app. It auto-detects the header row
(picks whichever of the first few rows has the most non-empty cells, so
a title row above the real headers doesn't break it) and matches
incoming JSON keys to columns by name - no hardcoded schema.
`lib/catalog_writeback.py` (7 unit tests) is the Python side:
`rip_session()` in `bin/wtul-rip` POSTs `{ARTIST, ALBUM, DATE, LOCAL:
true}` once a disc finishes ripping completely (not on a partial/failed
session - a half-ripped album shouldn't hit the rotation catalog).

**Real gotcha hit and fixed**: a live test POST came back as Apps
Script's own "Page Not Found" redirect HTML, not JSON - exactly the
documented `INTAKE.md` warning that a POST response against this kind of
endpoint can't be trusted. `write_row()` doesn't trust it either - it
POSTs, then re-`GET`s recent rows and checks the ARTIST+ALBUM actually
landed before reporting success. Live-verified twice against the real
sheet (test rows added, need deleting by hand - no delete endpoint was
built, out of scope for now).

Per the pipeline vision above, this is also where a newly-burned/labeled
curated mix (the end of the capture→curate→burn→label→rotation loop)
would get logged back in as a rotation item, not just per-disc catalog
rows from `wtul-rip` itself - not built, just noting the row shape
(`LOCAL: true` plus the rest) would need to change for that use once #9
exists.

Idea: there's an existing spreadsheet cataloging the local music
collection. As `wtul-rip` completes discs, automatically add/update rows
for what was just ripped instead of that being a separate manual step.

## 9. Capture-on-play - auto-rip material right after it airs

**New (2026-07-20)**, the front end of the pipeline vision above and not
designed yet - genuinely needs the user's input on mechanism, not a
guess:

Idea: right now `wtul-rip` only rips a physical CD inserted into the
drive. The actual goal is broader - whatever gets played on air (from
vinyl, a CD, a DJ's own device, whatever the studio's actual playback
chain is) should get captured into the "material to curate later" pile
automatically, right after it plays, without someone manually feeding a
disc into this tool afterward.

Needs before starting (open questions, not yet answered):
- **What's the actual capture source?** Is there a line-level tap on the
  studio's board/soundcard this machine could record from directly
  (`arecord`/similar, triggered somehow), or is "auto-rip" here really
  "auto-rip whatever CD is in the drive as soon as Spinitron logs a spin
  matching it" (i.e., #1's matching logic run in reverse - a spin appears,
  find the matching disc, rip it) rather than a live audio capture at all?
  These are very different builds.
- If it is live capture: what's the trigger (Spinitron spin start? a
  manual button/hotkey? VU/silence detection?) and what's the audio
  source (physical line-in on this machine, or something over network)?
- Where captured audio lands before curation (a dated holding folder
  under `~/Music/`?) and what identifies each capture for later curation
  (Spinitron spin metadata already gives artist/title/timestamp for free
  if #1's data is reused here).

## 10. Show-run sheet / sweeper integration - not designed, flagged not built

**New (2026-07-22)**, surfaced while prepping for a show, deliberately
**not built this round** (vision-debt guardrail - see realisateur's
`scheduler_relationship` notes on not building speculative cross-system
integration same-day): the Friday "Local Show" is run from a Google Sheet
(slot-numbered rows: `theme`/`sweeper N`/`music`/`psa`/`promo`/`calendar`/
`closer`, each sweeper row pointing at a pre-recorded Google Drive audio
clip) - a completely separate system from this repo's CD ripper. The idea
floated was "light integration" between wtul-rip and that sheet, but
there's no concrete mechanism yet (what would wtul-rip even do with a
run-sheet row - cue playback? log what aired? nothing here plays audio
today, it only rips discs already in hand).

Needs before starting (genuinely undesigned, not just unscheduled):
- What's the actual pain point the sheet doesn't already solve by itself
  (currently just read/followed manually during the show)?
- Would this be wtul-rip logging against the sheet (e.g. writing back
  which ripped tracks got played, sheet-row style, similar in shape to
  #8's catalog write-back), or the sheet driving wtul-rip (e.g.
  auto-queuing a rip when a sheet row says a track should air)? Different
  directions, not a detail to guess at.
- Out of scope until one of those directions is picked; the sheet works
  fine unintegrated in the meantime.
