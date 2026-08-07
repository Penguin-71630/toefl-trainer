"""Pick quiz targets by weighted random sampling without replacement (§5)."""

import json
import math
import random

from backend import config, state

VOCAB_TYPES = {"cloze", "synonym"}
GRAMMAR_TYPES = {"structure", "written_expression"}


def _roulette(pool: list[tuple[dict, float]], n: int) -> list[dict]:
    """Weighted sampling without replacement (random.choices would repeat)."""
    pool = [(item, w) for item, w in pool if w > 0]
    picked = []
    while pool and len(picked) < n:
        total = sum(w for _, w in pool)
        r = random.uniform(0, total)
        acc = 0.0
        for i, (item, w) in enumerate(pool):
            acc += w
            if acc >= r:
                picked.append(item)
                pool.pop(i)
                break
    return picked


def _vocab_weight(row, user_rating: float, question_type: str) -> float:
    if row["last_seen_at"] is None:
        p_eff = state.p_init(user_rating, row["rating"], question_type)
        days = 9999.0
        unfam = 0
    else:
        p_eff = state.effective_proficiency(
            row["proficiency"], row["streak"], row["last_seen_at"])
        days = state.days_since(row["last_seen_at"])
        unfam = row["unfamiliar_score"]
    w_prof = 1 + 3 * (1 - p_eff)
    w_unfamiliar = 1 + 0.5 * unfam
    w_recency = min(1.0, 0.2 + 0.8 * days / config.W_RECENCY_DAYS)
    w_level = math.exp(
        -((row["rating"] - user_rating) / config.W_LEVEL_SIGMA) ** 2)
    return (w_prof * w_unfamiliar * w_recency * w_level) ** config.TEMPERATURE


def _eligible_sense_indices(senses: list[dict], question_type: str) -> list[int]:
    out = []
    for i, s in enumerate(senses):
        pos = s.get("part_of_speech") or ""
        if not s.get("gloss"):
            continue
        if question_type == "synonym" and not s.get("thesaurus"):
            continue
        if question_type == "cloze" and pos in ("phr", ""):
            # cloze needs a plain word with a clear part of speech
            continue
        out.append(i)
    return out


def _pick_sense(conn, user_id: int, item_id: int, indices: list[int]) -> int:
    """Prefer the least-practised eligible sense."""
    if len(indices) == 1:
        return indices[0]
    counts = {i: 0 for i in indices}
    for row in conn.execute(
            "SELECT sense_index, COUNT(*) AS n FROM reviews "
            "WHERE user_id=? AND item_id=? GROUP BY sense_index",
            (user_id, item_id)):
        if row["sense_index"] in counts:
            counts[row["sense_index"]] = row["n"]
    least = min(counts.values())
    return random.choice([i for i, c in counts.items() if c == least])


def pick_vocab_targets(conn, user, question_type: str, n: int,
                       exclude_ids: set[int] | None = None) -> list[dict]:
    exclude_ids = exclude_ids or set()
    user_rating = user["rating"]
    rows = conn.execute(
        """SELECT v.id, v.word, v.rating, v.difficulty, v.senses,
                  ui.proficiency, ui.streak, ui.unfamiliar_score, ui.last_seen_at
           FROM vocabulary v
           LEFT JOIN user_items ui ON ui.item_id = v.id AND ui.user_id = ?
           WHERE v.rating BETWEEN ? AND ?""",
        (user["id"],
         user_rating - config.POOL_RATING_WINDOW,
         user_rating + config.POOL_RATING_WINDOW)).fetchall()

    weighted_new, weighted_seen = [], []
    for row in rows:
        if row["id"] in exclude_ids:
            continue
        senses = json.loads(row["senses"])
        indices = _eligible_sense_indices(senses, question_type)
        if not indices:
            continue
        entry = {"item_id": row["id"], "word": row["word"],
                 "rating": row["rating"], "difficulty": row["difficulty"],
                 "senses": senses, "sense_indices": indices}
        w = _vocab_weight(row, user_rating, question_type)
        (weighted_new if row["last_seen_at"] is None
         else weighted_seen).append((entry, w))

    quota = min(config.NEW_ITEM_QUOTA, n)
    picked = _roulette(weighted_new, quota)
    remaining = weighted_seen + [
        (e, w) for e, w in weighted_new if e not in picked]
    picked += _roulette(remaining, n - len(picked))

    for target in picked:
        target["sense_index"] = _pick_sense(
            conn, user["id"], target["item_id"], target["sense_indices"])
        target["sense"] = target["senses"][target["sense_index"]]
    return picked


def pick_grammar_targets(conn, user, n: int) -> list[dict]:
    rows = conn.execute(
        """SELECT g.*, ug.proficiency, ug.streak, ug.unfamiliar_score,
                  ug.last_seen_at
           FROM grammar_points g
           LEFT JOIN user_grammar_points ug
             ON ug.grammar_point_id = g.id AND ug.user_id = ?""",
        (user["id"],)).fetchall()
    weighted = []
    for row in rows:
        if row["last_seen_at"] is None:
            p_eff, days, unfam = config.GRAMMAR_P_INIT, 9999.0, 0
        else:
            p_eff = state.effective_proficiency(
                row["proficiency"], row["streak"], row["last_seen_at"])
            days = state.days_since(row["last_seen_at"])
            unfam = row["unfamiliar_score"]
        w_prof = 1 + 3 * (1 - p_eff)
        w_unfamiliar = 1 + 0.5 * unfam
        w_recency = min(1.0, 0.2 + 0.8 * days / config.W_RECENCY_DAYS)
        w = (w_prof * w_unfamiliar * w_recency) ** config.TEMPERATURE
        entry = {"grammar_point_id": row["id"], "name": row["name"],
                 "category": row["category"], "description": row["description"],
                 "example": json.loads(row["example"]),
                 "error_patterns": json.loads(row["error_patterns"])}
        weighted.append((entry, w))
    picked = _roulette(weighted, n)
    for target in picked:
        target["error_pattern"] = random.choice(target["error_patterns"])
    return picked


def pick_targets(conn, user, question_type: str, n: int) -> list[dict]:
    if question_type in VOCAB_TYPES:
        return pick_vocab_targets(conn, user, question_type, n)
    if question_type in GRAMMAR_TYPES:
        return pick_grammar_targets(conn, user, n)
    raise ValueError(f"unknown question type: {question_type}")
