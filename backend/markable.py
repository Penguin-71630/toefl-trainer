"""Locate deck words (difficulty >= 10) inside question text so the frontend
cursor can hover and mark them (§11). The backend owns the deck and the
inflection mapping; the frontend only moves a cursor over given spans."""

import re

from backend import config

_INDEX: dict[str, int] | None = None      # surface form -> item_id
_PHRASES: list[tuple[str, int]] | None = None


def _variants(word: str) -> list[str]:
    out = {word}
    if word.endswith("y"):
        out.add(word[:-1] + "ies")
        out.add(word[:-1] + "ied")
    if word.endswith("e"):
        out.add(word + "d")
        out.add(word[:-1] + "ing")
    out.add(word + "s")
    out.add(word + "es")
    out.add(word + "ed")
    out.add(word + "ing")
    return list(out)


def build_index(conn) -> None:
    global _INDEX, _PHRASES
    index: dict[str, int] = {}
    phrases: list[tuple[str, int]] = []
    rows = conn.execute(
        "SELECT id, word FROM vocabulary WHERE difficulty >= ?",
        (config.MARKABLE_MIN_DIFFICULTY,)).fetchall()
    for row in rows:
        word = row["word"].lower()
        if " " in word:
            phrases.append((word, row["id"]))
        else:
            for form in _variants(word):
                # a base form always beats an inflected collision
                if form not in index or form == word:
                    index[form] = row["id"]
    _INDEX = index
    _PHRASES = phrases


def find_markable(text: str) -> list[dict]:
    """Return [{span: [start, end], item_id}] sorted by position."""
    assert _INDEX is not None and _PHRASES is not None, "call build_index first"
    lower = text.lower()
    found: list[dict] = []
    taken: list[tuple[int, int]] = []

    for phrase, item_id in _PHRASES:
        start = lower.find(phrase)
        while start >= 0:
            end = start + len(phrase)
            if _is_word_boundary(lower, start, end):
                found.append({"span": [start, end], "item_id": item_id})
                taken.append((start, end))
            start = lower.find(phrase, end)

    for match in re.finditer(r"[a-z']+", lower):
        start, end = match.span()
        if any(s <= start < e or s < end <= e for s, e in taken):
            continue
        item_id = _INDEX.get(match.group())
        if item_id is not None:
            found.append({"span": [start, end], "item_id": item_id})

    found.sort(key=lambda m: m["span"][0])
    return found


def _is_word_boundary(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else " "
    after = text[end] if end < len(text) else " "
    return not before.isalnum() and not after.isalnum()
