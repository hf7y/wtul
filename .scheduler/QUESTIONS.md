# Questions for the user

Running log, appended to (never overwritten or trimmed) by `/wtul-batch`
whenever something bigger than a routine report note comes up.

## How to answer (this is the two-way interface)

Reply **inline, directly under the question**, on a new line starting
with `> ` (a Markdown blockquote). You don't need to delete anything
yourself. Example:

```
- **2026-07-18 (wtul-batch): Which metadata API?**
```

`/wtul-batch` step 0a reads this file first each run
(`collect-feedback.sh .scheduler/QUESTIONS.md --consume`), treats any `> `
reply as authoritative, acts on it, then removes that question's whole
entry (git history + that run's report keep the record) -- that's the
only thing that should ever remove something from this file. To dismiss
a question without any action, you can still just delete its line by
hand.

- **2026-07-22 (wtul-batch): wtul has no `.claude/FOCUS.md` -- deliberately not
  building one yet.** Flagged by scheduler's `scheduler status` (its
  "next up" parser needs a Current-focus/Priority/Backlog structure it
  can't find here) and picked up by realisateur
  (`FOCUS-md-formatting-compliance-20260722-145750.idea` in its repo),
  which is writing the canonical FOCUS.md formatting spec + deciding how
  wtul's FOCUS.md should reconcile with `ROADMAP.md` (migrate content,
  symlink, or a thin pointer file). Hand-fixed the OTHER conformance gap
  in the meantime -- this file's own header didn't document the `> `
  inline-reply contract `wtul-batch.md` step 0a already relies on
  (see the "How to answer" section added above). No decision needed from
  you; next `/wtul-batch` run should just check whether realisateur's
  spec has landed and build wtul's real FOCUS.md against it then.
- **2026-07-20 (Spinitron API key): resolved, no key needed.** User
  confirmed (via inline note in the scheduler's `BLOCKERS.md`) they don't
  have API access and would need to go through the station managers to get
  it - not pursuing that. Unblocked ROADMAP #1 instead by scraping
  `spinitron.com/WTUL/`, the public no-login page the WTUL website's own
  "currently playing" widget is backed by, which embeds each spin as JSON
  in a `data-spin` HTML attribute. `lib/spinitron.py` gained
  `fetch_recent_spins_public()` for this; `bin/wtul-rip` now calls it
  unconditionally (no env var gate). Live-verified against the real page.
  The old `SPINITRON_API_KEY`-gated path and its tests were removed since
  there's no key to gate on; the official `fetch_recent_spins(api_key)`
  client itself is left in `lib/spinitron.py` unused, in case station
  access is ever granted later.
- **2026-07-24 (parked, hardware): Tascam CD-500B relay playback cabling.**
  User wants two CD-500B decks wired for relay playback (deck B auto-starts
  when deck A's disc ends, for gapless broadcast continuity). Likely needs:
  (1) a relay link cable between the two units' `RELAY` jacks (believed to
  be 1/4" TS on the CD-500B, unverified against the actual manual/unit),
  and (2) audio-out cables to the console (XLR balanced vs RCA unbalanced,
  whichever the board expects). Not yet confirmed against the real
  hardware/manual - no purchase made. Revisit when ready to actually buy;
  this ties into ROADMAP.md's "capture-on-play" pipeline (#9) if relay
  playback becomes the live-source side of that eventually.
- **2026-07-24 (parked, wtul-rip UX): stream Spinitron spins into the CLI
  while running; earcon on detection failure.** Two ideas from live
  hardware testing: (1) `wtul-rip` currently only checks Spinitron once
  per disc (inside `rip_session()`, best-effort, silent on failure) -
  streaming/polling spins continuously and printing them live while the
  tool idles between discs would make the "already played on air" signal
  visible in real time, not just at rip-queue-build time. (2) an audible
  earcon (short sound cue) when disc/media detection fails, so a failed
  auto-rip attempt (e.g. today's "Metadata scrape failed to produce a
  discid" case, now fixed - see `bin/wtul-rip`'s `find_cddbread`) doesn't
  go unnoticed if no one's watching the terminal. Neither designed yet -
  needs: polling interval/rate-limit for (1), and a sound mechanism
  choice for (2) (terminal bell vs a real audio file needs an output
  device decision). Not built this round. **BOTH BUILT 2026-07-24 (runs
  10 and 11) — filed here late 2026-07-25 because those runs hit the
  `.claude/*.md` sensitive-file write gate and could only draft their
  entries into `~/reports/wtul/2026-07-24.md`.** (1) built on branch
  `spin-live-watch` (commit `58731a9`/`ef21883`, pushed) — idle-loop
  live spin printing + manual `spins` command, live-verified against
  the real Spinitron page; MERGED to `main` 2026-07-25 (`8042b62`,
  110/110 tests green), no decision needed. (2) built as a terminal bell
  (`WTUL_EARCON=0` to disable) on branch `detection-failure-earcon`,
  since MERGED to `main` (`d0dd74c`); fires on both metadata-scrape
  failure points in `rip_session()`, verifiable by ear on the next real
  rip that hits either path. The "real audio file" upgrade for (2)
  still awaits the output-device decision.
- **2026-07-24 (parked, bigger build): smarter on-air-detection than the
  Spinitron page scrape.** After live-testing, default ripping no longer
  gates on a Spinitron match at all (see `bin/wtul-rip` commit
  `7c55323`) - it's informational only, because the public page only
  covers the current show and can lag/miss. Two directions floated for
  actually closing that gap, not built (explicitly called out as a
  "bigger build", not a same-session tweak):
  (a) local audio fingerprinting - listen to (or otherwise sample) what's
  actually on air and match it directly, instead of trusting Spinitron's
  page to be current; would need an audio input source this repo doesn't
  have today (line-in from the board? a stream URL?) - undesigned.
  (b) an earcon (audible cue) when Spinitron's feed is confirmed still
  updating, as a "this data source is being kept live" signal, distinct
  from the failure-detection earcon idea above. Could combine both. Ties
  into ROADMAP #1 (Spinitron integration) and #9 (capture-on-play) -
  worth reconciling with both rather than freelancing a third mechanism
  when this actually gets built.
- **2026-07-24 (parked, hardware): eject softkey, since the drive doesn't
  have a physical eject button. RESOLVED same day (live session, not
  wtul-batch) - already built and on `main`.** `bin/wtul-rip`'s idle loop
  and its "disc left in drive" retry prompt both accept `e` and shell out
  to `eject <dev>` (see `main`, commit `f218be8`). This entry was stale by
  the time `wtul-batch` run 12 (2026-07-24) checked it - flagging only so
  the next run doesn't re-propose it.
- **2026-07-24 (parked, bigger build): fallback metadata service for
  discs AcoustID+Discogs (#2) can't identify.** Surfaced live: `fix
  <discid>` ran its full suggestion path and still came back empty for
  a disc neither service recognized. Not every disc will resolve via
  those two - a third fallback (a different fingerprint DB, MusicBrainz
  direct search by manually-typed title, or similar) is real future
  work, not designed yet. Ties into #2. **Standing rule in the meantime
  (stated live, not a code change): unidentifiable tracks don't go on a
  compilation/mix burn** - curation excludes them, they stay in
  `~/Music/ripped/` for a later identification pass rather than
  blocking or getting silently included in a mix.
- **2026-07-24 (parked, bigger build): fingerprint-cache re-rips of
  previously-ripped discs, symlink instead of re-ripping. BUILT 2026-07-24
  (wtul-batch run 12) as the stopgap version, branch `discid-rerip-cache`
  (commit `8703e12`, pushed).** Went with TOC discid (not a real audio
  fingerprint) as the identity check, per this idea's own note that it's
  "cheaper but less robust across different pressings of the same
  release" and "already computed for free" - the reasonable stopgap
  interpretation, not the eventual cross-week catalog/database. Each
  fully-completed album dir now gets a `.discid` marker file
  (`write_discid_marker()`); `find_prior_rip()` scans
  `MIXES_ROOT/*/*/*/.discid` for a match (excluding today's own dir),
  preferring the most-recently-modified if more than one prior dir
  somehow shares a discid; `symlink_prior_rip()` links that prior dir's
  mp3s into today's album dir instead of re-ripping. Wired into
  `rip_session()` right where it already checks for same-day resume.
  6 new tests in `tests/test_wiring.py` (no hardware needed - pure
  filesystem logic against synthetic dirs under a tmp `HOME`): no-marker
  case, matching-marker case, self-exclusion, most-recent-wins on a
  multi-candidate collision, symlink-vs-skip-existing, and a
  missing-dir-doesn't-raise defensive case. Full suite: 47/47 passing,
  `py_compile` clean. **Known limitation, not fixed this round** (matches
  the idea's own "stopgap, not final shape" framing): if a symlinked
  track's original file is later deleted or moved, the symlink in every
  mix folder that referenced it goes dangling - a real cross-week
  database (the idea's own stated eventual version) would need to handle
  that; this round didn't design that far. **Needs hands-on verification
  against two real rips of the same physical disc a week apart** before
  being trusted - this round only exercised it against synthetic
  fixtures, never a real `rip_session()` run with an actual drive.
- **2026-07-24 (parked, hardware/flaky): Phomemo M02 BLE connection is
  unreliable - flag for a dedicated session, not chased further
  tonight.** During live label-printing (#3), `print_label()`'s
  underlying `catprint`/Bleak client repeatedly failed with "Device ...
  was not found" or timed out, inconsistently, across many retries in
  one evening - sometimes a retry printed successfully anyway despite
  reporting failure (the BLE write can complete before the client's own
  cleanup/disconnect does), sometimes nothing came out at all.
  User's live theory, worth checking first: **the OS's own Bluetooth
  GUI/applet keeps auto-connecting to the M02** (`bluetoothctl info`
  showed `Connected: yes` more than once with no deliberate connect from
  this session) - BLE peripherals typically only accept one active
  connection, so a GUI-held connection would explain Bleak's client
  failing to get its own. Manually disconnecting via `bluetoothctl
  disconnect` before a print attempt helped at least once but not
  consistently. Not designed/fixed: whether to (a) find and disable
  whatever's auto-connecting (a GNOME/KDE Bluetooth applet auto-reconnect
  setting?), (b) have `print_label()` proactively disconnect any
  existing connection via `bluetoothctl` before invoking `catprint`, or
  (c) something else entirely (out-of-range, printer-side sleep/wake
  quirk). Needs a dedicated session with the printer in hand to
  reproduce deliberately rather than firefighting mid-ritual.

  **Update, same evening:** worse than first thought - it's not just
  losing the initial connection, it interrupts an *already-printing*
  job partway through (a real partial/corrupted print, not just a
  failed attempt - wastes label tape). `plasmashell` (KDE's desktop
  shell, which owns the Bluetooth applet/bluedevil) is confirmed running
  on this machine. Tried `bluetoothctl untrust` on the M02 on the theory
  that KDE's auto-reconnect only targets trusted devices - **did not
  help, reconnected anyway** (trust restored afterward, no reason to
  leave it off since it didn't fix anything). So auto-reconnect here
  isn't gated on the trust flag - rules out the simplest fix, narrows
  the real fix to either finding bluedevil's own auto-reconnect setting
  specifically (not the generic trust flag) or option (b) above
  (`print_label()` disconnecting immediately before *and pinning the
  connection through* its own print, not just disconnecting once
  beforehand - the mid-print steal means a one-time pre-disconnect
  isn't enough).
- **2026-07-24 (wtul-batch):** Run 14 live-verified ROADMAP #7's OCR
  fallback end-to-end (non-hardware parts) - and found blocker (a)
  ("tesseract-ocr not installed, no sudo") was already stale: a working
  `tesseract` 5.3.4 + English tessdata already exists at
  `~/.local/opt/tesseract-user/usr/bin/tesseract` (dated April 2024, some
  prior unrelated local install), and `lib/ocr_metadata.py`'s own
  `find_tesseract()` fallback already finds it correctly. Ran the real
  binary against a synthetic test cover image (no mocks) and got back
  real OCR'd candidate lines. Branch `ocr-metadata-extraction`'s full
  suite re-verified clean (86/86). See `.scheduler/FOCUS.md`'s #7 section
  for the full update. Only remaining blocker for #7 is unchanged and
  still hardware-gated: a real disc's real cover photo, which needs #4's
  live phone-capture flow. No decision needed from you; this is a status
  correction, not a new feature.
- **2026-07-25 (wtul-batch):** No new feature built this round - both
  remaining stability-milestone criteria (rip-speed monitoring merge,
  Discogs metadata-fix live-verify) are still gated on a real rip, and
  the rest of the backlog (#9, #10) needs the user's own decision
  already flagged in earlier entries below. Spent the round on step 2/4
  (re-verify from scratch + stress-test) instead: re-ran every one of
  the 7 unmerged feature branches' own test suites (not trusted from
  prior runs' claims - all green), then found and fixed 3 more real
  "well-formed-but-wrong-shaped/malformed-input" bugs in the same class
  the prior round caught (`lib/metadata_lookup.py`'s `acoustid_lookup`
  didn't validate nested list entries inside `results`/`recordings`/
  `artists`/`releasegroups`, `bin/wtul-rip`'s `read_toc_discid` assumed
  the TOC track count was always numeric, `lib/photo_capture.py`'s
  `associate_photo` subscripted a possibly-`url`-less response dict).
  All 3 fixed with regression tests, no hands-on hardware verification
  needed for any of them (pure parsing/shape-guard logic). All 7
  branches rebased onto `main`'s new tip and re-pushed (force, since
  rebase rewrites history) so branch health stays 0-behind - see
  `~/reports/wtul/2026-07-25.md` for exact tip SHAs and pre-rebase SHAs
  to revert to if needed. No decision needed from you; this round was
  routine upkeep, not a new judgment call.

- **2026-07-25 (wtul-batch):** Built the **rehearsal harness** on branch
  `rip-rehearsal-harness` (`lib/fake_drive.py`): `WTUL_SIMULATE_DRIVE=demo
  ./bin/wtul-rip` runs a whole rip end to end with **no disc and no drive**,
  by answering the four hardware commands wtul-rip shells out to from a JSON
  disc spec. This is what finally gave `rip_session()` test coverage - it had
  none, because it could only ever run with a real disc. Suite 52 -> 135.
  **Does NOT need hands-on hardware verification itself** (it deliberately
  never touches the drive), and it explicitly **does not clear any existing
  hardware gate** - both stability-milestone criteria are still exactly as
  gated on a real rip as they were. See FOCUS.md for usage/containment.
- **2026-07-25 (wtul-batch): ACTION NEEDED, one junk row to delete by hand.**
  The first real rehearsal run POSTed a fake album to the **live rotation
  catalog sheet** (#8) before I noticed the gap: sandboxing `RIPDIR` wasn't
  enough, because `CATALOG_WRITEBACK_URL` comes from
  `~/.config/wtul/secrets.env` and the write-back fired on a "complete"
  simulated disc. Now suppressed under rehearsal (with a regression test), but
  the row that already landed needs deleting manually - #8 deliberately built
  no delete endpoint. Look for **`Rehearsal Artist` / `Simulated Disc`, dated
  2026-07-25** on the sheet's LOCAL tab. (Prior hand-verification test rows
  from 2026-07-20 may still be there too, per #8's own note.)
- **2026-07-25 (wtul-batch): judgment call for you, not a blocker.** All 7
  older feature branches are green but sat 1 commit behind `main` this round -
  and that one commit is **docs-only** (`4b95fe2`, FOCUS/QUESTIONS text). I
  deliberately did **not** rebase+force-push all 7 to absorb it: that's 7
  rewritten histories for zero functional change. Prior runs treated
  "0-behind" as the standing goal, so flagging the deviation. If you'd rather
  they stay strictly 0-behind regardless of what the commit touches, say so
  and the next run will rebase them each time.

- **2026-07-25 (wtul-batch): two production bugs fixed and merged straight
  to `main`, not parked on a branch** (`c3e2988`, `d02f103`). Both were in
  code every real rip runs, so leaving them on a branch would have meant
  the next show night still hit them. (a) `album_dir_path()` didn't apply
  `abcde.conf`'s `mungefilename()`, so any disc with `'`, `"`, `?` or `:`
  in its metadata made wtul-rip look in a folder abcde never wrote to -
  resume-skip, live retagging and `fix <discid>`'s move all silently
  misfired. (b) `wtul-rip` with a non-terminal stdin spun a core at 100%
  and could traceback on the partial-disc prompt. **Neither needs hands-on
  hardware verification** (both are pure path/control-flow logic, tested
  against `abcde.conf`'s own shell function and with 3 new watch-loop
  tests) and **neither clears any hardware gate** - both milestone criteria
  are still exactly as gated on a real rip. Revert either with
  `git revert <sha>`.
- **2026-07-25 (wtul-batch): the rehearsal harness had a blind spot worth
  knowing about.** It could not have caught bug (a) above: `FakeDrive`
  takes its output path from `album_dir_path()`, so it reproduced the wrong
  folder faithfully and stayed green. Fixed on `rip-rehearsal-harness`
  (harness now takes the real `munge_filename` by injection, and its new
  punctuated-disc test asserts the folder *name*). The general lesson, if
  you want it applied more broadly: a rehearsal that derives its
  expectations from the code under test can only catch bugs *within* that
  code, never disagreements between the code and the external tool it
  models - those need a check against the real artifact (here, sourcing
  `abcde.conf` and running its function).
- **2026-07-25 (wtul-batch): all 8 feature branches rebased onto `main`
  again, this time onto real code changes rather than docs** - two needed
  manual conflict resolution (`spin-live-watch` in the watch loop,
  `discid-rerip-cache` adjacent to the new `munge_filename`), both resolved
  keep-both and re-tested green. This answers the prior round's open
  "strict-0-behind?" question in the only case that clearly matters: when
  `main` moves under a branch in code it touches, the rebase isn't
  optional. That question is still open for docs-only commits.
- **2026-07-25 (wtul-batch): triaged the two `fable-review` entries at the
  bottom of FOCUS.md; one was actively wrong.** It advised adding a comment
  naming `ROADMAP.md` as this project's source of truth - backwards since
  the 2026-07-24 migration, and following it would have pointed the next
  run at the retired stub. Struck through with the reasoning rather than
  deleted, so it isn't re-suggested from a clean slate. The other (a dexter
  deploy-key step in a `BLOCKERS` file) belongs to some other project -
  wtul has neither. **Worth a look at wherever that injector picks its
  target repo**, since one of two suggestions was wrong and the other was
  misdelivered.

- **2026-07-25 (wtul-batch, run 19): branch health after main absorbed
  three branches - no decision needed.** Found `detection-failure-earcon`,
  `label-printer-integration` and `spin-live-watch` merged to `main` since
  run 18 (merge commits tagged `[autonomy-tier:high, gate:tests-passed]` -
  not a wtul-batch action; noting for the record since every prior run
  held merges as a standing open question). Pruned those three refs
  (local + origin) per run 18's own rule for merged branches, then rebased
  the five survivors onto the post-merge `main` - all five conflicted in
  `bin/wtul-rip`/`tests/test_wiring.py`, resolved keep-both, every suite
  re-run green from scratch, force-pushed. Tips + pre-rebase SHAs in
  `~/reports/wtul/2026-07-25.md` (run 19). This run did NOT merge anything
  itself - the remaining five all still carry hardware-verification gates
  or (rehearsal harness) the hold-for-your-review note.
- **2026-07-25 (wtul-batch, run 19): #6's `speed` report would have said
  'No rip logs yet' forever - fixed on `rip-speed-monitoring`
  (`11cc903`), and the parser is now verified against real logs.** It only
  read `~/Music/mixes/.logs`, which doesn't exist until the first
  post-migration rip; all 37 real logs (incl. the 2026-07-24 live session)
  are at the legacy `~/Music/ripped/.logs`. It now reads both, merged
  chronologically (3 new tests, mutation-checked). Ran the report against
  the real history as a witness: 16 sessions with speed data, 30 tracks,
  overall median 23.2x (min 16.9x, max 27.6x), no slow-track flags, no
  degradation warning - your drive has been consistent across both log
  eras. STILL HARDWARE-GATED for merge: the live per-track `(read speed
  N.Nx)` print only fires during a real rip; the milestone criterion is
  unchanged.
- **2026-07-25 (wtul-batch, run 19): rehearsal would have physically
  printed a junk label - fixed on `rip-rehearsal-harness` (`6808e84`).**
  #3's merge to `main` put `print_label()` (real catprint/BLE - catprint
  exists on this machine) onto the rehearsed complete-disc path, so a full
  demo rehearsal with the M02 in range would have printed and wasted real
  label tape. Same containment class and same cause (main moved under the
  branch) as run 17's catalog-row leak. Now suppressed under rehearsal
  ('Label: print SUPPRESSED'), regression-tested, and witnessed by running
  the full demo disc for real. No hardware verification needed (the guard
  prevents hardware use; the ungated path is unchanged).
- **2026-07-25 (wtul-batch, run 19): built M02 mitigation (b) on new
  branch `m02-preprint-disconnect` (`affd850`) - NEEDS HANDS-ON PRINTER
  VERIFICATION, plus one finding that reframes the BLE mystery.** The
  finding (read-only, from `bluetoothctl info`): the M02 advertises a
  Human Interface Device (0x1812) service UUID, and BlueZ's *input plugin*
  auto-reconnects paired+bonded HID devices whenever they advertise -
  independent of KDE's trust flag, which is exactly why `bluetoothctl
  untrust` changed nothing on 2026-07-24 (and `bluedevilglobalrc`'s
  connectedDevices list is empty, so KDE login-reconnect isn't the actor).
  The build: `print_label()` now does a best-effort `bluetoothctl
  disconnect <mac>` right before invoking catprint, opt-in via
  `WTUL_PRINTER_MAC` (unset = exactly the old behavior; failures never
  block the print attempt; 5 new tests, mutation-checked). To try it on
  the next print session: add `WTUL_PRINTER_MAC=EA:F3:B6:A2:70:33` to
  `~/.config/wtul/secrets.env` (not done for you - the branch isn't
  merged, and activating it should coincide with you watching a print).
  This addresses the at-start collision only; the MID-print steal likely
  needs the dedicated session to try **unpairing** the M02 (a BLE-only
  catprint connection shouldn't need the bond, and unpairing is what makes
  the input plugin lose interest) - flagging that as the first experiment
  for that session rather than doing it unattended, since with the printer
  absent there'd be no way to re-pair or verify anything.

- **2026-07-26 (wtul-batch, run 20): main was BROKEN when this run started -
  fixed (`3f42a90`), but the cause needs your eyes on the auto-merger.** The
  three branches merged since run 19 (`discid-rerip-cache`,
  `m02-preprint-disconnect`, `rip-rehearsal-harness`, all tagged
  `[autonomy-tier:high, gate:tests-passed]`) were each green alone but
  broken together: completed discs now write a `.discid` marker, which the
  rehearsal tests' exact-listing assertions didn't expect (3 failures on
  main). Whatever runs that tests-passed gate evidently checks each branch
  before its own merge but does not re-run the suite on the merged result -
  the classic semantic-merge gap. **Worth fixing in the merger itself**: a
  post-merge suite run on main would have caught this at merge time. The
  same gap also broke `rip-speed-monitoring` far worse after rebase (24
  failures, below). No decision needed on the fix itself; the flag is about
  the merge gate.
- **2026-07-26 (wtul-batch, run 20): real production bug found under the
  same failures, fixed on `main` (`3f42a90`) - no hardware needed, none
  cleared.** `fix_by_discid()` moved only `*.mp3` out of an "Unknown Album"
  dir, so the `.discid` marker stayed behind: the emptied dir survived its
  cleanup, and - the real harm - `find_prior_rip()` would later match that
  marker and "already ripped" a re-inserted disc against a dir with no
  music in it, instead of the corrected folder. The marker now follows the
  moved music; rehearsal tests assert its presence/content; mutation-
  checked. Revert: `git revert 3f42a90`.
- **2026-07-26 (wtul-batch, run 20): `rip-speed-monitoring` rebased +
  repaired (`dcce0db`, 222/222) - STILL HARDWARE-GATED for merge, but its
  live print now rehearses.** Two things under one commit (`ad160fd`): (a)
  the branch widened `sh_live()` to return 5 values but main's now-merged
  rehearsal twin still returned 4, so every rehearsal on the rebased branch
  crashed at the first track (24 failures); (b) FakeDrive emitted its speed
  sample as prose that SPEED_RE never matched, so the live `(read speed
  N.Nx)` print - the branch's headline feature - silently never fired under
  rehearsal: the same harness-agrees-with-itself blind spot as run 18's
  mungefilename lesson. FakeDrive now emits cdparanoia's real `|N.Nx|`
  format, and a rehearsal witnesses the print for real. The milestone
  criterion is unchanged: a real rip is still the gate.
- **2026-07-26 (wtul-batch, run 20): third member of the rehearsal
  containment class, fixed on `web-photo-capture` (`ac85159`).** With
  `PHOTO_CAPTURE_URL` set in secrets.env, a complete rehearsal disc would
  have printed a pairing URL against the real GAS endpoint - inviting a
  phone upload keyed to a discid that doesn't exist (same class as the
  catalog row and the label print, same cause: main's features moving onto
  a rehearsed path). Pairing is now suppressed under rehearsal,
  regression-tested like its two predecessors.
- **2026-07-26 (wtul-batch, run 20): #10 (show-run sheet sweeper-prime web
  UI) - proposing defaults so one reply unblocks the build.** FOCUS.md
  gates this on three decisions; here is a concrete default for each, pick
  or veto per line: (a) *sheet read*: a bound Apps Script web app on the
  run-sheet serving row JSON via doGet - the exact pattern #8's
  catalog-writeback.gs.js already uses, no OAuth, needs only the
  run-sheet's URL from you (it isn't recorded anywhere in this repo); (b)
  *"cache"*: browser-held - the page fetches the next sweeper clip into a
  Blob/object-URL wired to an `<audio>` element, so playback is instant
  but the tab must stay open through the show (a to-disk cache for an
  external player would be a different build); (c) *where it runs*: any
  browser pointed at the GAS `/exec` URL, same hosting shape as #4/#8, no
  new server. Reply with the run-sheet URL + yes/veto per default and the
  next run builds it; silence keeps it deferred, not guessed at.

- **2026-07-26 (wtul-batch, run 21): built the third metadata-fix fallback
  on new branch `musicbrainz-fallback` (`5a872c8` + `07f880d`) - answers
  the 2026-07-24 "fallback metadata service" entry in its own suggested
  "MusicBrainz direct search by typed title" shape.** When AcoustID and
  Discogs both come back empty in `fix <discid>`, typing `? <text>` at the
  artist prompt (e.g. words read off the cover, or #7's OCR lines printed
  just above) now runs a keyless MusicBrainz free-text release search and
  offers numbered candidates; a pick becomes an editable suggestion, never
  applied blind - same confirm/edit discipline as #2/#7. 12 new tests
  (client shape-guards + 3 interactive rehearsal tests), two mutations
  verified caught, and the client was live-verified against the real
  MusicBrainz API (no key: "radiohead ok computer" -> one deduped
  `Radiohead - OK Computer (1997)` row). **The search itself needs no
  hardware; the full `fix <discid>` flow against a real freshly-ripped
  disc remains part of #2's existing real-rip gate - this doesn't clear
  it.** No decision needed from you.
- **2026-07-26 (wtul-batch, run 21): the auto-merger merged #4+#7
  (`ocr-metadata-extraction`, which contains `web-photo-capture`) into
  `main` (`81cdcc6`) - and this time the merged result is GREEN (255/255
  re-run from scratch), unlike run 20's broken arrival.** Difference: run
  20 had left every branch strictly 0-behind, so the merge had no semantic
  drift to trip over - evidence the 0-behind policy is what makes the
  merger's no-post-merge-test gap survivable. The run-20 flag on that gap
  stands. Merged refs pruned local+origin per the standing rule;
  `rip-speed-monitoring` (the last pre-existing branch) rebased onto the
  new main - same keep-both conflict class as before - and re-verified
  270/270 with the live speed print witnessed under rehearsal again; new
  tip `4f96cf1` (pre-rebase `dcce0db` to revert). Full demo rehearsal on
  merged main also witnessed: sandboxed rip, catalog + label both
  SUPPRESSED. Since #4's code is now on `main`, the phone-capture flow is
  one live session away from producing the real cover.jpg #7 needs.

- **2026-07-26 (wtul-batch, run 22): the auto-merger merged the
  hardware-gated milestone branch - a gate-order inversion worth your
  eyes, though nothing is broken.** `rip-speed-monitoring` (`82c771e`)
  and `musicbrainz-fallback` (`ea00116`) were both merged to `main` by
  the tests-passed auto-merger since run 21 - but the milestone
  criterion explicitly said "hardware-verified against a real rip,
  *then* merged", and run 21 had deliberately held `musicbrainz-fallback`
  back too. The merged result is fine (re-verified from scratch here:
  282/282, demo rehearsal witnessed with the live speed print firing and
  catalog/label suppressed, `speed` report re-witnessed against the real
  37-log history), refs pruned per the standing rule, nothing to revert.
  But the tests-passed gate evidently doesn't distinguish
  hardware-gated branches from ordinary ones, so from now on "it's on
  main" no longer implies "it's been watched working on real hardware".
  The judgment call for you: should the auto-merger skip branches whose
  QUESTIONS.md/FOCUS.md entries flag them hardware-gated (or honor some
  marker to that effect), or is merge-early-verify-on-main acceptable
  going forward? The next real rip remains the actual verification
  either way. (This is the second auto-merger flag; run 20's
  no-post-merge-test gap still stands.)
- **2026-07-26 (wtul-batch, run 22): two real bugs found stress-testing
  the newly-merged fix flow, fixed on `main` (`1c4f488`) - NO hardware
  verification needed, and none cleared.** (a) Ctrl+D at any of `fix
  <discid>`'s three prompts (artist, album, MusicBrainz pick) raised an
  uncaught EOFError that killed the entire watch session mid-show-night
  - the same class run 18 guarded on the partial-disc retry prompt,
  reintroduced by the new prompts; artist/album EOF now cancels the fix
  cleanly (never silently accepts a suggestion), pick EOF just declines
  the results. (b) The typed discid went into `glob.glob` unescaped, so
  `fix *` matched any parenthesized album name ("Album (Deluxe
  Edition)") and would have offered to move/retag the wrong folder; now
  matched literally via `glob.escape`. 4 regression tests, each
  mutation-checked against the pre-fix code. Revert: `git revert
  1c4f488`. No decision needed from you.
- **2026-07-26 (wtul-batch, run 23): built `wtul-rip doctor`, a no-disc
  preflight - branch `preflight-doctor` (`4aae15f`), NOT merged.** Answers
  "is this rig ready to rip?" from the machine alone: required binaries,
  /dev/sr0 present+readable, both abcde config files, disk space and mix-folder
  writability, stale lockfile, abandoned abcde scratch dirs, credentials, and
  metadata-service reachability. Exits nonzero on any FAIL so it can gate a
  script. 32 new tests, all against injected synthetic state (no drive, no
  network, no installed abcde); both directions of its central comparison
  mutation-checked; 318/318 overall. **Hardware verification status:** the
  doctor itself needs none - it *reports on* hardware rather than using it,
  and it was witnessed live on this machine (correctly FAILing on the absent
  drive, with real network probes to Spinitron/AcoustID/Discogs/MusicBrainz).
  What it cannot do is prove a rip works; a green doctor means "nothing known
  is broken", not "verified end to end".
- **2026-07-26 (wtul-batch, run 23): the doctor's first run found a live
  production breakage on this machine, and I fixed it outside the repo -
  please sanity-check.** The installed `~/.abcde.conf` still had
  `OUTPUTDIR=$HOME/Music/ripped`: the 2026-07-24 ripped->mixes migration
  changed the repo's copy, but `install.sh` silently leaves an existing
  `~/.abcde.conf` alone, so the live machine never got it. The next real rip
  would have written into the retired `~/Music/ripped` while `wtul-rip` looked
  in `~/Music/mixes/<date>` - abcde "succeeds", every downstream step
  (tracklist, retagging, catalog write-back, re-rip cache) reads an empty
  directory. Since it would have broken the next show night, I installed the
  repo's `abcde.conf` over it; the previous file is backed up verbatim at
  `~/.abcde.conf.pre-mixes-migration.2026-07-26` (restore with `cp`), and it
  differed from the repo's copy in *only* those two variables. **If you had
  hand-edits in that file, check the backup.** `install.sh` on the branch now
  diffs and warns loudly instead of staying quiet - it still never overwrites.
- **2026-07-26 (wtul-batch, run 23): judgment call - should `doctor` become a
  gate rather than a thing you remember to run?** It's currently opt-in
  (`wtul-rip doctor`). The options: (a) leave it opt-in; (b) run it
  automatically at `wtul-rip` startup and print warnings but never block;
  (c) run it at startup and refuse to enter the watch loop on a FAIL. (c) is
  the safest for show night but would have refused to start on this very
  machine today (no drive attached) even for rehearsal use, so I did not guess
  - it changes the tool's behavior for you, not just its capability. Tell me
  which and it's a small change.
- **2026-07-27 (wtul-batch, run 24):** your reply to the 2026-07-18
  (b)/(c)/(d) entry is consumed and that entry is deleted per this file's
  contract. What each answer became, so none of it is lost with it:
  **(b)** the sheet URL you gave is the same one #8 has been writing to
  since 2026-07-20, and its columns match what's recorded there - so the
  only new instruction was attribution. Built: `DJ NAME` now goes on every
  catalog row, defaulting to "Guy" (branch `catalog-dj-name`, see the next
  entry). `DATE` was already the date entered. **(c)** Phomemo M02 -
  matches the 2026-07-20 decision already in FOCUS.md #3; nothing changed,
  the M02 work is built and waiting on a dedicated printer session, not on
  this answer. **(d)** Android + host on Apps Script - recorded in FOCUS.md
  #4/#10, along with the HUD project link you gave
  (`script.google.com/.../1ed2WEziF9LVxsAm_RdAXmh4y61GZevBSD8NRvZJn6x4UcE7sdPQDH9uE`)
  and the "tabbed page design" steer. That link is new information this
  repo did not have: #4 was built against the *other* GAS project (the one
  bound to the photo-capture sheet), and #10 had no host at all.
- **2026-07-27 (wtul-batch, run 24): built, branch `catalog-dj-name`
  (`b28240b`), NOT merged.** Adds the `DJ NAME` column to #8's catalog
  write-back - every row written since 2026-07-20 has landed in the
  rotation catalog unattributed. Default "Guy", override with
  `WTUL_DJ_NAME`, an explicitly empty value writes no DJ NAME rather than
  attributing someone else's rips to you. 4 new rehearsal tests, both
  mutations caught, 322/322. **Still needs hands-on verification**, though
  a weak form: the key match is live-verified (the deployed endpoint's
  `?scope=schema` reports the header as exactly `DJ NAME`, read-only GET,
  nothing written), but only a complete rip of a real disc actually puts a
  row in the sheet. Check the LOCAL tab's DJ NAME column after the next
  real rip.
- **2026-07-27 (wtul-batch, run 24): a judgment call I did not make for
  you - should the catalog row carry GENRE/YEAR/LABEL too?** The sheet has
  those columns and this repo already has the lookup that fills them
  (`discogs_genre_year()`, built for the mix label in #3), so it is a small
  change. I did not build it: you asked for DJ NAME and DATE specifically,
  and a Discogs genre guess written into the station's rotation catalog is
  harder to walk back than a blank cell - there is still no delete
  endpoint. Say the word and it ships next run.
- **2026-07-27 (wtul-batch, run 24): FYI, no action needed - wtul's
  FOCUS.md/QUESTIONS.md moved from `.claude/` to `.scheduler/`** (this
  file's new home; wtul `9539e30`, scheduler `07a9bbf`). That is the
  migration that had been sitting in scheduler's `BLOCKERS.md` since
  2026-07-24. Full record, including a correction to the belief that an
  unattended run could not do it, is appended under `## wtul` there
  (scheduler `33ca45f`).
- **2026-07-27 (wtul-batch, run 25): built, branch `catalog-outbox`
  (`51d9632`) — a completed rip can no longer silently lose its catalog
  row.** When the write-back failed, `wtul-rip` printed one line ("add it
  to the sheet by hand if it matters") and forgot the row; on show night
  that line scrolls off behind the next disc's tracklist. Putting the disc
  back in doesn't help either — every track is already ripped, so the rip
  returns before it ever reaches the write-back. Failed rows now queue to
  `~/Music/mixes/.catalog-outbox.json`, and are retried at the next
  `wtul-rip` startup, by a new `catalog` command (or `wtul-rip catalog`,
  which needs no drive — runnable from a laptop the morning after), and
  listed by `doctor` until they land. **Still needs your hands-on
  verification**: the retry path has only ever run against a host that
  doesn't resolve. A real rip whose catalog write actually fails, then
  succeeds on retry into the real sheet, is the witness. 37 new tests
  (359 total), mutation-checked; no disc was ripped and nothing was
  written to the real sheet this run.
- **2026-07-27 (wtul-batch, run 25): a real tradeoff in the retry, worth
  your call — the flush drops a queued row if that ARTIST+ALBUM already
  appears in the sheet's last 50 rows.** This is deliberate: `write_row`
  returns False both when the POST failed *and* when it landed but the
  confirming GET failed, so re-POSTing a queued row blind is how one
  network blip becomes a duplicate you delete by hand. The cost is the
  mirror case: if you genuinely re-catalogue the same album (a re-rip, a
  second copy for rotation) while the first row is still within the last
  50, the retry reports it as "already in the sheet" and drops it instead
  of writing a second row. I picked that way round because a missing row
  announces itself and a duplicate doesn't, and because you have no delete
  endpoint. Say so if you'd rather it always write and you'll delete
  duplicates by hand.
- **2026-07-27 (wtul-batch, run 25): FYI, a pattern worth a standing
  rule.** This run's own feature was caught POSTing a rehearsal's
  simulated album at the live catalog URL — `catalog_retry()` gated its
  suppression on `SIM`, which is built by `init_simulation()`, and the new
  `catalog` subcommand exits before the watch loop and so never calls it
  (fixed to gate on `SIMULATING`, `51d9632`). That is the **fifth**
  instance of one class (2026-07-25's catalog leak and label print, run
  20's photo pairing, run 19's harness print). Proposed rule, adopt or
  drop: *any new entry point that can touch the sheet, the printer or the
  phone endpoint gets checked against the rehearsal guard — and the check
  is running it, not reading it.* All five were found by running, none by
  review.
