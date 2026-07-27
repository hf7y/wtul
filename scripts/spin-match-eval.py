#!/usr/bin/env python3
"""Sweep the Spinitron match threshold over the labelled corpus (FOCUS #1).

    scripts/spin-match-eval.py                # sweep + per-case scores
    scripts/spin-match-eval.py --live         # also score the corpus's
                                              # artists against real spins

Read-only: `--live` does one GET of WTUL's public Spinitron page (the same
page `rip_session()` already scrapes) and writes nothing anywhere. No drive,
no disc, no key.

Why this exists: DEFAULT_THRESHOLD sat in the source for a week described as
"an unverified first guess". A number nobody can re-derive is a number nobody
dares move. This prints the evidence - every case's score, the decision
margin, and what each candidate threshold would get right and wrong - so the
next person to touch it is making a measured change instead of another guess.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
import spinitron as sp  # noqa: E402

CORPUS_PATH = os.path.join(HERE, "..", "etc", "spin-match-corpus.json")


def score(case):
    """Same combination spin_matches_track uses: both fields must clear the
    threshold, so the case's score is the weaker of the two."""
    spin_artist, spin_song, track_artist, track_title, _why = case
    return min(sp._similarity(spin_artist, track_artist),
               sp._similarity(spin_song, track_title))


def load_corpus(path=CORPUS_PATH):
    with open(path) as fh:
        return json.load(fh)


def report(corpus, out=sys.stdout):
    scored = {kind: sorted(((score(c), c) for c in corpus[kind]),
                           key=lambda sc: sc[0])
              for kind in ("positives", "negatives")}

    for kind, want in (("positives", "MUST match"), ("negatives", "must NOT")):
        print(f"\n== {kind} ({want}) ==", file=out)
        for s, c in scored[kind]:
            ok = (s >= sp.DEFAULT_THRESHOLD) == (kind == "positives")
            print(f"  {'ok ' if ok else 'BAD'} {s:.3f}  "
                  f"{c[0]} / {c[1]}  <->  {c[2]} / {c[3]}   ({c[4]})", file=out)

    worst_pos = scored["positives"][0][0]
    best_neg = scored["negatives"][-1][0]
    print(f"\nworst positive {worst_pos:.3f} | best negative {best_neg:.3f} | "
          f"threshold {sp.DEFAULT_THRESHOLD}", file=out)
    if best_neg < worst_pos:
        print(f"separable: any threshold in ({best_neg:.3f}, {worst_pos:.3f}] "
              f"labels this corpus perfectly", file=out)
    else:
        print("NOT separable: no threshold labels this corpus perfectly - "
              "some case is mislabelled, or the matcher needs the fix, not "
              "the number", file=out)

    print("\n== sweep ==", file=out)
    print("  thresh  pos-hit  neg-hit(false)", file=out)
    for i in range(60, 100, 2):
        t = i / 100.0
        hits = sum(1 for s, _ in scored["positives"] if s >= t)
        false = sum(1 for s, _ in scored["negatives"] if s >= t)
        mark = "  <- default" if abs(t - sp.DEFAULT_THRESHOLD) < 1e-9 else ""
        print(f"  {t:.2f}    {hits:2d}/{len(scored['positives']):2d}"
              f"    {false:2d}/{len(scored['negatives']):2d}{mark}", file=out)
    return worst_pos, best_neg


def live(corpus, out=sys.stdout):
    """Score every corpus artist against the spins actually on the public page
    right now. This is not a hit-rate measurement - the page only carries the
    show currently on air, and none of it is labelled - it just proves the
    scrape and the matcher agree on real, unrehearsed strings."""
    spins = sp.fetch_recent_spins_public()
    print(f"\n== live: {len(spins)} spin(s) on the public page ==", file=out)
    for s in spins:
        print(f"  spin: {s['artist']!r} / {s['song']!r}", file=out)
    if not spins:
        print("  (no show on air - nothing to score against)", file=out)
        return
    best = []
    for c in corpus["positives"] + corpus["negatives"]:
        for s in spins:
            best.append((min(sp._similarity(s["artist"], c[2]),
                             sp._similarity(s["song"], c[3])), c[2], c[3]))
    best.sort(reverse=True)
    print("  closest corpus tracks to what is airing:", file=out)
    for sc, a, t in best[:3]:
        flag = "MATCH" if sc >= sp.DEFAULT_THRESHOLD else "no"
        print(f"    {sc:.3f} {flag:5s} {a} / {t}", file=out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true",
                    help="also GET the public Spinitron page (read-only)")
    args = ap.parse_args(argv)
    corpus = load_corpus()
    worst_pos, best_neg = report(corpus)
    if args.live:
        live(corpus)
    return 0 if best_neg < worst_pos else 1


if __name__ == "__main__":
    sys.exit(main())
