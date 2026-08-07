"""Build answer options for vocabulary questions (§6).

The backend owns options and the answer index; the LLM never sees the answer.
"""

import json
import random
from difflib import SequenceMatcher

from backend import config


def _candidate_rows(conn, target: dict) -> list:
    return conn.execute(
        """SELECT id, word, word_family_id, senses FROM vocabulary
           WHERE id != ? AND difficulty BETWEEN ? AND ?
             AND word NOT LIKE '% %'""",
        (target["item_id"],
         target["difficulty"] - config.DISTRACTOR_DIFFICULTY_WINDOW,
         target["difficulty"] + config.DISTRACTOR_DIFFICULTY_WINDOW)).fetchall()


def _weight(cand_row, cand_sense, target: dict, target_family: int | None,
            target_pos: str, target_thesaurus: set[str]) -> float:
    word = cand_row["word"]
    if word.lower() in target_thesaurus:
        return 0                       # would be a second correct answer
    same_family = (target_family is not None
                   and cand_row["word_family_id"] == target_family)
    same_pos = cand_sense.get("part_of_speech") == target_pos
    if same_family and not same_pos:
        return 0                       # word-form questions are out of scope
    if same_family and same_pos:
        return config.FAMILY_SAME_POS_WEIGHT
    ratio = SequenceMatcher(None, target["word"], word).ratio()
    return 1 + config.SIMILARITY_WEIGHT * ratio


def cloze_options(conn, target: dict) -> tuple[list[str], int]:
    """3 same-POS distractors + the target word, shuffled."""
    sense = target["sense"]
    pos = sense.get("part_of_speech") or ""
    thesaurus = {t.lower() for t in (sense.get("thesaurus") or [])}
    family = None
    row = conn.execute("SELECT word_family_id FROM vocabulary WHERE id=?",
                       (target["item_id"],)).fetchone()
    if row:
        family = row["word_family_id"]

    weighted = []
    for cand in _candidate_rows(conn, target):
        for cs in json.loads(cand["senses"]):
            if cs.get("part_of_speech") == pos:
                w = _weight(cand, cs, target, family, pos, thesaurus)
                if w > 0:
                    weighted.append((cand["word"], w))
                break
    distractors = _sample_words(weighted, 3)
    if len(distractors) < 3:
        distractors += _fallback_pool(conn, target, pos,
                                      exclude={target["word"], *distractors},
                                      n=3 - len(distractors))
    options = distractors[:3] + [target["word"]]
    random.shuffle(options)
    return options, options.index(target["word"])


def synonym_options(conn, target: dict) -> tuple[list[str], int]:
    """Correct = a thesaurus word of the chosen sense; distractors include one
    thesaurus word of ANOTHER sense when available (the ITP 'as used in the
    passage' trap), plus weighted candidates."""
    sense = target["sense"]
    correct = random.choice(sense["thesaurus"])
    used = {correct.lower(), target["word"].lower()}

    distractors: list[str] = []
    other_thesaurus = [t for i, s in enumerate(target["senses"])
                       if i != target["sense_index"]
                       for t in (s.get("thesaurus") or [])
                       if t.lower() not in used]
    if other_thesaurus:
        trap = random.choice(other_thesaurus)
        distractors.append(trap)
        used.add(trap.lower())

    pos = sense.get("part_of_speech") or ""
    if pos in ("", "phr"):
        # phrase targets have no single-word POS peers; match the POS of
        # the correct answer instead so distractors stay plausible
        pos = _word_pos(conn, correct) or pos
    thesaurus = {t.lower() for t in sense["thesaurus"]}
    weighted = []
    for cand in _candidate_rows(conn, target):
        if cand["word"].lower() in used:
            continue
        for cs in json.loads(cand["senses"]):
            if cs.get("part_of_speech") == pos:
                if cand["word"].lower() in thesaurus:
                    break
                ratio = SequenceMatcher(None, correct, cand["word"]).ratio()
                weighted.append((cand["word"],
                                 1 + config.SIMILARITY_WEIGHT * ratio))
                break
    distractors += _sample_words(weighted, 3 - len(distractors))
    if len(distractors) < 3:
        distractors += _fallback_pool(conn, target, pos,
                                      exclude=used | set(distractors),
                                      n=3 - len(distractors))
    options = distractors[:3] + [correct]
    random.shuffle(options)
    return options, options.index(correct)


def _word_pos(conn, word: str) -> str | None:
    """POS of a word: its own vocabulary entry if present, else the most
    common POS among senses that list it as a thesaurus synonym."""
    row = conn.execute(
        "SELECT senses FROM vocabulary WHERE lower(word) = lower(?)",
        (word,)).fetchone()
    if row:
        return json.loads(row["senses"])[0].get("part_of_speech")
    votes: dict[str, int] = {}
    for r in conn.execute("SELECT senses FROM vocabulary WHERE senses LIKE ?",
                          (f'%"{word}"%',)):
        for s in json.loads(r["senses"]):
            p = s.get("part_of_speech")
            if p and p != "phr" and word in (s.get("thesaurus") or []):
                votes[p] = votes.get(p, 0) + 1
    return max(votes, key=votes.get) if votes else None


def _sample_words(weighted: list[tuple[str, float]], n: int) -> list[str]:
    picked: list[str] = []
    pool = [(w, wt) for w, wt in weighted if wt > 0]
    while pool and len(picked) < n:
        total = sum(wt for _, wt in pool)
        r = random.uniform(0, total)
        acc = 0.0
        for word, wt in pool:
            acc += wt
            if acc >= r:
                picked.append(word)
                pool = [(w2, wt2) for w2, wt2 in pool
                        if w2.lower() != word.lower()]
                break
    return picked


def _fallback_pool(conn, target: dict, pos: str, exclude: set[str],
                   n: int) -> list[str]:
    rows = conn.execute(
        """SELECT word, senses FROM vocabulary
           WHERE id != ? AND word NOT LIKE '% %'
           ORDER BY ABS(difficulty - ?) LIMIT 400""",
        (target["item_id"], target["difficulty"])).fetchall()
    out = []
    lowered = {e.lower() for e in exclude}
    for strict in (True, False):
        for row in rows:
            if row["word"].lower() in lowered:
                continue
            if strict and not any(s.get("part_of_speech") == pos
                                  for s in json.loads(row["senses"])):
                continue
            out.append(row["word"])
            lowered.add(row["word"].lower())
            if len(out) >= n:
                return out
    return out
