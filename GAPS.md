# GAPS -- what `grave` cannot yet do

Recorded 2026-07-30 during the bashify pass. These are to be closed
later; they are written down now so the utility never pretends.

## Tooling in other languages, not reachable through the verb (2 files)

This tree does real work in javascript/typescript. The verb wraps shell
only, so none of it is exposed yet. This is the largest single gap here:

- `gas/catalog-writeback.gs.js`
- `gas/photo-capture.gs.js`

## Python that was never given a shell contract (28 files)

These do real work but are not reachable through the verb, because they
have no stated argv/output promise to wrap:

- `lib/catalog_outbox.py`
- `lib/catalog_writeback.py`
- `lib/fake_drive.py`
- `lib/label_render.py`
- `lib/metadata_lookup.py`
- `lib/mix_label.py`
- `lib/ocr_metadata.py`
- `lib/photo_capture.py`
- `lib/preflight.py`
- `lib/spinitron.py`
- `scripts/spin-match-eval.py`
- `tests/test_album_dir_munge.py`
- `tests/test_catalog_outbox.py`
- `tests/test_catalog_writeback.py`
- `tests/test_fake_drive.py`
- `tests/test_label_render.py`
- `tests/test_metadata_lookup.py`
- `tests/test_mix_label.py`
- `tests/test_ocr_metadata.py`
- `tests/test_photo_capture.py`
- `tests/test_preflight.py`
- `tests/test_rehearsal_guard_audit.py`
- `tests/test_rip_rehearsal.py`
- `tests/test_speed.py`
- `tests/test_spin_match_corpus.py`
- `tests/test_spinitron.py`
- `tests/test_watch_loop_stdin.py`
- `tests/test_wiring.py`

## Standing gap: the cost baseline

No before-measurement exists for what the previous implementation cost
per call, so the saving from mechanising it is **unmeasured, not zero
and not assumed**. Closing this needs a real measurement, not an estimate.
