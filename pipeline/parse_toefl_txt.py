"""Parse mahavivo TOEFL.txt (word / IPA / pos+simplified-Chinese glosses).

Line format examples:
  abandon           [ə'bændən]            vt.  放弃,沉溺n.  放任
  abashed           [ə'bæʃt]              adj.  1  (在人前) 感觉羞愧的...
Output: data/intermediate/toefl_txt.json
"""

import json
import re
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "toefl_txt.txt"
OUT = Path(__file__).resolve().parent.parent / "data" / "intermediate" / "toefl_txt.json"

POS_MAP = {
    "vt": "v", "vi": "v", "v": "v", "n": "n", "adj": "adj", "a": "adj",
    "adv": "adv", "ad": "adv", "prep": "prep", "conj": "conj",
    "interj": "interj", "int": "interj", "pron": "pron", "aux": "v",
    "num": "n", "abbr": "n",
}
POS_TOKEN = re.compile(r"(?:^|(?<=[^a-zA-Z]))(" + "|".join(POS_MAP) + r")\.\s*")

LINE_RE = re.compile(
    r"^(?P<word>[a-zA-Z][a-zA-Z\-'’ ]*?)\s+\[(?P<ipa>[^\]]*)\]\s*(?P<body>.*)$"
)


def parse_body(body: str):
    """Split '<pos>. gloss<pos>. gloss...' into senses."""
    senses = []
    matches = list(POS_TOKEN.finditer(body))
    if not matches:
        gloss = body.strip()
        if gloss:
            senses.append({"pos": None, "gloss": gloss})
        return senses
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        gloss = body[m.end():end].strip(" ,;，；")
        senses.append({"pos": POS_MAP[m.group(1)], "gloss": gloss})
    return senses


def parse():
    entries = []
    anomalies = []
    for line in RAW.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        m = LINE_RE.match(line)
        if not m:
            anomalies.append(line.strip()[:120])
            continue
        word = m.group("word").strip().lower()
        senses = parse_body(m.group("body"))
        entries.append({"word": word, "ipa": m.group("ipa"), "senses": senses})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"entries": entries, "anomalies": anomalies},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"toefl_txt: {len(entries)} entries, "
          f"{sum(len(e['senses']) for e in entries)} senses, "
          f"{len(anomalies)} anomaly lines")


if __name__ == "__main__":
    parse()
