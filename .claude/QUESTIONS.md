# Questions for the user

Running log, appended to (never overwritten or trimmed) by `/wtul-batch`
whenever something bigger than a routine report note comes up. Clear an
entry by deleting its line once you've actually read and dealt with it;
that's the only thing that should ever remove something from this file.

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
