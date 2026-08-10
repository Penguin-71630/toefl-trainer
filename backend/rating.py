"""Elo: expected score, rank titles, TOEFL estimate, per-quiz update (§3)."""

from backend import config

OBJECTIVE_TYPES = {"cloze", "synonym", "structure", "written_expression"}
GRAMMAR_TYPES = {"structure", "written_expression"}


def rating_weight(question_type: str) -> float:
    if question_type in GRAMMAR_TYPES:
        return config.GRAMMAR_RATING_WEIGHT
    return 1.0


def expected(rating_user: float, rating_item: float, question_type: str) -> float:
    e_raw = 1 / (1 + 10 ** ((rating_item - rating_user) / 400))
    if question_type in OBJECTIVE_TYPES:
        return config.GUESS_FLOOR + (1 - config.GUESS_FLOOR) * e_raw
    return e_raw


def k_factor(exams_done: int) -> int:
    for limit, k in config.K_FACTORS:
        if limit is None or exams_done < limit:
            return k
    raise AssertionError("K_FACTORS must end with a (None, k) entry")


def quiz_delta(scores: list[float], expecteds: list[float],
               weights: list[float], exams_done: int) -> float:
    return k_factor(exams_done) * sum(
        w * (s - e)
        for s, e, w in zip(scores, expecteds, weights, strict=True))


def clamp_rating(rating: float) -> float:
    return max(config.RATING_FLOOR, min(config.RATING_CAP, rating))


def rank_title(rating: float) -> str:
    for limit, title in config.RANKS:
        if limit is None or rating < limit:
            return title
    raise AssertionError("RANKS must end with a (None, title) entry")


def toefl_estimate(rating: float) -> int:
    toefl = config.TOEFL_ANCHOR_SCORE + (
        rating - config.TOEFL_ANCHOR_RATING
    ) / config.TOEFL_PER_RATING
    return round(max(310, min(677, toefl)))
