"""Discount difficulty for morphologically transparent derivations.

Raw corpus frequency treats `nonrelevant` as very rare, but a learner who
knows `relevant` and the prefix `non-` does not have to learn it separately.
For every headword we try to strip one known affix, look up the base's
difficulty (COCA rank, else calibrated wordfreq zipf), and take

    difficulty = max(min(own, base + affix_penalty), own - MAX_DISCOUNT)

The penalty reflects how transparent the affix is. Words whose own frequency
is missing (`difficulty = null`) get the derived estimate outright.

A purely orthographic strip produces false parents (`wither` = `with` + `er`,
`butter` = `but` + `ter`, `cohere` = `co` + `here`), so every analysis is
verified against WordNet: if the word is a WordNet lemma it must be an
inflection of the base, or be derivationally related / a pertainym of it.
Words WordNet does not know at all (`nonrelevant`, `platelike`) are accepted,
since being absent from the dictionary is itself evidence of a transparent
ad-hoc derivation.

The analysis recurses two levels so that stacked affixes collapse to the true
root: `unbiased` -> `biased` -> `bias`.

Writes data/vocabulary.json in place and data/output/morph_report.json.
"""

import json
import math
from pathlib import Path

from nltk.corpus import wordnet as wn
from wordfreq import zipf_frequency

from merge import coca_ranks, fit_zipf_to_rank

BASE = Path(__file__).resolve().parent.parent
VOCAB = BASE / "data" / "vocabulary.json"
OUT = BASE / "data" / "output"

# affix -> penalty in difficulty units (1 unit = corpus rank doubling)
PREFIXES = {
    "non": 0.4, "un": 0.4, "re": 0.8, "over": 0.5, "under": 0.5, "semi": 0.6,
    "multi": 0.5, "anti": 0.6, "pre": 0.6, "post": 0.6, "sub": 0.8,
    "super": 0.6, "mis": 0.6, "inter": 0.8, "co": 1.0, "dis": 0.8,
    "in": 1.0, "im": 1.0, "ir": 1.0, "il": 1.0, "out": 0.8, "up": 0.8,
    "counter": 0.6, "extra": 0.6, "ultra": 0.6, "micro": 0.6, "macro": 0.6,
}
SUFFIXES = {
    "ly": 0.3, "ness": 0.4, "less": 0.5, "ful": 0.5, "like": 0.4,
    "wise": 0.5, "fold": 0.5, "ship": 0.6, "hood": 0.6, "er": 0.5,
    "or": 0.6, "ed": 0.3, "ing": 0.3, "s": 0.2, "es": 0.3, "able": 0.6,
    "ible": 0.8, "ist": 0.6, "ism": 0.7, "ize": 0.6, "ise": 0.6,
    "ment": 0.6, "ity": 0.9, "ous": 0.9, "ive": 0.8, "al": 0.7,
    "ic": 0.8, "ical": 0.8, "ation": 0.9, "tion": 1.0, "sion": 1.0,
    "ary": 0.9, "ency": 1.0, "ancy": 1.0, "ance": 0.9, "ence": 0.9,
}
# Affixes transparent enough that a WordNet entry of their own does not mean
# the derivation must be learned separately (`semiliterate`, `platelike`).
# `fold` is excluded: `manifold` is not a transparent derivation of `many`.
# `in-` / `re-` / `co-` are excluded: `instill` is not `in` + `still`.
TRANSPARENT = {"non", "un", "semi", "multi", "over", "under", "pre", "post",
               "anti", "micro", "macro", "ultra", "extra", "counter",
               "like", "wise"}
MIN_BASE_LEN = 4
MAX_DISCOUNT = 2.5      # a derivation is never credited more than this much


def base_variants(stem):
    """Orthographic restorations after stripping a suffix."""
    out = [stem, stem + "e"]
    if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "aeiou":
        out.append(stem[:-1])                      # running -> run
    if stem.endswith("i"):
        out.append(stem[:-1] + "y")                # happi -> happy
    return out


def candidates(word):
    """Yield (base, penalty, affix) for one affix strip."""
    for pre, pen in PREFIXES.items():
        if word.startswith(pre) and len(word) - len(pre) >= MIN_BASE_LEN:
            yield word[len(pre):], pen, pre
    for suf, pen in sorted(SUFFIXES.items(), key=lambda kv: -len(kv[0])):
        if word.endswith(suf) and len(word) - len(suf) >= MIN_BASE_LEN:
            for cand in base_variants(word[: -len(suf)]):
                yield cand, pen, suf


def related(word, base, affix):
    """Is `base` a plausible morphological parent of `word` per WordNet?"""
    synsets = wn.synsets(word)
    if not synsets:
        return True                                # unknown word: trust the affix
    if affix in TRANSPARENT and wn.synsets(base):
        return True
    for pos in ("n", "v", "a", "r"):
        if wn.morphy(word, pos) == base:
            return True                            # plain inflection
    for syn in synsets:
        for lemma in syn.lemmas():
            if lemma.name().lower() != word:
                continue
            for rel in lemma.derivationally_related_forms() + lemma.pertainyms():
                if rel.name().lower() == base:
                    return True
    return False


def main():
    vocab = json.load(open(VOCAB))
    ranks = coca_ranks()
    estimate, _ = fit_zipf_to_rank(ranks)

    def difficulty_of(word):
        if word in ranks:
            return round(math.log2(ranks[word]), 2)
        z = zipf_frequency(word, "en")
        if z > 0:
            return round(math.log2(max(1, round(10 ** estimate(z)))), 2)
        return None

    def analyse(word, depth):
        """Cheapest (difficulty, base, penalty) reachable by stripping affixes."""
        best = None
        for cand, pen, affix in candidates(word):
            own = difficulty_of(cand)
            if own is None or not related(word, cand, affix):
                continue
            base = own
            if depth > 1:
                deeper = analyse(cand, depth - 1)
                if deeper is not None:
                    base = min(base, deeper[0])
            derived = round(base + pen, 2)
            if best is None or derived < best[0]:
                best = (derived, cand, pen)
        return best

    report = {"discounted": [], "filled": [], "unresolved": []}
    for item in vocab:
        word = item["word"]
        if " " in word or "-" in word:            # phrases keep their own value
            continue
        best = analyse(word.lower(), 2)
        own = item.get("difficulty")
        if best is None:
            if own is None:
                report["unresolved"].append(word)
            continue
        derived, cand, pen = best
        if own is None:
            item["difficulty"] = derived
            item["_difficulty_source"] = f"morph:{cand}+{pen}"
            report["filled"].append({"word": word, "base": cand,
                                     "penalty": pen, "difficulty": derived})
        elif derived < own - 0.3:                 # ignore noise-level changes
            derived = max(derived, round(own - MAX_DISCOUNT, 2))
            item["difficulty"] = derived
            item["_difficulty_source"] = f"morph:{cand}+{pen}"
            report["discounted"].append({"word": word, "base": cand,
                                         "from": own, "to": derived})

    json.dump(vocab, open(VOCAB, "w"), ensure_ascii=False, indent=1)
    json.dump(report, open(OUT / "morph_report.json", "w"),
              ensure_ascii=False, indent=1)
    print(f"discounted: {len(report['discounted'])}, "
          f"filled (was null): {len(report['filled'])}, "
          f"still null: {len(report['unresolved'])}")


if __name__ == "__main__":
    main()
