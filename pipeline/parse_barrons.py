"""Parse Barron's Essential Words for the TOEFL (EPUB) lesson word lists.

Each lesson (06_Ch5-Lxx.xhtml) contains one table per headword:
- row 1: headword | pos | English definition
- later rows: derived-form pos | derived form, and 'syn.' | synonyms
Example sentences follow each table as <p> elements.
Output: data/intermediate/barrons.json
"""

import json
import re
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
EPUB = BASE / "data" / "raw" / "barrons_essential_words.epub"
OUT = BASE / "data" / "intermediate" / "barrons.json"

POS_MAP = {
    "n": "n", "v": "v", "adj": "adj", "adv": "adv", "prep": "prep",
    "conj": "conj", "interj": "interj", "pron": "pron",
    "vt": "v", "vi": "v",
}


def strip_tags(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def parse():
    entries = []
    anomalies = []
    with zipfile.ZipFile(EPUB) as z:
        lessons = sorted(n for n in z.namelist()
                         if re.search(r"06_Ch5-L\d+\.xhtml$", n))
        for lesson_i, name in enumerate(lessons, start=1):
            html = z.read(name).decode("utf-8", errors="ignore")
            # split into blocks: each table + trailing <p> examples
            parts = re.split(r"(<table class=\"tword\".*?</table>)", html,
                             flags=re.S)
            for i in range(1, len(parts), 2):
                table, tail = parts[i], parts[i + 1]
                rows = re.findall(r"<tr>(.*?)</tr>", table, re.S)
                if not rows:
                    anomalies.append(f"L{lesson_i}: empty table")
                    continue
                cells0 = re.findall(r"<td[^>]*>(.*?)</td>", rows[0], re.S)
                if len(cells0) < 3:
                    anomalies.append(f"L{lesson_i}: bad first row")
                    continue
                word = strip_tags(cells0[0]).lower()
                pos = POS_MAP.get(strip_tags(cells0[1]).rstrip("."),
                                  None)
                definition = strip_tags(cells0[2]) if len(cells0) == 3 \
                    else strip_tags(cells0[2] + " " + cells0[3])
                # for 4-col first rows: pos in col 3, def in col 4
                if len(cells0) == 4:
                    pos = POS_MAP.get(strip_tags(cells0[2]).rstrip("."), pos)
                    definition = strip_tags(cells0[3])

                synonyms, derived = [], []
                for row in rows[1:]:
                    cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
                    texts = [strip_tags(c) for c in cells]
                    for j, t in enumerate(texts):
                        if t == "syn." and j + 1 < len(texts):
                            synonyms += [s.strip().lower() for s in
                                         re.split(r"[;,]", texts[j + 1])
                                         if s.strip()]
                        elif re.fullmatch(r"(?:adj|adv|n|v|vt|vi|prep)\.", t) \
                                and j + 1 < len(texts) and texts[j + 1] \
                                and texts[j + 1] != "syn.":
                            form = texts[j + 1].lower()
                            if re.fullmatch(r"[a-z'’\- ]+", form):
                                derived.append(
                                    {"form": form,
                                     "pos": POS_MAP.get(t.rstrip("."))})

                examples = []
                for p in re.findall(r"<p class=\"noindent1?\">(.*?)</p>",
                                    tail, re.S):
                    txt = strip_tags(p)
                    if txt:
                        examples.append(txt)

                entries.append({
                    "word": word, "pos": pos, "definition_en": definition,
                    "synonyms": synonyms, "derived": derived,
                    "examples": examples[:2], "lesson": lesson_i,
                })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"entries": entries, "anomalies": anomalies},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"barrons: {len(entries)} entries, "
          f"{sum(len(e['derived']) for e in entries)} derived forms, "
          f"{len(anomalies)} anomalies")


if __name__ == "__main__":
    parse()
