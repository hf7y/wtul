# CONTRACT -- `grave`

engrave the disc: rip, tag and log a radio record

Derived 2026-07-30 from the tooling that actually existed in `wtul`.
Where there was no stated contract before, this is the first one; that
is a finding about the old tree, recorded rather than hidden.

## The promise

```
grave <subcommand> [args...]
```

| subcommand | promises | backed by |
|---|---|---|
| `cd-autorip` | whatever `bin/cd-autorip.sh` promised | `bin/cd-autorip.sh` |
| `wtul-rip` | whatever `bin/wtul-rip` promised | `bin/wtul-rip` |
| `install` | whatever `install.sh` promised | `install.sh` |
| `install-tesseract-local` | whatever `scripts/install-tesseract-local.sh` promised | `scripts/install-tesseract-local.sh` |

## Universal clauses

Every subcommand, without exception:

- exits **0 only if the promise was kept**. Never an exit-0 no-op.
- exits **4 (GAP)** if the tooling does not exist, and says what is missing.
- exits **6 (BLIND)** if it cannot read its domain. "I cannot see" is
  never reported as "nothing to report".
- **cannot spend money** unless it declares `--summon`, which has no
  short form and is never implied.

## Verification

```
./test/contract-test.sh <command>
```

The same assertions run against the legacy tooling and against `grave`.
That is what makes "keeps the same contract" a measurement, not a claim.
