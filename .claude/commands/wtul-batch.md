---
description: Weekly/bi-weekly thorough pass on ROADMAP.md's deeper integrations -- no live tracker, this project's backlog lives in ROADMAP.md directly
---

<!-- Adapted from Project Archive/scheduler/examples/nightly-batch.md.template
     for a project with no web-facing tracker: wtul is a personal CLI/
     hardware-automation tool (CD ripping), not a live web app with end
     users filing bugs, so this skips the INTAKE.md tracker steps
     (fetch/resolve reports, NIGHTLY: handoff, sweep-status POST) that
     template assumes. ROADMAP.md IS the backlog here, not a tracker. -->

This runs unattended, on a weekly/bi-weekly cadence (the show this
project supports is weekly), with no human review step until the user
next opens the machine. Build first, don't just analyze: pick the most
reasonable interpretation of a ROADMAP.md item and build it, on its own
branch, flagged in `.claude/QUESTIONS.md` and the report. Only actually
stop and wait for the user when the action itself can't be reverted --
an ordinary commit, branch, or report write never qualifies.

## 0. The hardware constraint - read this first

This project automates ripping physical CDs via a real optical drive
(`/dev/sr0`) using `abcde`/`cdparanoia`/`eyeD3`. An unattended batch run
has **no physical disc to insert and no guarantee this machine even has
a drive attached when the job runs**. That means:

- Do NOT claim a ROADMAP.md item is "done" or "working" based on this
  run alone if it depends on actually reading a disc, talking to the
  drive, or anything else that needs physical hardware present. Build
  the code, get it to compile/typecheck/pass any tests that don't need
  real hardware, and explicitly flag in the report that it still needs
  the user's own hands-on verification with a real disc before it's
  trusted in production.
- Things that ARE safely buildable/testable unattended: parsing logic,
  API client code against a real external service (Spinitron, AcoustID,
  etc. - these can be tested for real without a CD), config file changes,
  the CLI's non-hardware code paths (history/status/fix-by-discid logic
  can be unit-tested against synthetic files), documentation.
- Things that are NOT safely claimed as done unattended: anything
  touching cdparanoia/abcde/the drive itself, the label-printer
  integration (needs the actual printer), the phone-photo web app's
  actual capture flow (needs a phone).

## 1. Orient

`git log --oneline -10`, current branch state, `README.md` if one
exists, and `ROADMAP.md` in full. If a previous batch run left work in
progress (check the last report under `~/reports/wtul/`), pick up from
there rather than starting over.

## 2. Re-verify anything a previous run touched, from scratch

Do not trust a prior run's own claims about what works. Re-run whatever
non-hardware checks are available (syntax/compile checks, any existing
test harness) before building further on top of it.

## 3. Push forward, building rather than just analyzing

Pick the most tractable, highest-value item(s) from `ROADMAP.md` given
the time budget (`MAX_TURNS`) - there's no separate FOCUS.md here, use
judgment on what's worth advancing this round; note the choice and why
in the report. Commit as you complete meaningful chunks; do not save it
all for one giant commit at the end.

A feature (or any distinct new idea) gets its own branch off `main`,
named for what it is, pushed on its own - don't stack unrelated new work
onto whatever branch happens to be checked out.

If a ROADMAP.md item turns out to need a real decision only the user can
make (which API/vendor, which hardware, a genuine tradeoff), don't guess
- write it up in `.claude/QUESTIONS.md` and move to the next item instead
of blocking the whole run on it.

## 4. Stress-test what you built (within the hardware constraint above)

For anything not gated on physical hardware: look for edge cases, empty
states, malformed input, what a first pass typically misses. Fix what
breaks; note what's genuinely out of scope for this round.

## 5. Flag what you built, and anything needing the user's own judgment

Append-only in `.claude/QUESTIONS.md`, format
`- **YYYY-MM-DD (wtul-batch):** <text>`:

- Every feature/distinct new idea built this round - which branch, what
  it does, in one or two lines, and **explicitly whether it still needs
  hands-on hardware verification** before being trusted.
- A genuine judgment call needing the user's own decision (not "should I
  build this" - default yes, per ROADMAP.md - but a real tradeoff or
  ambiguous direction).

## 6. Write the report

`~/reports/wtul/$(date +%Y-%m-%d).md`, and update `~/reports/wtul/LATEST.md`
to match it. Cover: what shipped (with commit references), what's still
pending hands-on hardware verification, what was deliberately deferred
and why, and whether anything got appended to `.claude/QUESTIONS.md`
(point at it, don't duplicate its full text here).

## 7. Before finishing

Confirm every meaningful change has a real commit, pushed to origin. A
batch run that isn't saved anywhere didn't happen.
