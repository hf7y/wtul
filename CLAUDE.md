# CLAUDE.md

## Push permission (2026-07-22, human-directed)

Claude may push committed changes directly to `origin/main` without
asking each time, for ordinary work in this repo. Flag every such push in
the next report/summary (what was pushed, why, and how to revert it —
`git revert <sha>`). This does not license skipping review of what goes
into a commit in the first place, only the push step itself.



## Build discipline (realisateur baseline — see realisateur/BUILD-DISCIPLINE.md)
Before marking anything done:
- [ ] Fails **loud**? (no exit-0 no-ops; pipefail+SIGPIPE guarded)
- [ ] **Wired to a real path** (boot/timer/enabled-flag), not just built?
- [ ] "Working" backed by a **test name or human-sense witness**, not exit code alone?
- [ ] New mechanism **names what it retires**?
- [ ] Config read from **one source**, not retyped per file?
- [ ] Deploy verified against a **git ref**; drift fails loud?
- [ ] **No secret** in a tracked file; tree clean of build debris?
