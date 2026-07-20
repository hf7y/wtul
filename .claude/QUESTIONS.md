# Questions for the user

Running log, appended to (never overwritten or trimmed) by `/wtul-batch`
whenever something bigger than a routine report note comes up. Clear an
entry by deleting its line once you've actually read and dealt with it;
that's the only thing that should ever remove something from this file.

- **2026-07-18 (wtul-batch):** Built ROADMAP #6 (rip-speed monitoring) on branch `rip-speed-monitoring`. Adds `wtul-rip speed` (+ interactive `speed`) reporting per-session/overall median extraction speed from existing logs, slow-track flags, and a degradation warning; plus a live `(read speed N.Nx)` line per track. Parser is unit-tested against real logs. NEEDS HANDS-ON HARDWARE VERIFICATION: the live per-track print only fires during a real rip with a disc — merge/trust after you've watched one real rip. No decision needed from you.
- **2026-07-18 (wtul-batch):** Built the hardware-free core of ROADMAP #1 (Spinitron prioritization) on branch `spinitron-priority-matching`: `lib/spinitron.py` (fuzzy match + queue reorder + thin `/api/spins` client), unit-tested. NOT wired into the rip flow and never run against the live API. DECISION/INPUT NEEDED: please provide the station's Spinitron API key + station ID (Spinitron → Settings → API) so the next run can wire `fetch_recent_spins` into `rip_session()` and tune the 0.82 match threshold against real spin data. Where to put the secret safely (env var? a gitignored config file?) is also your call.
- **2026-07-18 (wtul-batch):** Deferred, needs your decision before I build (a genuine either/or, not "should I"): (a) ROADMAP #2 metadata-fix API — AcoustID/Chromaprint (needs `fpcalc`, NOT installed here, + an AcoustID key) vs Discogs API (needs a Discogs token); pick one. (b) ROADMAP #8 catalog spreadsheet — where does the sheet live and its format/columns (Google Sheets + OAuth vs local .csv/.xlsx)? (c) ROADMAP #3 label printer — which printer model? (d) ROADMAP #4/#7 web-photo/OCR — need a phone + hosting decision. #3/#4/#7 are hardware-gated, so they can't be verified unattended even once built.
- **2026-07-19 (Spinitron API key): acknowledged, mine to get.** #1's
  wiring is built and unit-tested (`SPINITRON_API_KEY` env var, silent
  no-op until set) but has never been called against the real API. User
  will obtain the station's Spinitron API key + station ID directly
  (Settings > API in Spinitron, per ROADMAP.md #1) -- not something a
  nightly run can do. No need to keep flagging this as blocking; once the
  key is set in the environment, the next rip will exercise it live.
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
