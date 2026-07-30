# CONTRACT — `grave`

**engrave the disc**: turn a physical CD into a trustworthy radio record —
ripped, identified, tagged, and logged where the station can find it again.

Derived 2026-07-30 from what is actually in `/home/zach/Documents/wtul`
(path from `scheduler/schedule/wtul.conf`, which differs from the
`Projects/` guess). This **revises** the CONTRACT.md on `origin/bashified`
rather than replacing it. That document listed four subcommands whose
promise was written as *"whatever `bin/cd-autorip.sh` promised"* — a
placeholder, honestly labelled. This one states the promises.

**It also corrects that document's shape.** The prior contract treated
`cd-autorip`, `wtul-rip`, `install` and `install-tesseract-local` as four
peers. They are not: `bin/wtul-rip` is a 1799-line front door with three
real subcommands (`speed`, `catalog`, `doctor`) plus a default watch loop,
`cd-autorip.sh` is the rip engine it drives, and the two installers are
deployment. Counting them as four equal subcommands understated the first
and overstated the last two.

`grave` is **not on `PATH`** (`command -v grave` → nothing, probed
2026-07-30). What is on `PATH` is `/usr/local/bin/wtul-rip` (a root-owned
symlink into `/usr/local/lib/wtul-rip/`) and `/usr/local/bin/cd-autorip.sh`.
The mechanization is real; the verb surface is not built yet.

## How to read the HOW column

| HOW | meaning | exit when unmet | cost |
|---|---|---|---|
| **bash** | mechanized. Runs free, unattended, no model in the loop. | 5 if it ran and broke | free |
| **summon** | SHOULD DO — in scope, not yet mechanized. | 4 (GAP), naming its own escalation | metered, printed before spending |
| **refused** | WON'T DO — out of scope on principle. | 7 (REFUSED) | n/a, no summon exists |

`--summon` is **available on 4 and forbidden on 7**. A gap names its
escalation; a refusal offers none, because having no escalation path is
what refusing on principle means.

## The obligations

### Engraving — getting the audio off the disc

| obligation | HOW | backed by |
|---|---|---|
| Rip an inserted audio CD to tagged MP3 | bash | `bin/cd-autorip.sh` → `abcde`, driven by `rip_session()` in `bin/wtul-rip`. Interactive by design (a human sets track priority), but no model is in the loop. |
| Survive an interrupted rip without losing finished tracks | bash | `abcde.conf` `LOWDISK=y` — one track encoded at a time, wav deleted on write, so no half-written track exists. Stated in `bin/cd-autorip.sh`'s header. |
| Refuse to start a rip that cannot finish | bash | `bin/cd-autorip.sh`: `MIN_FREE_KB=524288` (<512MB free = refuse), `MAX_RUNTIME=2700` (45-min wall cap), `MAX_LOG_BYTES=5000000`, `flock` on `/tmp/cd-autorip-<dev>.lock`. |
| Not let one dying drive grow a log without bound | bash | same file: log cap plus `KEEP_LOG_DAYS=14` pruning. |
| Report rip speed so a degrading drive is visible before show night | bash | `wtul-rip speed` (`speed_report()`), reading past rip logs. Read-only, no drive needed. |
| Hardware-verify that speed report against a real rip | summon | undetermined — code merged to `main` (`82c771e`, 2026-07-26) BEFORE verification; `.scheduler/FOCUS.md` still carries this as an unchecked stability-milestone box. Settled only by one real disc on the real drive. |

### Identifying — knowing what the disc is

| obligation | HOW | backed by |
|---|---|---|
| Scrape metadata on insert, before ripping | bash | `lib/spinitron.py` + `lib/metadata_lookup.py`, called from the watch loop. |
| Prioritize tracks the station has already aired | bash | `lib/spinitron.py`; corpus at `etc/spin-match-corpus.json`, scored by `scripts/spin-match-eval.py`. |
| Identify a disc no database knows, after the fact | bash | `fix_by_discid()` in `bin/wtul-rip` — the disc ID is baked into the `Unknown Album (discid)` folder name, so it works after the session has moved on. Falls back to MusicBrainz search, then a manual prompt. |
| Resolve an unidentified disc from audio fingerprint | bash | `lib/metadata_lookup.py` — AcoustID primary, Discogs fallback. |
| Live-verify that metadata-fix path against a real rip | summon | undetermined — `.scheduler/FOCUS.md`'s second unchecked milestone box; the Discogs token is in hand, the disc is not. |
| Read cover art off a phone photo when no database matches | summon | built but unverified: `lib/photo_capture.py` + `gas/photo-capture.gs.js` (upload), `lib/ocr_metadata.py` + `scripts/install-tesseract-local.sh` (OCR). No run against a real unidentified disc is recorded. |

### Logging — the record the station reads

| obligation | HOW | backed by |
|---|---|---|
| Write every ripped album to the station catalog sheet | bash | `lib/catalog_writeback.py` → `gas/catalog-writeback.gs.js`, matching keys to the sheet's real column headers by name. |
| Not believe a write that did not land | bash | `catalog_writeback.write_row()` re-GETs to confirm; it distinguishes "the POST landed" from "the POST's response lied". |
| Not lose a row when the network is down at the venue | bash | `lib/catalog_outbox.py` — durable outbox; `wtul-rip catalog` retries the morning after from anywhere. |
| Notice when the sheet's schema drifts out from under the writer | bash | `preflight.check_catalog_schema` (`?scope=schema`, read-only) compared against `catalog_writeback.build_row`'s keys. |
| Decide whether GENRE/YEAR/LABEL belong in the catalog row | summon | undetermined — an open design question addressed to Zach in `.scheduler/FOCUS.md`/`QUESTIONS.md`. Settled by Zach answering, not by picking a default. |
| Print a case label for a finished mix | summon | `lib/label_render.py` + `lib/mix_label.py` render correctly and are unit-tested; `print_label()` is the only piece touching the Phomemo M02 over BLE and has never run. Settled by one M02 session. |

### Readiness — answering "is this rig ready?" without a disc

| obligation | HOW | backed by |
|---|---|---|
| Answer "can this rig rip tonight?" with no disc and no drive | bash | `wtul-rip doctor` → `lib/preflight.py`, 13 named checks (`check_binaries`, `check_mutagen`, `check_drive`, `check_conf_files`, `check_outputdir_matches_ripdir`, `check_disk`, `check_writable`, `check_lock`, `check_stale_tempdirs`, `check_credentials`, `check_network`, `check_catalog_outbox`, `check_catalog_schema`). Exits nonzero on any FAIL, so `wtul-rip doctor || ...` is meaningful. |
| Catch a repo-side config change that never reached the installed copy | bash | `check_outputdir_matches_ripdir` — this check exists *because* run 23 found `~/.abcde.conf` still writing to the retired `~/Music/ripped` while `wtul-rip` read `~/Music/mixes/<date>`. A config change is not deployed until something checks the installed copy. |
| Distinguish a stale lockfile from a live rip | bash | `_lock_is_stale()` in `bin/wtul-rip`, wired into `check_lock`. |
| Rehearse a whole rip with no disc and no drive | bash | `lib/fake_drive.py`; `tests/test_rip_rehearsal.py`, `tests/test_watch_loop_stdin.py`. |
| Prove the tree still works, unattended | bash | 401 named test functions across `tests/` (counted 2026-07-30, `grep -rhc '^def test' tests/*.py`); the gate is declared outside the repo as `BATCH_TEST_CMD="pytest -q"` in `schedule/wtul.conf`, with `AUTONOMY_TIER="high"` explicitly gated on it. |
| Speak the 4/5/6/7 exit vocabulary | summon | **not implemented.** `doctor()` returns 1-or-0; the only other coded exit is `sys.exit(2)` at `bin/wtul-rip:933`. So "no drive attached" (BLIND, 6), "no disc metadata source reachable" (GAP, 4) and "the rip broke" (BROKEN, 5) are indistinguishable to a caller. Settled by a `lib/verb.sh`-style dispatcher on the verb front door. |
| Be invocable as `grave` | summon | `bin/grave` exists only on `origin/bashified` and is not installed; `command -v grave` is empty. The mechanization is real, the verb surface is not. |

### What `grave` WILL NOT do

| obligation | HOW | backed by |
|---|---|---|
| Rip a disc automatically on insert | refused | `install.sh` removes the udev rule; `etc/udev/99-cd-autorip.rules.disabled` is kept disabled by name. A rip is started deliberately or not at all — `bin/wtul-rip`'s own docstring calls itself the replacement for the auto-trigger. |
| Require an account or OAuth to identify a disc | refused | `.scheduler/FOCUS.md`: Spinitron public-scrape + Discogs, "both credential-free". `lib/catalog_writeback.py`: "no OAuth/service account, just POST JSON". A station tool that needs someone's login is unusable on show night. |
| Eject a disc after a failed or partial rip | refused | `abcde.conf` `EJECTCD=y` fires only on a clean finish; `noeject.abcde.conf` exists for the other case. A failed rip leaves the disc in the drive to retry, which is what a human at 2am needs. |
| Count a rehearsal as a hardware verification | refused | `lib/fake_drive.py` exists precisely so hardware-gated work can be exercised — and `tests/test_rehearsal_guard_audit.py` enforces that a rehearsal cannot take a real action. Both stability-milestone boxes stay unchecked until a real disc goes in. |
| Decide the parked directions on Zach's behalf | refused | `.scheduler/FOCUS.md` parks #9 (capture-on-play front end) and #10 (show-run sheet) as *undecided design calls addressed to Zach*, not as work waiting for hands. Guessing one is inventing a decision. |

*(Refusals four and five are the same principle applied twice: this project
has a documented history of prose drifting ahead of the machine, and both
rules exist to stop a plausible claim from standing in for a verified one.)*

## Universal clauses

Every obligation above, without exception:

- exits **0 only if the promise was kept**. Never an exit-0 no-op.
- exits **4 (GAP)** when the thing is in scope but not built, and names its
  own escalation. `--summon` is available here.
- exits **5 (BROKEN)** when it ran and broke.
- exits **6 (BLIND)** when it cannot read its domain. "I cannot see the
  drive" is never reported as "no disc to rip".
- exits **7 (REFUSED)** on anything in the WILL NOT table. `--summon` is
  **forbidden** on 7: there is no escalation, and that is what the refusal
  means.
- **cannot spend money** unless it declares `--summon`, which has no short
  form and is never implied.

**Today the exit clauses above are the document's largest gap, not its
summary.** `bin/wtul-rip` implements none of 4/5/6/7 (see the readiness
table's last-but-one row). The document is right and the code is behind.

## The finding

**30 obligations — 18 bash, 7 summon, 5 refused (counted from the table,
not estimated) — and no verb, no exit vocabulary.** `wtul` is the most
mechanized project in this pass that has no front door: 401 test functions,
a 13-check preflight, a durable outbox and a rehearsal rig, all reachable
only as `wtul-rip`, and all speaking exit 0/1. The two cheapest unblocking
summons are (1) put `grave` on `PATH` over the existing subcommands and (2)
give it the 4/5/6/7 dispatcher — after which every `bash` row above becomes
callable by the rest of the ecosystem instead of only by Zach at the drive.

The three remaining `summon` rows that no amount of code will close —
speed verification, metadata-fix verification, the M02 label session — are
all **hardware-gated**, and have been across at least six unattended batch
runs. That is not a backlog; it is a standing statement that this verb's
last mile requires a person, a disc and a drive.
```
