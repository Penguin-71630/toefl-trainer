"""Fix OCR residue in the merged vocabulary: truncated headwords, misspellings,
and glosses with trailing part-of-speech letters.

Renamed entries get their difficulty recomputed with the same COCA/zipf
calibration merge.py uses; if the corrected headword already exists the two
entries are merged (senses de-duplicated by (pos, gloss)).

Writes data/vocabulary.json in place and data/output/cleanup_report.json.
"""

import json
import math
import re
from pathlib import Path

from merge import coca_ranks, fit_zipf_to_rank
from wordfreq import zipf_frequency

BASE = Path(__file__).resolve().parent.parent
VOCAB = BASE / "data" / "vocabulary.json"
OUT = BASE / "data" / "output"

# Truncated headwords (the source PDF clipped the last characters).
RENAME = {
    "at one sessio": "at one session",
    "be acquaint with": "be acquainted with",
    "down the drai": "down the drain",
    "equestria": "equestrian",
    "express trai": "express train",
    "in commo": "in common",
    "labor unio": "labor union",
    "log cabi": "log cabin",
    "now and the": "now and then",
    "pack dow": "pack down",
    "presidential electio": "presidential election",
    "pry ope": "pry open",
    "social distinctio": "social distinction",
    "torrential rai": "torrential rain",
    # Misspellings / non-words.
    "distent": "distended",
    "hestiant": "hesitant",
    "improvision": "improvisation",
    "incorpoarate": "incorporate",
    "inpractical": "impractical",
    "malfunctional": "multifunctional",
    "melodie": "melody",
    "morphololgy": "morphology",
    "mounmental": "monumental",
    "ploished": "polished",
    "propery": "property",
    "romote": "remote",
    "victuosity": "virtuosity",
    "ma’am": "ma'am",
}

# Parse artefacts with no recoverable headword.
DELETE = {"acqua"}

# Trailing part-of-speech letters glued onto the Chinese gloss.
GLOSS_TAIL = re.compile(r"(?<=[\u4e00-\u9fff。，、）\.\s])(vi|vt|adj|adv|prep|[vin])$")


def clean_gloss(gloss):
    if not gloss:
        return gloss, False
    fixed = GLOSS_TAIL.sub("", gloss).strip()
    return fixed, fixed != gloss


def merge_senses(dst, src):
    seen = {(s.get("part_of_speech"), s.get("gloss")) for s in dst["senses"]}
    for s in src["senses"]:
        if (s.get("part_of_speech"), s.get("gloss")) not in seen:
            dst["senses"].append(s)
            seen.add((s.get("part_of_speech"), s.get("gloss")))
    for key in ("sources", "exam_tags"):
        dst[key] = sorted(set(dst[key]) | set(src[key]))


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

    by_word = {x["word"]: x for x in vocab}
    report = {"renamed": [], "merged": [], "deleted": [], "glosses": []}

    for old, new in RENAME.items():
        item = by_word.get(old)
        if item is None:
            continue
        before = item["difficulty"]
        item["word"] = new
        item["difficulty"] = difficulty_of(new)
        target = by_word.get(new)
        if target is not None and target is not item:
            merge_senses(target, item)
            item["_drop"] = True
            report["merged"].append({"from": old, "into": new})
        else:
            by_word[new] = item
            report["renamed"].append({
                "from": old, "to": new,
                "difficulty": [before, item["difficulty"]],
            })
        by_word.pop(old, None)

    for x in vocab:
        for i, sense in enumerate(x["senses"]):
            fixed, changed = clean_gloss(sense.get("gloss"))
            if changed:
                report["glosses"].append({
                    "word": x["word"], "sense": i,
                    "from": sense["gloss"], "to": fixed,
                })
                sense["gloss"] = fixed

    kept = []
    for x in vocab:
        if x.pop("_drop", False):
            continue
        if x["word"] in DELETE:
            report["deleted"].append(x["word"])
            continue
        kept.append(x)

    json.dump(kept, open(VOCAB, "w"), ensure_ascii=False, indent=1)
    json.dump(report, open(OUT / "cleanup_report.json", "w"),
              ensure_ascii=False, indent=1)

    print(f"renamed: {len(report['renamed'])}, merged: {len(report['merged'])}, "
          f"deleted: {len(report['deleted'])}, "
          f"glosses fixed: {len(report['glosses'])}, items: {len(kept)}")


if __name__ == "__main__":
    main()
