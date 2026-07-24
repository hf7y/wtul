<!-- Per-project scope marker -- read FIRST by wtul's own nightly-batch/
     bug-sweep before touching anything else. -->

## Stability milestone

**Current (2026-07-24, realisateur):** wtul reliably rips a disc
end-to-end with correct track metadata (Spinitron public-scrape +
Discogs lookup, both credential-free) and logs it in a form Zach can
trust without hand-checking — status: in-progress
Done when:
- [x] FOCUS.md/ROADMAP.md reconciliation done (thin pointer above, kept
      2026-07-24)
- [ ] rip-speed monitoring (`rip-speed-monitoring` branch) hands-on
      hardware-verified against a real rip, then merged
- [ ] metadata-fix API (#2) built against Discogs (decided 2026-07-24,
      token already in hand) and live-verified against a real rip

Ideas beyond this bar are PARKED by default (see
realisateur/STABILITY-MILESTONES.md): capture-on-play pipeline
front-end (#9), label printer (#3), catalog spreadsheet (#8), web-photo/
OCR (#4/#7), show-run sheet (#10) — all deeper-integration items still
needing hardware/design decisions the user hasn't made yet (see
QUESTIONS.md's 2026-07-18 either/or, parts b/c/d).

## Current focus

`ROADMAP.md` (repo root) is the single source of truth for the real
backlog -- ten numbered deeper-integration items, each needing research/
design/hardware access, not yet implemented. This section is a short,
curated pointer into it (kept intentionally thin to avoid drift between
two copies of the same list); read `ROADMAP.md` directly for full detail
on any item before starting it.

1. Capture-on-play (#9) -- the not-yet-designed front end for the
   pipeline vision (play -> auto-rip -> curate -> burn+label ->
   re-enter rotation); currently the biggest unblocked-but-undesigned
   piece.
2. Label printer integration (#3) and catalog spreadsheet (#8) -- the
   burn+label and re-enter-rotation legs of the same pipeline.
3. Metadata API fix-up (#2), web app + phone photo capture (#4), OCR on
   the photo-scan layer (#7) -- independent quality-of-life items on the
   ripping side, not blocking the pipeline.
4. Rip-speed monitoring (#6) -- built on branch `rip-speed-monitoring`
   2026-07-18, needs hands-on hardware verification against a real rip
   before merge/trust (see QUESTIONS.md).
5. Show-run sheet / sweeper integration (#10) -- not designed yet,
   flagged not built.

(realisateur, 2026-07-24: fleshed out per `FOCUS-md-formatting-
compliance-*.idea` -- reconciled the FOCUS.md-vs-ROADMAP.md split by
keeping ROADMAP.md as the real detail doc and this file as a thin,
parseable pointer, rather than migrating content wholesale. Not
blocking: wtul's regular scheduled dispatch should continue running
against this format regardless.)

## Ideas (added via `scheduler -i`)

- **2026-07-22 14:58 (via `scheduler -i`): RESOLVED 2026-07-24
  (realisateur).** FOCUS.md fleshed out above with a real `## Current
  focus` pointer into `ROADMAP.md` so `scheduler status wtul`'s next-up
  parser can see it.
