<!-- Per-project scope marker -- read FIRST by wtul's own nightly-batch/
     bug-sweep before touching anything else. -->

## Stability milestone

**Current:** wtul reliably rips a disc end-to-end with correct track metadata (Spinitron public-scrape + Discogs lookup, both credential-free) and logs it in a form Zach can trust without hand-checking — status: in-progress
Done when:
- [x] FOCUS.md/ROADMAP.md reconciliation done (thin pointer above, kept
      2026-07-24)
- [ ] rip-speed monitoring (`rip-speed-monitoring` branch) hands-on
      hardware-verified against a real rip, then merged
- [ ] metadata-fix API (#2) built against Discogs (decided 2026-07-24,
      token already in hand) and live-verified against a real rip

Ideas beyond this bar are PARKED by default (see
realisateur/STABILITY-MILESTONES.md): capture-on-play pipeline
front-end (#9), label printer (#3), web-photo/OCR (#4/#7), show-run
sheet (#10). **Correction (2026-07-24, realisateur):** #8 (catalog
spreadsheet) was wrongly listed here — it's done, live-verified, and
already merged to `main` (see ROADMAP.md #8); it isn't past the bar,
it's finished. #3/#4/#7 aren't waiting on undecided hardware/design
either anymore (all three were decided 2026-07-20 and built this week)
— what actually parks them is that they live on unmerged branches that
have drifted behind `main` (see "Branch health" below), not open
questions. QUESTIONS.md's 2026-07-18 either/or parts (b)/(c)/(d) were
reclassified `(parked)` the same day for this reason.

## Branch health (2026-07-24, foundation note for the next dev cycle)

Four feature branches are built but unmerged, and **all four are stale
— diverged behind `main`** by today's live-test fixes (cddbread.N
parsing, TOC-discid resume fix, install.sh's lib/ bundling, the
Unknown-fallback, Spinitron-gating revert, eject soft-key):
`rip-speed-monitoring` (36 commits behind, ROADMAP #6),
`label-printer-integration` (13 behind, #3), `web-photo-capture` (13
behind, #4), `ocr-metadata-extraction` (13 behind, #4/#7, itself
branched off `web-photo-capture`). Merging any of these as-is would
silently *reintroduce* today's live-caught bugs — a layer-not-replace
regression, not a clean merge. Whichever
gets picked up next needs a **rebase onto `main` first**, not a merge,
before its own hardware/live verification even starts. `rip-speed-
monitoring` is the one closest to mattering (it's a milestone
criterion) — rebase it first.
(`spinitron-priority-matching`, the fifth stale-looking branch `scheduler
status` surfaces, is a false alarm: `git branch --merged main` confirms
it's already fully merged, just an unpruned local ref — safe to delete,
not a real backlog item.)

**Update, same evening:** `label-printer-integration` picked up first
(real hardware verification in progress against a real mix burn - see
ROADMAP.md #3), rebased clean onto `main` (one conflict, in ROADMAP.md's
own status text, resolved). Also landed on `main` this evening, unrelated
to the branch-staleness problem above but touching the same rip
destination code every one of those four branches assumes: **rips now
land in a dated mix folder** (`~/Music/mixes/YYYY-MM-DD/`, not the old
flat `~/Music/ripped/<Artist>/<Album>`) - see ROADMAP.md's "Vision"
section and `bin/wtul-rip`'s `RIPDIR`/`MIXES_ROOT`. Whoever rebases the
other three branches next needs to be aware of *this* migration too, not
just the live-test bug fixes - anything in those branches assuming
`~/Music/ripped` as the rip destination will need a second look.

See `LIVE-TEST-DEBRIEF-2026-07-24.md` for the full session debrief this
was drawn from.

**Update (2026-07-25, wtul-batch stress-test round):** all 7 unmerged
feature branches (`detection-failure-earcon`, `discid-rerip-cache`,
`label-printer-integration`, `rip-speed-monitoring`, `spin-live-watch`,
`web-photo-capture`, `ocr-metadata-extraction`) re-verified from scratch
(each branch's own test suite re-run, not trusted from a prior run's
claim) and rebased onto `main`'s new tip, all green - see
`~/reports/wtul/2026-07-25.md` for tip SHAs. No milestone-criterion
status change (both remaining criteria are still gated on a real rip);
this was routine branch-health upkeep plus 3 more well-formed-but-wrong-
shaped/malformed-input bugs found and fixed the same way as the prior
round's `spinitron`/`catalog_writeback` guards
(`lib/metadata_lookup.py`'s `acoustid_lookup` nested-list shape,
`bin/wtul-rip`'s `read_toc_discid` non-numeric track count,
`lib/photo_capture.py`'s `associate_photo` missing-`url` response).

**Update (2026-07-25, run 17): rehearsal harness built, branch
`rip-rehearsal-harness`.** The recurring reason nothing moves on this
milestone unattended is that `rip_session()` — the function that actually
sequences a rip — can only run with a disc in a real drive, so it had no
test coverage at all; only its leaf parsers did. `lib/fake_drive.py` now
answers the four hardware commands `bin/wtul-rip` shells out to
(`udevadm info`, `cdparanoia -Q`, `abcde -a cddb`, `abcde -a
read,encode,tag,move N`) from a JSON disc spec.

Usage: `WTUL_SIMULATE_DRIVE=demo ./bin/wtul-rip` for the built-in 3-track
disc, or point it at a spec file (`etc/rehearsal-disc.example.json` is a
copyable template; fields: `discid` (8 hex), `artist`, `album`, `match`
(false → rehearse the Unknown-Album fallback), `disc_present`,
`read_speed`, and `tracks[]` with `title`/`length` (`M:SS`)/`fails`).
`WTUL_SIMULATE_ROOT` overrides the sandbox location.

**This does not clear any hardware gate, and no criterion above changed
status because of it.** A rehearsal says nothing about how a real drive or
a real scratched CD behaves. What it buys: a scarce real-disc session is no
longer spent rediscovering a logic bug that was findable without a disc.

Containment (all three verified by running it for real, not just tested):
rips land in `~/.cache/wtul/rehearsal`, never the mix folder that gets
burned; session logs are named `-SIMULATED` so `history()` can't read one
as a real rip; a separate lockfile keeps it clear of a real rip. A bad
spec exits rather than falling back to the real drive.

**Update (2026-07-25, run 18): two real bugs found and fixed on `main`,
both in code a real rip runs every time.**

1. **`album_dir_path()` didn't mirror `abcde.conf`'s `mungefilename()`**
   (`c3e2988`, merged to `main`). abcde maps `:` to `-` and deletes `'`,
   `"`, `?` and control characters from every path component before
   writing; wtul-rip predicted the *unstripped* folder. So for any disc
   whose metadata carries one of those - "It's Alive", "Songs: Ohia",
   "Who's Next?", i.e. a large share of real records - wtul-rip was
   looking in a directory abcde had never created. Nothing raised;
   three separate features just quietly did nothing: resume-skip re-ripped
   every track on reinsert, `find_track_file()` never populated `ripped`
   so live `artist=`/`album=`/`N=Title` edits couldn't retag what was
   already on disk, and `retag_ripped_tracks()` moved files to a second
   wrong folder. `fix_by_discid()` built its destination the same way.
   The tests don't re-type the rule - they source `abcde.conf` and run the
   real shell function, so the conf stays single-source.
2. **`wtul-rip` busy-looped at 100% CPU on a non-terminal stdin**
   (`d02f103`, merged to `main`). An EOF stdin is permanently "readable",
   so `select()` returned instantly forever instead of polling every
   `POLL_SECS`; the partial-disc retry prompt below it used a bare
   `input()` that raised an uncaught `EOFError`. Both now degrade to
   "keep watching the drive, no keyboard commands". Hit for real while
   trying to drive a rehearsal from this batch job.

Bug 1 is the more instructive one: **the rehearsal harness could not have
caught it**, because `FakeDrive` takes its output path *from*
`album_dir_path()` and so inherited the same wrong rule - harness and code
agreed with each other while both disagreed with abcde. Found by reading
`abcde.conf` against the Python instead. The harness has since been
re-pointed at the real `munge_filename` (`rip-rehearsal-harness`), and its
new punctuated-disc rehearsal asserts the folder *name*, not just that
resume works, so agreement-on-a-wrong-answer fails the suite now.

Neither fix needs hardware to verify, and neither clears a hardware gate -
but both were live in the path a real show-night rip takes, so the next
real rip should behave better than the last one did.

*(Milestone drafted 2026-07-24 via realisateur's `/ideate` — revise if
it doesn't fit wtul's own read of its bar.)*

## Current focus

**Migrated in full from `ROADMAP.md` 2026-07-24** (see "Ideas" below --
a fresh request came in mid-evening asking for exactly this, reversing
the same-day-earlier "keep it a thin pointer" call). `ROADMAP.md` itself
is now a retired stub pointing back here -- this section, not that file,
is the real backlog going forward, matching the convention every other
project in this ecosystem already uses.

### Vision: the full lifecycle (2026-07-20)

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
- **Curation** - **retired as a separate step, 2026-07-24.** Originally
  "manual, no roadmap item yet, not blocking anything else"; superseded
  same day by a simpler decision made live during an actual show-night
  ritual: rips land directly in a dated mix folder
  (`~/Music/mixes/YYYY-MM-DD/`, see `bin/wtul-rip`'s `RIPDIR`/
  `MIXES_ROOT`), so whatever got ripped on a given day just **is** that
  day's mix - no separate copy-into-a-mix-folder pass. The old flat
  `~/Music/ripped/<Artist>/<Album>` destination is retired for new rips
  (history from before the switch stays there, untouched). One curation
  step remains, unavoidably manual: unidentified tracks (`Unknown Album
  (discid)`) are excluded from what gets burned, by rule, and stay put
  for a later identification pass rather than landing on a mix.
- **Burn + label** - burning is out of scope for `wtul-rip` (it's a
  ripper, not a burner) but **#3's Phomemo M02 label printer is the label
  half**, once a mix is burned by hand.
- **Re-enter rotation** - **#8's catalog spreadsheet** is where a
  newly-burned mix CD gets logged back in as a real rotation item.

So #3, #8, and (once designed) #9 are the pipeline; #2/#4/#5/#7 are
independent quality-of-life items on the ripping side, not part of this
loop.

### 1. Spinitron integration - prioritize already-played tracks

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

### 2. External API to fix metadata on already-ripped unidentified discs

**Status (2026-07-24): built, wired, and live-verified end-to-end
(non-hardware parts).** Both keys now live at `~/.config/wtul/secrets.env`
(gitignored-by-location, never committed - `bin/wtul-rip` loads it at
startup via `os.environ.setdefault`, real env vars still win):
`ACOUSTID_API_KEY` (since 2026-07-20) and now `DISCOGS_TOKEN` (the
"localshow" token, per the realisateur decision recorded 2026-07-24 to
go with Discogs over further AcoustID/Chromaprint work - see
`.claude/QUESTIONS.md`'s consumed reply). `libchromaprint-tools` is also
now installed (`fpcalc version 1.5.1`), clearing the last blocker noted
below.

`lib/metadata_lookup.py` (15 unit tests, all mocked - no real
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

**Live-verified this session** (real network calls, no mocks, no CD
drive needed): `fpcalc` fingerprinted a real local audio file end to end;
the AcoustID HTTP round-trip succeeded cleanly (empty result set, as
expected for non-music test audio - the point was confirming the API
call itself works, not a real match); `discogs_search_by_artist` returned
a real catalog hit for "Radiohead". One test (`test_wiring.py`'s
`test_acoustid_key_env_var_picked_up`) was reading the real
`~/.config/wtul/secrets.env` instead of a clean fixture once that file
had real content - fixed by pointing `HOME` at an empty tmp dir for that
test.

**Still pending real hands-on verification**: the whole path has never
run against an actual freshly-ripped disc via `fix_by_discid()` itself -
next real rip of a previously-unidentified disc is the real test.

Idea: extend the `fix <discid>` command so it can look up the correct
metadata automatically instead of only accepting manual artist/album entry.

Needs before starting:
- ~~`fpcalc` (Chromaprint) installed~~ - done, see Status above.
- ~~AcoustID API key~~ - done, see Status above.
- ~~A Discogs personal access token~~ - done, see Status above.
- ~~Rate limits for both~~ - **2026-07-24**: `resolve_disc_metadata` now
  throttles AcoustID lookups to one per 0.35s (its documented 3 req/s
  client limit) since it fires one request per track in a loop - a
  normal multi-track album would otherwise burst past that on a single
  disc, not just across a backlog. Discogs is only ever called once per
  disc (artist-catalog fallback), so no throttle needed there. 2 new
  tests (`tests/test_metadata_lookup.py`), throttle is injectable
  (`sleep_fn`/`clock`) so tests don't actually wait.

### 3. Label printer integration - seamless tagging

**Decision (2026-07-20): Phomemo M02** (BLE thermal receipt/label printer).
**Status (2026-07-24): built and wired, branch `label-printer-integration`,
rebased onto `main` twice same day to pick up the live-test fixes and the
ripped->mixes migration below before hardware verification.**
`lib/label_render.py` (pure-PIL, no BLE) renders a single-disc label;
`lib/mix_label.py` + `render_mix_label()`/`render_mix_label_columns()`
(added live, same evening) assemble a numbered, left-aligned label for a
whole dated mix compilation instead of one disc - built for, and tested
against, a real 14-track mix the same night. Genre/year come from a new
`discogs_genre_year()` lookup (throttled - a real 8-album mix fired
requests fast enough to get silently rate-limited mid-batch on first
try). `print_label()` shells out to `~/.local/bin/catprint` and degrades
to `(False, reason)` on any failure - missing binary, timeout, non-zero
exit - never raising, so a printer that's off/out of BLE range doesn't
fail the rip itself.

**Live-verification: partial, ongoing.** The M02 printed successfully at
least once tonight (confirmed physically) but the BLE connection is
unreliable - see `.claude/QUESTIONS.md`'s "Phomemo M02 BLE connection is
unreliable" entry for the live debugging so far (untrusting the device
didn't fix it; it can even interrupt an already-printing job mid-way).
Needs a dedicated session with the printer in hand, not more firefighting
mid-ritual. Tonight's actual post-show routine stopped after the
metadata-repair/mix-assembly stage as a result - no CD got burned, no
label made it onto one (see `LIVE-TEST-DEBRIEF-2026-07-24.md`).

Per the pipeline vision above, this printer is also the label half of
the "burn a curated mix, print its label" loop (#8) - `render_label()`
was written generically (artist/album/tracklist/discid, not
wtul-rip-specific) so that reuse doesn't need a rewrite once #9 exists,
just a caller with the mix's own metadata instead of a single disc's.

Idea: once a disc finishes ripping, automatically print a physical label
(artist/album/tracklist, maybe a QR code encoding the disc ID for
`fix <discid>` lookups later) for the CD/case.

### 4. Web app + phone photo capture for album art

**Decision (2026-07-20): host in Google Apps Script**, reusing the
existing GAS project already backing
[this sheet](https://docs.google.com/spreadsheets/d/1GzIbZUhn6fF7JPC20kdG2IMomvZlDBidDTy5cDEF3U8/edit?gid=1753821521#gid=1753821521)
and deployed at `hf7y.com/localshow.html` (forwards to the script's `/exec`
link) - not a new Flask/FastAPI service.
**Status (2026-07-24): built on branch `web-photo-capture` (pairing/
upload/embed pipeline), not yet hardware/live-verified, and stale behind
`main` - needs a rebase before it's touched again (see "Branch health"
above). `ocr-metadata-extraction` (#7) branches off this one, so
rebasing this branch first is the prerequisite for rebasing that one
too.** This is the same
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

### 5. Instrumental intro/outro detection

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

### 6. Monitor and improve ripping speed

**Status (2026-07-24): built 2026-07-18 on branch `rip-speed-monitoring`
(reports per-session/overall median extraction speed, slow-track flags,
a degradation warning, and a live `(read speed N.Nx)` line per track;
parser unit-tested against real logs), but NOT merged and stale behind
`main`** — it predates every fix from today's live test session
(cddbread.N parsing, TOC-discid resume, install.sh's lib/ bundling,
Unknown-fallback, Spinitron-gating revert, eject soft-key), **and
predates the ripped->mixes dated-folder migration (its own log-parsing
needs will read `~/Music/mixes/.logs/`, not `~/Music/ripped/.logs/`,
once rebased).** Needs a **rebase onto `main` first**, then hands-on
hardware verification against a real rip (the live per-track print only
fires during an actual rip) before merge — this is the last non-metadata
criterion on wtul's current stability milestone (see "Branch health"
above and `LIVE-TEST-DEBRIEF-2026-07-24.md`).

Idea: surface actual rip throughput (cdparanoia reports an extraction
speed multiplier, e.g. "4.2x") so slow rips are visible instead of just
"it's taking a while," and use that to decide whether the bottleneck is
worth fixing via hardware (a faster/better drive) or software (a lower
encode quality/bitrate trades CPU+time for size).

Needs before starting:
- Parse cdparanoia's speed output per track (it prints a running
  extraction-speed multiplier - need to check exact format across the
  runs already logged in `~/Music/mixes/.logs/` for the regex to match
  (moved here 2026-07-24 from `~/Music/ripped/.logs/`; older logs from
  before the move are still at the old path, untouched).
- Decide what "monitoring" means concretely: live display during the
  existing `sh_live` streaming (cheap - just surface a number that's
  already in the output), vs. persisted stats across rips to spot
  degradation over time (needs a small stats log/store).
- If it turns out software-side, `LAMEOPTS` in `abcde.conf` is the knob
  (currently `-V 2`; a faster preset or lower quality trades encode time
  for size/quality) - but drive read speed (cdparanoia) is likely the
  actual bottleneck, not LAME encode speed, so measure before assuming
  which one to change.

### 7. OCR on the photo-scan layer for metadata generation

**Status (2026-07-24): built, unit-tested, branch `ocr-metadata-extraction`
(branched off `web-photo-capture` since it depends on #4's cover-photo
plumbing, which isn't in `main` yet). Not live-verified. Also stale
behind `main` (same figure as #4, since it branches off it) — see
"Branch health" above; rebase #4 first, then this one.** `lib/ocr_metadata.py`
finds a disc's `cover.jpg` (saved by #4's `photo_capture.associate_photo`)
and runs the `tesseract` CLI on it directly (not the `pytesseract`
wrapper - not installable here without overriding the OS's
externally-managed-Python guard, and the CLI is the simpler,
already-established pattern this codebase uses for `fpcalc` too). Wired
into `fix_by_discid()` in `bin/wtul-rip`: when AcoustID/Discogs (#2) find
no confident match, cleaned OCR candidate lines are printed to the user
alongside the existing manual artist/album prompt - never auto-filled,
same confirm/edit discipline #2's suggestions already follow. 20 new
tests (`tests/test_ocr_metadata.py`), subprocess fully mocked.

**Update (2026-07-24, wtul-batch run 14): blocker (a) was already stale
before this session started.** A real `tesseract` 5.3.4 binary + English
`tessdata` turned out to already exist at
`~/.local/opt/tesseract-user/usr/bin/tesseract` (dated April 2024 - some
prior, unrelated local install, not something any `wtul-batch` run put
there). `find_tesseract()`'s own PATH-then-local-install fallback finds
it correctly (verified directly this round, not assumed). Ran the real,
un-mocked pipeline end to end: generated a synthetic cover image with
"RADIOHEAD" / "OK Computer" text via Pillow, pointed
`ocr_cover_candidates()` at it with no mocks - it shelled out to the real
binary and returned OCR'd candidate lines (`['PADIOHEAD', 'OkComputer']`
- imperfect character recognition on a plain default-font test image, as
expected, but the plumbing - binary discovery, subprocess invocation,
`TESSDATA_PREFIX` env passthrough, line-cleaning - is now genuinely
live-verified, not just unit-tested against mocks). Full branch suite
re-run clean: 86/86 passing.

**Still pending real verification, on one front only now**: (b) this has
never been tried against a *real disc's real cover photo* (as opposed to
a synthetic test image), which still needs #4's live phone-capture flow
to produce a `cover.jpg` in the first place - that part is unchanged,
still hardware/phone-gated.

Needs before starting:
- ~~Depends on #4 existing first (the photo capture/association
  pipeline).~~ - exists, on unmerged branch `web-photo-capture`.
- ~~An OCR engine~~ - **resolved 2026-07-24, see Update above**: a
  working local `tesseract` install already exists on this machine and
  is picked up automatically; no further `sudo apt install` action
  needed.
- ~~OCR'd text would be messy/unstructured~~ - resolved as "present to
  the user as a suggestion they confirm/edit", per Status above; no
  fuzzy-match-to-fields step was built, deliberately (raw OCR lines are
  shown as-is, not parsed into structured fields).

### 8. Auto-update the local music catalog spreadsheet

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

### 9. Capture-on-play - auto-rip material right after it airs

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

### 10. Show-run sheet / sweeper integration - not designed, flagged not built

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

**Direction picked (2026-07-24, next `/wtul-batch`): a small web UI, sheet
driving playback prep, not wtul-rip logging.** Idea: a page that reads the
run-sheet and, for the upcoming `sweeper N` row, pre-loads that row's
Google Drive audio clip into local cache ahead of when it airs -
eliminating the on-air lag of a cold fetch/buffer at cue time. Two
pieces:
- **Auto-prime**: as the show clock advances (or the sheet's current row
  advances), automatically cache the *next* upcoming sweeper clip.
- **Manual prime button**: a button to force-cache a specific sweeper on
  demand, for cases where auto-prime hasn't caught up yet (jumping ahead
  in the sheet, re-cueing something already played, etc).

Still needs, before `/wtul-batch` builds anything real:
- How this web UI reads the sheet - Google Sheets API (read-only,
  service-account or OAuth?) vs a manually-exported/synced copy. This
  repo has no Google API wiring today; #8's catalog spreadsheet work may
  end up sharing this decision, worth deciding once for both rather than
  twice.
- What "cache" means concretely - browser cache (fetch + hold in memory/
  IndexedDB, page must stay open), or a local file fetched to disk so
  something else (e.g. a media player) can pick it up? Changes the whole
  shape of "load to cache."
- Where this runs during the show - same machine as `wtul-rip`, or a
  separate browser tab/device someone's actually watching live? No
  hosting/deployment decision made yet.
- This is new surface area (a web app + Google Sheets read access), not a
  wtul-rip change - likely its own script/directory rather than bolted
  onto `bin/wtul-rip`.

## Ideas (added via `scheduler -i`)

- **2026-07-22 14:58 (via `scheduler -i`): RESOLVED 2026-07-24
  (realisateur).** FOCUS.md fleshed out with a real `## Current focus`
  section so `scheduler status wtul`'s next-up parser could see it.
  Superseded by the full migration below same evening.
- **2026-07-24 15:11 (via `scheduler -i`): RESOLVED 2026-07-24
  (realisateur).** This *was* the request to migrate `ROADMAP.md`'s
  content into `FOCUS.md` in line with the rest of the ecosystem's
  convention, reversing the morning's thin-pointer call - done above.
  `ROADMAP.md` is now a retired stub; `.claude/commands/wtul-batch.md`
  updated to read `FOCUS.md` instead (it was the load-bearing reference,
  not just docs - the scheduled job's own instructions pointed at
  `ROADMAP.md` directly).

## Fable review (2026-07-25)

<!-- Appended by realisateur/fable-like/inject-suggestions.sh. Full context: fable-like/FABLE_REPORT.md. Triage these like any dated entries; delete freely. -->

- **2026-07-25 (fable-review):** the dexter move's one remaining step is human and unnamed in BLOCKERS — record it precisely: install gh on dexter OR add the deploy key via GitHub web UI; a reverted migration with an unnamed step is a mystery in three weeks
  - **Triaged 2026-07-25 (wtul-batch): not this repo's.** wtul has no
    `BLOCKERS` file, no dexter migration and no deploy-key step; the only
    dexter mention here is #5's Demucs note, a different thing entirely.
    Left in place rather than deleted so whoever runs the injector can see
    it landed in the wrong project, but no wtul action follows from it.
- ~~**2026-07-25 (fable-review):** keep this FOCUS.md thin but add a comment naming ROADMAP.md as source of truth, so the duplication is never "fixed" by deleting the wrong file~~
  - **Rejected 2026-07-25 (wtul-batch): backwards, and acting on it would
    have caused the exact damage it warns about.** The 2026-07-24 migration
    went the other way - `ROADMAP.md` is a retired stub and *this* file is
    the source of truth. A comment naming ROADMAP.md as canonical would
    have pointed the next reader, and the next batch run, at the empty
    file. Struck through rather than deleted so a future run doesn't
    re-derive the same suggestion from a clean slate and act on it.
