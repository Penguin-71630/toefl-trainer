"""Merge the three parsed sources into the final vocabulary items.

Steps:
1. Union of wym / toefl_txt / l6 headwords (+ wym phrase rows and
   per-sense phrase-column phrases as `phr` items).
2. Convert simplified Chinese glosses to Traditional (OpenCC s2twp).
3. difficulty = log2(rank); rank from COCA_20000, else calibrated from
   wordfreq Zipf via a linear fit log10(rank) = a - b*zipf.
4. word_family assignment (shared stem heuristics).
5. phrase_attribute {head, particles} for phr items.
6. Emit data/output/vocabulary.json, merge-conflict log, AI-todo lists.
"""

import json
import math
import re
from collections import defaultdict
from pathlib import Path

from opencc import OpenCC
from wordfreq import zipf_frequency

BASE = Path(__file__).resolve().parent.parent
INTER = BASE / "data" / "intermediate"
OUT = BASE / "data" / "output"

cc = OpenCC("s2twp")

PARTICLES = {
    "up", "down", "in", "out", "on", "off", "over", "under", "away", "back",
    "through", "along", "around", "about", "across", "by", "for", "with",
    "to", "at", "of", "into", "onto", "from", "after", "against", "forward",
    "apart", "aside", "ahead", "behind", "between", "without", "upon",
}
STOPWORDS = {"a", "an", "the", "one's", "oneself", "sth", "sb", "and", "or",
             "be", "it", "that", "this", "so", "as", "no", "not", "all",
             "…", "...", "etc"}


def tw(s):
    if not s:
        return s
    s = cc.convert(s)
    return re.sub(r"^(?:詞組|片語|词组)\s*", "", s).strip() or None


def load():
    wym = json.load(open(INTER / "wym.json"))["entries"]
    toefl = json.load(open(INTER / "toefl_txt.json"))["entries"]
    l6 = json.load(open(INTER / "l6.json"))["entries"]
    return wym, toefl, l6


def clean_word(w):
    w = w.strip().lower()
    w = re.sub(r"\s+", " ", w)
    return w


def build_phrase_attribute(phrase):
    tokens = phrase.split()
    head = None
    particles = []
    for t in tokens:
        t2 = t.strip("…().")
        if not t2 or t2 in STOPWORDS:
            continue
        if t2 in PARTICLES:
            particles.append(t2)
        elif head is None:
            head = t2
    return {"head": head or tokens[0], "particles": particles}


def coca_ranks():
    ranks = {}
    for i, line in enumerate(
            open(BASE / "data" / "raw" / "COCA_20000.txt",
                 encoding="utf-8", errors="ignore")):
        w = line.strip().lower()
        if w and w not in ranks:
            ranks[w] = i + 1
    return ranks


def fit_zipf_to_rank(ranks):
    """Nonparametric calibration: median log10(rank) per zipf bin (width 0.25),
    then a monotone lookup with linear interpolation between bin centers."""
    bins = defaultdict(list)
    for w, r in ranks.items():
        z = zipf_frequency(w, "en")
        if z > 0:
            bins[round(z * 4) / 4].append(math.log10(r))
    pts = sorted((z, sorted(v)[len(v) // 2]) for z, v in bins.items()
                 if len(v) >= 5)
    # enforce monotone decreasing log-rank as zipf increases
    mono = []
    for z, lr in pts:
        while mono and mono[-1][1] <= lr:
            mono.pop()
        mono.append((z, lr))

    def estimate(z):
        if z <= mono[0][0]:
            # extrapolate below lowest bin with slope -1 (Zipf's law)
            return mono[0][1] + (mono[0][0] - z)
        if z >= mono[-1][0]:
            return mono[-1][1]
        for (z1, l1), (z2, l2) in zip(mono, mono[1:]):
            if z1 <= z <= z2:
                t = (z - z1) / (z2 - z1)
                return l1 + t * (l2 - l1)
        return mono[-1][1]

    return estimate, mono


STEM_SUFFIXES = [
    "ization", "isation", "ability", "ibility", "ically", "ation", "ition",
    "ment", "ness", "ance", "ence", "tion", "sion", "ally", "able", "ible",
    "ical", "ious", "eous", "ship", "hood", "less", "ful", "ist", "ism",
    "ity", "ive", "ize", "ise", "ous", "ant", "ent", "ary", "ory", "ial",
    "ure", "age", "ly", "er", "or", "al", "ic", "y", "e",
]
PREFIXES = ["un", "in", "im", "ir", "il", "dis", "non", "re", "over",
            "under", "mis", "anti", "counter", "de", "ab"]


def stem(word):
    w = word
    for p in PREFIXES:
        if w.startswith(p) and len(w) - len(p) >= 4:
            w = w[len(p):]
            break
    for s in STEM_SUFFIXES:
        if w.endswith(s) and len(w) - len(s) >= 4:
            w = w[: -len(s)]
            break
    return w[:6] if len(w) > 6 else w


def main():
    wym, toefl, l6 = load()
    items = {}          # word -> item dict (senses merged)
    conflicts = []

    def get(word, is_phrase=False):
        word = clean_word(word)
        if word not in items:
            items[word] = {
                "word": word, "sources": [], "senses": [],
                "is_phrase": is_phrase or " " in word,
            }
        return items[word]

    # --- wym (primary: has thesaurus) ---
    for e in wym:
        w = clean_word(e["word"])
        if not re.match(r"^[a-z][a-z'’\- ]*$", w):
            conflicts.append(f"wym skip malformed headword: {w!r}")
            continue
        it = get(w, e["is_phrase"])
        if "wym" not in it["sources"]:
            it["sources"].append("wym")
        for s in e["senses"]:
            it["senses"].append({
                "part_of_speech": "phr" if e["is_phrase"] else (s["pos"] or "n"),
                "gloss": tw(s["gloss"]),
                "thesaurus": s["thesaurus"],
                "_gloss_origin": "wym",
            })
            # phrase-column phrases become their own phr items
            for ph in s.get("phrases", []):
                ph_clean = clean_word(re.sub(r"[\u4e00-\u9fff，。；;].*$", "", ph))
                if ph_clean and " " in ph_clean \
                        and re.match(r"^[a-z][a-z'’\- ]*$", ph_clean):
                    pit = get(ph_clean, True)
                    if "wym" not in pit["sources"]:
                        pit["sources"].append("wym")

    # --- toefl_txt (adds gloss for words wym lacks; no thesaurus) ---
    for e in toefl:
        w = clean_word(e["word"])
        if not re.match(r"^[a-z][a-z'’\- ]*$", w):
            conflicts.append(f"toefl_txt skip malformed headword: {w!r}")
            continue
        it = get(w)
        if "toefl_txt" not in it["sources"]:
            it["sources"].append("toefl_txt")
        if not any(s["_gloss_origin"] == "wym" for s in it["senses"]):
            for s in e["senses"]:
                it["senses"].append({
                    "part_of_speech": s["pos"] or "n",
                    "gloss": tw(s["gloss"]),
                    "thesaurus": [],
                    "_gloss_origin": "toefl_txt",
                })
        else:
            conflicts.append(
                f"{w}: kept wym senses, ignored toefl_txt "
                f"({'; '.join(x['gloss'][:20] for x in e['senses'])})")

    # --- l6 (word + pos only) ---
    for e in l6:
        w = clean_word(e["word"])
        it = get(w)
        if "l6" not in it["sources"]:
            it["sources"].append("l6")
        if not it["senses"]:
            for p in e["pos"] or ["n"]:
                it["senses"].append({
                    "part_of_speech": p, "gloss": None,
                    "thesaurus": [], "_gloss_origin": "PENDING_AI",
                })

    # items created from phrase columns may have no senses yet
    for it in items.values():
        if not it["senses"]:
            it["senses"].append({
                "part_of_speech": "phr" if it["is_phrase"] else "n",
                "gloss": None, "thesaurus": [],
                "_gloss_origin": "PENDING_AI",
            })

    # --- difficulty ---
    ranks = coca_ranks()
    estimate, mono = fit_zipf_to_rank(ranks)

    def rank_of(word):
        if word in ranks:
            return ranks[word], "coca"
        z = zipf_frequency(word, "en")
        if z > 0:
            return max(1, round(10 ** estimate(z))), "zipf"
        return None, "none"

    stats = defaultdict(int)
    for it in items.values():
        r, src = rank_of(it["word"])
        stats[src] += 1
        it["difficulty"] = round(math.log2(r), 2) if r else None
        it["_rank"] = r
        it["_rank_source"] = src

    # --- word families ---
    fam = defaultdict(list)
    for w, it in items.items():
        if it["is_phrase"]:
            continue
        fam[stem(w)].append(w)
    fam_id = 0
    for key, words in sorted(fam.items()):
        if len(words) < 2:
            for w in words:
                items[w]["word_family_id"] = None
            continue
        fam_id += 1
        for w in words:
            items[w]["word_family_id"] = fam_id
    for it in items.values():
        it.setdefault("word_family_id", None)

    # --- phrase attributes & exam tags & ids ---
    out = []
    for i, w in enumerate(sorted(items), start=1):
        it = items[w]
        it["id"] = i
        it["exam_tags"] = ["toefl_itp"]
        it["phrase_attribute"] = (build_phrase_attribute(w)
                                  if it["is_phrase"] else None)
        if it["is_phrase"]:
            for s in it["senses"]:
                s["part_of_speech"] = "phr"
        del it["is_phrase"]
        out.append(it)

    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT / "vocabulary.json", "w"),
              ensure_ascii=False, indent=1)
    json.dump(conflicts, open(OUT / "merge_conflicts.json", "w"),
              ensure_ascii=False, indent=1)

    # --- AI todo lists ---
    need_meaning = [it["word"] for it in out
                    if any(s["gloss"] is None for s in it["senses"])]
    need_thesaurus = [it["word"] for it in out
                      if not it["phrase_attribute"]
                      and all(not s["thesaurus"] for s in it["senses"])]
    json.dump({"need_meaning": need_meaning,
               "need_thesaurus": need_thesaurus},
              open(OUT / "ai_todo.json", "w"), ensure_ascii=False, indent=1)

    print(f"items: {len(out)}  "
          f"(phrases: {sum(1 for x in out if x['phrase_attribute'])})")
    print(f"rank sources: {dict(stats)}")
    print(f"zipf calibration points: {[(z, round(l,2)) for z, l in mono]}")
    print(f"need_meaning: {len(need_meaning)}, "
          f"need_thesaurus: {len(need_thesaurus)}")
    print(f"conflicts logged: {len(conflicts)}")


if __name__ == "__main__":
    main()
