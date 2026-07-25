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
(`collect-feedback.sh .claude/QUESTIONS.md --consume`), treats any `> `
reply as authoritative, acts on it, then removes that question's whole
entry (git history + that run's report keep the record) -- that's the
only thing that should ever remove something from this file. To dismiss
a question without any action, you can still just delete its line by
hand.

- **2026-07-18 (wtul-batch):** Built ROADMAP #6 (rip-speed monitoring) on branch `rip-speed-monitoring`. Adds `wtul-rip speed` (+ interactive `speed`) reporting per-session/overall median extraction speed from existing logs, slow-track flags, and a degradation warning; plus a live `(read speed N.Nx)` line per track. Parser is unit-tested against real logs. NEEDS HANDS-ON HARDWARE VERIFICATION: the live per-track print only fires during a real rip with a disc — merge/trust after you've watched one real rip. No decision needed from you.
- **2026-07-18 (wtul-batch):** Deferred, needs your decision before I build (a genuine either/or, not "should I"): (a) ROADMAP #2 metadata-fix API — AcoustID/Chromaprint (needs `fpcalc`, NOT installed here, + an AcoustID key) vs Discogs API (needs a Discogs token); pick one. **(a) RESOLVED 2026-07-24: Discogs, token already in hand — see FOCUS.md's stability milestone, which now lists #2/Discogs as a milestone criterion still needing build + live-verification.** (b) ROADMAP #8 catalog spreadsheet — where does the sheet live and its format/columns (Google Sheets + OAuth vs local .csv/.xlsx)? (c) ROADMAP #3 label printer — which printer model? (d) ROADMAP #4/#7 web-photo/OCR — need a phone + hosting decision. **(b)/(c)/(d) RECLASSIFIED 2026-07-24 (realisateur): (parked)** — all three sit past wtul's current stability milestone (rip-speed monitoring + Discogs metadata-fix only), already named in FOCUS.md's parked list; no longer presented as blocking decisions until the milestone is reached and a new one promotes them into the active set. #3/#4/#7 remain hardware-gated regardless.



- **2026-07-19 (Spinitron API key): acknowledged, mine to get.** #1's
  wiring is built and unit-tested (`SPINITRON_API_KEY` env var, silent
  no-op until set) but has never been called against the real API. User
  will obtain the station's Spinitron API key + station ID directly
  (Settings > API in Spinitron, per ROADMAP.md #1) -- not something a
  nightly run can do. No need to keep flagging this as blocking; once the
  key is set in the environment, the next rip will exercise it live.
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
  device decision). Not built this round.
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
  suite re-verified clean (86/86). See `.claude/FOCUS.md`'s #7 section
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

