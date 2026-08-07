"""Fill missing thesaurus entries using WordNet, restricted to the
vocabulary union set (so distractor/synonym pools never leave the deck).

Deterministic and offline. Words WordNet cannot cover stay empty and are
listed for optional LLM enrichment later.
Writes data/vocabulary.json in place and thesaurus_report.json.
"""

import json
from pathlib import Path

from nltk.corpus import wordnet as wn

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "output"
VOCAB = BASE / "data" / "vocabulary.json"

WN_POS = {"n": "n", "v": "v", "adj": "a", "adv": "r"}


def main():
    vocab = json.load(open(VOCAB))
    union = {it["word"] for it in vocab}

    filled_words, still_empty = [], []
    for it in vocab:
        if it["phrase_attribute"]:
            continue
        if any(s["thesaurus"] for s in it["senses"]):
            continue
        word = it["word"]
        got_any = False
        for s in it["senses"]:
            wn_pos = WN_POS.get(s["part_of_speech"])
            syns = []
            for synset in wn.synsets(word, pos=wn_pos):
                for lemma in synset.lemmas():
                    cand = lemma.name().replace("_", " ").lower()
                    if cand != word and cand in union and cand not in syns:
                        syns.append(cand)
            if syns:
                s["thesaurus"] = syns[:6]
                s["_thesaurus_origin"] = "wordnet"
                got_any = True
        if got_any:
            filled_words.append(word)
        else:
            still_empty.append(word)

    json.dump(vocab, open(VOCAB, "w"),
              ensure_ascii=False, indent=1)
    json.dump({"filled": filled_words, "still_empty": still_empty},
              open(OUT / "thesaurus_report.json", "w"),
              ensure_ascii=False, indent=1)
    print(f"wordnet filled: {len(filled_words)}, still empty: {len(still_empty)}")


if __name__ == "__main__":
    main()
