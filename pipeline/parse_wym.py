"""Parse 王玉梅托福词汇 (wym.txt, from pdftotext -layout) into structured JSON.

Layout: numbered entries with columns 词条 / 含义 / 近义 / 词组.
- A single numbered entry may span multiple lines (one line per sense).
- Derived words appear as their own rows (sometimes unnumbered).
- Phrase rows (词组 sections) have no POS column and multi-word headwords.
- Column offsets vary per "Word list" section; we track the latest header.
Output: data/intermediate/wym.json
"""

import json
import re
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw" / "wym.txt"
OUT = Path(__file__).resolve().parent.parent / "data" / "intermediate" / "wym.json"

POS_RE = r"(?:vt|vi|v|n|adj|adv|prep|conj|interj|int|pron|aux)\.?"
CJK = r"\u4e00-\u9fff\u3000-\u303f\uff00-\uffef（）…"

LINE_RE = re.compile(
    rf"^\s*(?P<num>\d+)?\s*"
    rf"(?P<word>[a-zA-Z][a-zA-Z'’\-/ ()]*?)?\s*"
    rf"(?P<pos>{POS_RE}(?:/{POS_RE})*)\s+"
    rf"(?P<rest>(?:pl\.|[（(\[])?[{CJK}].*)$"
)

# phrase rows (词组 entries): no POS column, headword is a multi-word phrase
PHRASE_LINE_RE = re.compile(
    rf"^\s*(?P<num>\d+)?\s+"
    rf"(?P<word>[a-zA-Z][a-zA-Z'’\-]*(?: [a-zA-Z'’\-…]+)+)\s{{2,}}"
    rf"(?P<rest>[{CJK}].*)$"
)

POS_MAP = {
    "vt": "v", "vi": "v", "v": "v", "n": "n", "adj": "adj", "adv": "adv",
    "prep": "prep", "conj": "conj", "interj": "interj", "int": "interj",
    "pron": "pron", "aux": "v",
}


def is_ascii_chunk(s: str) -> bool:
    return bool(s) and all(ord(c) < 0x2E80 for c in s)


def split_rest(line: str, rest_start: int, phr_off: int):
    """Split the tail of a line into (gloss, synonyms, phrases) using
    absolute column positions for the synonyms/phrases distinction."""
    rest = line[rest_start:].rstrip()
    am = re.search(r"\s{2,}(?=[A-Za-z(])", rest)
    if am:
        gloss = rest[: am.start()].strip()
        ascii_abs = rest_start + am.end()
        ascii_part = rest[am.end():]
    else:
        return rest.strip(), [], []

    synonyms, phrases = [], []
    for chunk_m in re.finditer(r"[^\s].*?(?=\s{2,}|$)", ascii_part):
        chunk = chunk_m.group(0).strip()
        if not chunk:
            continue
        col = ascii_abs + chunk_m.start()
        if phr_off > 0 and col >= phr_off - 6:
            phrases.append(chunk)
        else:
            for s in re.split(r"[;；]", chunk):
                for t in re.split(r"[,/]", s):
                    t = t.strip()
                    if t and is_ascii_chunk(t):
                        synonyms.append(t)
    return gloss, synonyms, phrases


def parse():
    text = RAW.read_text(encoding="utf-8", errors="ignore")
    pages = text.split("\f")

    entries = []
    anomalies = []
    phr_off = 86  # default; updated at each header
    current = None

    for page in pages:
        for line in page.splitlines():
            if "词条" in line and "含义" in line:
                phr_off = line.find("词组")
                continue
            if not line.strip():
                continue
            if (re.match(r"^\s*(Word list|Page |ada99:)", line)
                    or re.match(r"^\s*\d+\s*$", line)
                    or re.match(rf"^\s*[{CJK}]{{1,2}}\s*$", line)):
                continue  # headers, page numbers, stray cells like 词/组

            m = LINE_RE.match(line)
            if m:
                word = (m.group("word") or "").strip()
                pos = POS_MAP.get(m.group("pos").split("/")[0].rstrip("."))
                gloss, synonyms, phrases = split_rest(line, m.start("rest"), phr_off)
                sense = {"pos": pos, "gloss": gloss,
                         "thesaurus": synonyms, "phrases": phrases}
                if word and (not current or word.lower() != current["word"]):
                    current = {"word": word.lower(), "is_phrase": False,
                               "senses": [sense]}
                    entries.append(current)
                elif current:
                    current["senses"].append(sense)
                continue

            pm = PHRASE_LINE_RE.match(line)
            if pm:
                word = pm.group("word").strip().lower()
                gloss, synonyms, _ = split_rest(line, pm.start("rest"), phr_off)
                sense = {"pos": "phr", "gloss": gloss,
                         "thesaurus": synonyms, "phrases": []}
                current = {"word": word, "is_phrase": True, "senses": [sense]}
                entries.append(current)
                continue

            if line.strip():
                anomalies.append(line.strip()[:120])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"entries": entries, "anomalies": anomalies},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wym: {len(entries)} entries "
          f"({sum(1 for e in entries if e['is_phrase'])} phrases), "
          f"{sum(len(e['senses']) for e in entries)} senses, "
          f"{len(anomalies)} anomaly lines")


if __name__ == "__main__":
    parse()
