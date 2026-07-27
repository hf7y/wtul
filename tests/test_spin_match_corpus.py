"""The labelled corpus behind DEFAULT_THRESHOLD (FOCUS #1).

FOCUS.md carried "the 0.82 match threshold is still a first guess" for a week.
This turns it into a pinned decision: every case in
`etc/spin-match-corpus.json` is a real-world credit-style variant that must
match, or a look-alike that must not. Loosening the matcher (or moving the
threshold) without re-deciding those cases fails here.

The corpus is hand-built from how DJs actually type credits vs how CDDB spells
them, plus the real discs sitting in this machine's library - it is NOT a log
of observed spins, so it can't tell us the real-world hit rate. It can only
tell us the matcher hasn't regressed on the drift we know exists.
"""
import difflib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import spinitron as sp  # noqa: E402

CORPUS_PATH = os.path.join(os.path.dirname(__file__), "..", "etc",
                           "spin-match-corpus.json")


def _load():
    with open(CORPUS_PATH) as fh:
        return json.load(fh)


def _cases(kind):
    return [pytest.param(c, id=f"{c[0]} / {c[1]}") for c in _load()[kind]]


def _strict_ratio(a, b):
    """What _similarity scored before the credit-style key was added."""
    return difflib.SequenceMatcher(None, sp._normalize(a), sp._normalize(b)).ratio()


def _score(case):
    spin_artist, spin_song, track_artist, track_title, _why = case
    spin = {"artist": spin_artist, "song": spin_song}
    return (spin, track_artist, track_title,
            min(sp._similarity(spin_artist, track_artist),
                sp._similarity(spin_song, track_title)))


@pytest.mark.parametrize("case", _cases("positives"))
def test_positive_cases_match_at_the_default_threshold(case):
    spin, artist, title, score = _score(case)
    assert sp.spin_matches_track(spin, artist, title), (
        f"{case[4]}: should match but scores {score:.3f} < "
        f"{sp.DEFAULT_THRESHOLD}")


@pytest.mark.parametrize("case", _cases("negatives"))
def test_negative_cases_stay_below_the_default_threshold(case):
    spin, artist, title, score = _score(case)
    assert not sp.spin_matches_track(spin, artist, title), (
        f"{case[4]}: should NOT match but scores {score:.3f} >= "
        f"{sp.DEFAULT_THRESHOLD}")


@pytest.mark.parametrize("case", _cases("accepted_false_positives"))
def test_accepted_false_positives_still_match(case):
    """These are wrong matches we knowingly tolerate (see the corpus comment:
    a bad match costs a queue reorder, a missed one costs the feature). Pinned
    so the tradeoff is visible rather than assumed."""
    spin, artist, title, score = _score(case)
    assert sp.spin_matches_track(spin, artist, title), (
        f"{case[4]}: this no longer matches ({score:.3f}) - the matcher got "
        f"BETTER. Move this case into 'negatives' and delete this note.")


def test_corpus_is_not_trivially_satisfiable():
    """A corpus of only-exact-matches and only-wildly-different pairs would
    pass at any threshold and prove nothing. Require that the loosening added
    for credit-style drift is load-bearing - i.e. several positives would have
    FAILED under the plain normalized ratio alone - and that some negative
    still scores respectably high, so the threshold itself is doing work."""
    corpus = _load()
    would_have_missed = []
    for c in corpus["positives"]:
        strict = min(_strict_ratio(c[0], c[2]), _strict_ratio(c[1], c[3]))
        if strict < sp.DEFAULT_THRESHOLD:
            would_have_missed.append(c)
    assert len(would_have_missed) >= 5, (
        "the credit-style loosening rescues too few cases to justify itself")
    near_miss_negatives = [c for c in corpus["negatives"] if _score(c)[3] >= 0.6]
    assert len(near_miss_negatives) >= 5


def test_threshold_has_margin_on_both_sides():
    """The chosen threshold should not sit flush against a case. If the worst
    positive scores 0.821 the next real-world variant will fall through, and
    that is exactly how this stayed an unverified guess - so require daylight."""
    corpus = _load()
    worst_positive = min(_score(c)[3] for c in corpus["positives"])
    best_negative = max(_score(c)[3] for c in corpus["negatives"])
    assert best_negative < sp.DEFAULT_THRESHOLD <= worst_positive
    assert worst_positive - sp.DEFAULT_THRESHOLD >= 0.02, (
        f"worst positive {worst_positive:.3f} is flush against the threshold")
    # Only 0.02 of daylight on this side, and that is the honest finding:
    # "Come Together" vs "Get Together" by the same act scores 0.800. Titles
    # that differ by one short word are where this heuristic runs out of
    # room - lowering the threshold much below 0.82 starts buying them.
    assert sp.DEFAULT_THRESHOLD - best_negative >= 0.02 - 1e-9, (
        f"best negative {best_negative:.3f} is flush against the threshold")


def test_compare_key_drops_only_credit_style_noise():
    assert sp._compare_key("The Beatles") == "beatles"
    assert sp._compare_key("Rolling Stones, The") == "rolling stones"
    assert sp._compare_key("Tank & The Bangas") == "tank bangas"
    # Both spellings of the conjunction, not just the ampersand - a mutation
    # dropping "and" from _NOISE_TOKENS survived the corpus alone.
    assert sp._compare_key("Tank and the Bangas") == "tank bangas"
    assert sp._compare_key("Sly and the Family Stone") == "sly family stone"
    assert sp._compare_key("Kendrick Lamar feat. Zacari") == "kendrick lamar"
    assert sp._compare_key("Big Freedia ft Boyfriend") == "big freedia"
    # "with" and "&" are credits, not noise - a duo is not its first member.
    assert sp._compare_key("Big Freedia & Boyfriend") == "big freedia boyfriend"
    # Nothing but noise -> empty, which _similarity refuses to compare on.
    assert sp._compare_key("The") == ""


def test_noise_token_set_is_a_decision_not_a_drawer():
    """Every token added here silently widens what counts as the same record,
    and a wider match is invisible - it shows up as a queue that reordered for
    no reason, months later. A mutation adding "a"/"of" passed the whole
    corpus. So the set itself is pinned: adding one means coming here and
    adding the negative case that justifies it."""
    assert sp._NOISE_TOKENS == frozenset(("the", "and"))


def test_all_noise_names_do_not_collapse_into_a_match():
    """Two different acts whose names are entirely article/conjunction tokens
    would both key to "", and SequenceMatcher calls "" vs "" a perfect match.
    _similarity must fall back to the strict ratio instead."""
    assert sp._similarity("The", "And") < 0.5
    assert sp._similarity("The The", "The") < sp.DEFAULT_THRESHOLD


def test_similarity_never_scores_below_the_strict_ratio():
    """The looser key is a max(), not a replacement: nothing that matched
    before this change may stop matching because of it."""
    import difflib
    for a, b in [("Radiohead", "Radiohead"), ("The Beatles", "The Beatles"),
                 ("Love", "Love Song"), ("Helen Gillet", "Helen Gillett")]:
        strict = difflib.SequenceMatcher(
            None, sp._normalize(a), sp._normalize(b)).ratio()
        assert sp._similarity(a, b) >= strict


def test_eval_script_runs_and_reports_the_corpus_separable():
    """`scripts/spin-match-eval.py` is the human-facing half of this - it has
    to actually run, and it has to fail loud (non-zero) if the corpus ever
    stops being separable by a single threshold. Offline path only: no --live,
    so no network. Run here rather than trusted, because a report generator
    nobody runs is how the threshold became folklore in the first place."""
    import importlib.util
    import io
    path = os.path.join(os.path.dirname(__file__), "..", "scripts",
                        "spin-match-eval.py")
    spec = importlib.util.spec_from_file_location("spin_match_eval", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    buf = io.StringIO()
    worst_pos, best_neg = mod.report(mod.load_corpus(), out=buf)
    text = buf.getvalue()
    assert best_neg < worst_pos
    assert "BAD" not in text, f"eval reports a mislabelled case:\n{text}"
    assert "separable:" in text
    assert mod.main([]) == 0
