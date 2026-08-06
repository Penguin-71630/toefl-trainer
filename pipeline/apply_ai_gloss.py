"""Apply AI-generated Traditional Chinese glosses (batch files) to
vocabulary.json. Junk pseudo-words (parse artifacts) are removed.

Writes vocabulary.json in place and gloss_fill_report.json.
"""

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
INTER = BASE / "data" / "intermediate"
OUT = BASE / "data" / "output"

JUNK = {"n"}  # single-letter parse artifacts


def main():
    glosses = {}
    for f in sorted(INTER.glob("ai_gloss_batch*.json")):
        glosses.update(json.load(open(f)))

    vocab = json.load(open(OUT / "vocabulary.json"))
    filled, missing = [], []
    kept = []
    for it in vocab:
        if it["word"] in JUNK:
            continue
        for s in it["senses"]:
            if s["gloss"] is None:
                g = glosses.get(it["word"])
                if g:
                    s["gloss"] = g
                    s["_gloss_origin"] = "llm_generated"
                    filled.append(it["word"])
                else:
                    missing.append(it["word"])
        kept.append(it)

    # re-number ids after junk removal
    for i, it in enumerate(kept, start=1):
        it["id"] = i

    json.dump(kept, open(OUT / "vocabulary.json", "w"),
              ensure_ascii=False, indent=1)
    json.dump({"filled": sorted(set(filled)), "missing": sorted(set(missing))},
              open(OUT / "gloss_fill_report.json", "w"),
              ensure_ascii=False, indent=1)
    print(f"glosses filled: {len(set(filled))}, "
          f"still missing: {len(set(missing))}, items: {len(kept)}")


if __name__ == "__main__":
    main()
