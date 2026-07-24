# Live-test debrief — wtul (2026-07-24)

First hands-on session against real hardware (Apple USB SuperDrive) and
real discs since most of this week's work landed as unit-tested-only
branches. Short, cite-first — scope is this one session, not a full
retrospective.

## What broke, live, and got fixed same-session

- **`cddbread.N` isn't always `.0`.** abcde numbers the CDDB match file
  by chosen-match index, not always 0 — a disc with exactly one
  MusicBrainz hit wrote `cddbread.1`. The hardcoded `.0` path silently
  found nothing and aborted the rip with "Metadata scrape failed to
  produce a discid" even though the scrape itself succeeded. Now
  discovers the real file instead of assuming its name (`9b19263`).
- **Per-track abort used the wrong discid.** abcde's `-C` resume flag
  and its scratch-dir naming key off the TOC-based discid
  (`cddbdiscid`), but the code was passing whichever `DISCID=` field the
  winning metadata source wrote — correct for plain CDDB, wrong for
  MusicBrainz (different ID scheme), so every track aborted with
  "Discid undefined" whenever MusicBrainz was the only hit. Now always
  resolves the TOC discid regardless of which source matched (`5bb7258`).
- **No CDDB/MusicBrainz match aborted the whole rip.** Now falls back to
  ripping as "Unknown Artist"/"Unknown Album" using the disc's own
  always-available TOC discid, correctable later via the existing
  live-fix commands or `fix <discid>` (`a712b37`).
- **`install.sh` never deployed `lib/`.** `wtul-rip` imports
  `lib/spinitron.py` etc. relative to its own location; the installed
  copy only ever got the single script, so any installed build crashed
  with `ModuleNotFoundError` the moment it touched an import. Worked by
  accident until today because the installed binary predated those
  imports. Now installs the whole `bin`+`lib` tree and symlinks the
  entry point onto `PATH` (`2477751`).

## Behavior changed live, on user direction

- **Spinitron gating reverted.** A same-day earlier change had gated
  ripping on a Spinitron match; live use showed this too restrictive
  (ripping now always starts at track 1 immediately, Spinitron surfaced
  as informational only). Added an `only <N>`-style manual command to
  still target a specific track on demand (`9e072aa`).
- **Eject soft-key added.** The SuperDrive has no physical eject button;
  `e` now ejects from the keyboard at any idle/retry prompt, not just
  mid-rip (`f218be8`).

## What's now real-verified vs. still not

**Live-verified today:** the whole non-hardware metadata-fix path (#2) —
`fpcalc` fingerprinting real audio, a real AcoustID HTTP round-trip, a
real Discogs catalog hit for a test artist. Spinitron's public-scrape
path, CDDB/MusicBrainz fallback, and the four fixes above were all
exercised against real discs this session.

**Still not:** `fix_by_discid()`'s AcoustID/Discogs suggestion flow has
never run against an actual freshly-ripped disc end-to-end (next
previously-unidentified disc is the real test) — see ROADMAP #2.
Rip-speed monitoring (#6), label-printer integration (#3), and
web-photo-capture (#4, and #7 which depends on it) are all built but
have never been exercised against real hardware at all.

## The finding that matters most for what's next: branch staleness

Every one of those built-but-unverified features (#3, #4, #6, #7) lives
on a branch that **predates today's four fixes above** — `main` has
moved 13–36 commits past each of them. Picking any of them back up as a
plain merge would silently *reintroduce* bugs this session just caught
live. Full detail in `.claude/FOCUS.md`'s "Branch health" note and
ROADMAP.md's per-item status blocks; the short version: **rebase before
touching, for all four, starting with `rip-speed-monitoring`** since
it's the one item standing between wtul and its current stability
milestone.

One branch, `spinitron-priority-matching`, looked like a fifth stale
branch but is a false alarm — already fully merged into `main`, just an
unpruned local ref. Deleted (`git branch -d`, confirmed merged first —
no non-merged commit is on it, nothing lost).

## Today's wrap-up (this session)

- QUESTIONS.md: resolved the stale metadata-API either/or, parked the
  three items past the milestone bar that were still phrased as open
  decisions.
- FOCUS.md: corrected the parked-ideas list (#8 was wrongly listed —
  it's done, not parked) and added the branch-health finding above.
- ROADMAP.md: added accurate built/stale status to #3, #4, #6, #7 (none
  had ever recorded that they were sitting on unmerged branches).
- `.gitignore`: added `.scheduler-autocommit.log` (empty scheduler
  debris file that was showing up as untracked in every `git status`).
- Deleted the dead, already-merged `spinitron-priority-matching` local
  branch ref.

## Foundation for the next dev cycle

1. **Rebase `rip-speed-monitoring` onto `main`, then hardware-verify it
   against a real rip.** Closes the last open milestone criterion.
2. **Live-verify `fix_by_discid()`'s Discogs suggestion path** against a
   real previously-unidentified disc. Closes the other open criterion.
3. Once both land, wtul's current stability milestone is reached —
   time to set the next one and decide, deliberately, which of the
   parked items (#3/#4/#7/#9/#10) get promoted into it (see
   `STABILITY-MILESTONES.md`'s lifecycle: promotion is a stated
   decision, not a default).
4. The other three stale branches (#3, #4, #7) don't need to move until
   promoted — but they'll keep drifting further behind `main` the longer
   they wait, so factor that into whenever they're picked back up.
