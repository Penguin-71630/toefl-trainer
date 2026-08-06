"""Parse 高中英文參考詞彙表 第六級 (l6.txt, from pdftotext -layout).

Three-column layout of 'word pos[/pos...]' cells; no Chinese glosses.
Handles continuation lines where the POS wrapped to the next line.
Output: data/intermediate/l6.json
"""

import json
import re
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "l6.txt"
OUT = Path(__file__).resolve().parent.parent / "data" / "intermediate" / "l6.json"

POS_MAP = {
    "n": "n", "v": "v", "adj": "adj", "adv": "adv", "prep": "prep",
    "conj": "conj", "interj": "interj", "int": "interj", "pron": "pron",
    "aux": "v", "art": "n", "abbr": "n", "det": "adj",
}
POS_PAT = r"(?:n|v|adj|adv|prep|conj|interj|int|pron|aux|art|abbr|det)"
CELL_RE = re.compile(
    rf"^(?P<word>[A-Za-z][A-Za-z\u00c0-\u00ff’'\-/() ]*?)\s+"
    rf"(?P<pos>\(?{POS_PAT}\.?\)?(?:/\(?{POS_PAT}\.?\)?)*)$"
)
WORD_ONLY_RE = re.compile(r"^[A-Za-z][A-Za-z\u00c0-\u00ff’'\-/() ]*$")
POS_ONLY_RE = re.compile(rf"^\(?{POS_PAT}\.?\)?(?:/\(?{POS_PAT}\.?\)?)*$")


def norm_pos(pos_str):
    out = []
    for p in pos_str.split("/"):
        p = p.strip().strip("().").rstrip(".")
        mapped = POS_MAP.get(p)
        if mapped and mapped not in out:
            out.append(mapped)
    return out


def parse():
    entries = []
    anomalies = []
    pending = None  # word whose POS wrapped to the next line

    for line in RAW.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or "第六級" in stripped or "詞彙表" in stripped \
                or "排序" in stripped or re.match(r"^\d+$", stripped):
            continue
        for cell in re.split(r"\s{2,}", stripped):
            cell = cell.strip()
            if not cell:
                continue
            m = CELL_RE.match(cell)
            if m:
                for w in m.group("word").split("/"):
                    w = w.strip().lower()
                    if w:
                        entries.append({"word": w, "pos": norm_pos(m.group("pos"))})
                pending = None
            elif POS_ONLY_RE.match(cell) and pending:
                for w in pending.split("/"):
                    w = w.strip().lower()
                    if w:
                        entries.append({"word": w, "pos": norm_pos(cell)})
                pending = None
            elif WORD_ONLY_RE.match(cell):
                pending = cell
            else:
                anomalies.append(cell[:120])

    # dedupe, merging pos lists
    merged = {}
    for e in entries:
        w = e["word"].strip()
        w = re.sub(r"\(.*?\)", "", w).strip()  # attain(ment) -> attain
        if not w:
            continue
        if w in merged:
            for p in e["pos"]:
                if p not in merged[w]:
                    merged[w].append(p)
        else:
            merged[w] = list(e["pos"])
    entries = [{"word": w, "pos": p} for w, p in sorted(merged.items())]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"entries": entries, "anomalies": anomalies},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"l6: {len(entries)} unique words, {len(anomalies)} anomaly cells")


if __name__ == "__main__":
    parse()
