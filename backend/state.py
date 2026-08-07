"""Per-item memory state: proficiency EMA, streak, unfamiliar marks (§4)."""

from datetime import datetime, timezone

from backend import config, rating


def p_init(rating_user: float, rating_item: float, question_type: str) -> float:
    return rating.expected(rating_user, rating_item, question_type)


def update_proficiency(p_old: float, score: float) -> float:
    alpha = config.ALPHA_UP if score >= p_old else config.ALPHA_DOWN
    return p_old + alpha * (score - p_old)


def update_streak(streak: int, score: float) -> int:
    return streak + 1 if score >= 0.5 else 0


def update_unfamiliar(unfamiliar_score: int, marked: bool) -> int:
    if marked:
        return unfamiliar_score + config.UNFAMILIAR_MARK_BONUS
    return max(unfamiliar_score - config.UNFAMILIAR_DECAY, 0)


def days_since(last_seen_at: str | None) -> float:
    if not last_seen_at:
        return 9999.0
    last = datetime.fromisoformat(last_seen_at)
    return (datetime.now(timezone.utc) - last).total_seconds() / 86400


def effective_proficiency(p_stored: float, streak: int,
                          last_seen_at: str | None) -> float:
    """Decay only above 0.5: mastery fades toward uncertainty, weakness stays."""
    if p_stored <= 0.5:
        return p_stored
    half_life = min(
        config.HALF_LIFE_BASE * config.HALF_LIFE_GROWTH ** streak,
        config.HALF_LIFE_MAX)
    decay = 0.5 ** (days_since(last_seen_at) / half_life)
    return p_stored + (0.5 - p_stored) * (1 - decay)


def apply_review(conn, user_id: int, *, item_id: int | None,
                 grammar_point_id: int | None, score: float, marked: bool,
                 rating_user: float, rating_item: float,
                 question_type: str) -> None:
    """Upsert user_items / user_grammar_points after one answer."""
    if item_id is not None:
        table, key_col, key = "user_items", "item_id", item_id
        prior = p_init(rating_user, rating_item, question_type)
    else:
        table, key_col, key = ("user_grammar_points", "grammar_point_id",
                               grammar_point_id)
        prior = config.GRAMMAR_P_INIT

    row = conn.execute(
        f"SELECT * FROM {table} WHERE user_id=? AND {key_col}=?",
        (user_id, key)).fetchone()
    if row is None:
        p_old, streak, unfam = prior, 0, 0
        correct, wrong = 0, 0
    else:
        p_old, streak, unfam = (row["proficiency"], row["streak"],
                                row["unfamiliar_score"])
        correct, wrong = row["correct_count"], row["wrong_count"]

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        f"""INSERT INTO {table}
            (user_id, {key_col}, correct_count, wrong_count, proficiency,
             streak, unfamiliar_score, last_seen_at)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id, {key_col}) DO UPDATE SET
              correct_count=excluded.correct_count,
              wrong_count=excluded.wrong_count,
              proficiency=excluded.proficiency,
              streak=excluded.streak,
              unfamiliar_score=excluded.unfamiliar_score,
              last_seen_at=excluded.last_seen_at""",
        (user_id, key,
         correct + (1 if score >= 0.5 else 0),
         wrong + (0 if score >= 0.5 else 1),
         update_proficiency(p_old, score),
         update_streak(streak, score),
         update_unfamiliar(unfam, marked),
         now))


def mark_word(conn, user_id: int, item_id: int, marked: bool,
              rating_user: float, rating_item: float) -> None:
    """User pressed ENTER on a markable word (independent of answering)."""
    row = conn.execute(
        "SELECT * FROM user_items WHERE user_id=? AND item_id=?",
        (user_id, item_id)).fetchone()
    if row is None:
        prior = p_init(rating_user, rating_item, "synonym")
        unfam = config.UNFAMILIAR_MARK_BONUS if marked else 0
        conn.execute(
            """INSERT INTO user_items (user_id, item_id, proficiency, streak,
               unfamiliar_score, last_seen_at) VALUES (?,?,?,0,?,?)""",
            (user_id, item_id, prior, unfam,
             datetime.now(timezone.utc).isoformat()))
    else:
        unfam = update_unfamiliar(row["unfamiliar_score"], marked)
        conn.execute(
            "UPDATE user_items SET unfamiliar_score=? WHERE user_id=? AND item_id=?",
            (unfam, user_id, item_id))
