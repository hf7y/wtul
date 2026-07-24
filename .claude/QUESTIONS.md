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
