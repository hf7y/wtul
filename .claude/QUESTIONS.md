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
- **2026-07-18 (wtul-batch):** Deferred, needs your decision before I build (a genuine either/or, not "should I"): (a) ROADMAP #2 metadata-fix API — AcoustID/Chromaprint (needs `fpcalc`, NOT installed here, + an AcoustID key) vs Discogs API (needs a Discogs token); pick one. (b) ROADMAP #8 catalog spreadsheet — where does the sheet live and its format/columns (Google Sheets + OAuth vs local .csv/.xlsx)? (c) ROADMAP #3 label printer — which printer model? (d) ROADMAP #4/#7 web-photo/OCR — need a phone + hosting decision. #3/#4/#7 are hardware-gated, so they can't be verified unattended even once built.



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
  have a physical eject button.** Surfaced during live testing (`q` got
  stuck / disc needed manual handling with no way to eject from the
  drive itself). Idea: a `wtul-rip` command (e.g. `eject`) that shells
  out to `eject <dev>` so the disc can be ejected from the keyboard
  instead. Not built - no confirmed need yet beyond this one session,
  and worth checking `eject` actually works against this drive
  (SuperDrive quirks already bit us once today) before wiring it in.
