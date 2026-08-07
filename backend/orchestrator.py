"""Quiz lifecycle: build (sampler → distractor → generator → validator),
in-memory quiz store, question bank reuse, submit (grade → state → Elo)."""

import asyncio
import json
import random
import time
import uuid

from backend import (
    config,
    db,
    distractor,
    generator,
    grader,
    markable,
    rating,
    sampler,
    state,
    validator,
)

LETTERS = "ABCDE"


class QuizStore:
    """Volatile: quiz_id -> quiz dict. Answers never leave the backend
    before submit. TTL-evicted."""

    def __init__(self):
        self._quizzes: dict[str, dict] = {}

    def create(self, user_id: int, question_type: str, total: int) -> str:
        self._evict()
        quiz_id = uuid.uuid4().hex
        self._quizzes[quiz_id] = {
            "quiz_id": quiz_id, "user_id": user_id,
            "question_type": question_type, "total": total,
            "questions": [], "failed": 0, "submitted": False,
            "created_at": time.monotonic(),
        }
        return quiz_id

    def get(self, quiz_id: str) -> dict | None:
        self._evict()
        return self._quizzes.get(quiz_id)

    def _evict(self):
        cutoff = time.monotonic() - config.QUIZ_TTL_SECONDS
        for qid in [q for q, v in self._quizzes.items()
                    if v["created_at"] < cutoff]:
            del self._quizzes[qid]


store = QuizStore()
_conn = None
_provider = None
_lock = asyncio.Lock()


def setup(conn, provider) -> None:
    global _conn, _provider
    _conn = conn
    _provider = provider
    markable.build_index(conn)


# ---------------------------------------------------------------- build

def _bank_take(user_id: int, question_type: str, n: int) -> list[dict]:
    rows = _conn.execute(
        """SELECT id, payload FROM question_bank
           WHERE user_id=? AND question_type=?
           ORDER BY created_at LIMIT ?""",
        (user_id, question_type, n)).fetchall()
    questions = []
    for row in rows:
        questions.append(json.loads(row["payload"]))
        _conn.execute("DELETE FROM question_bank WHERE id=?", (row["id"],))
    _conn.commit()
    return questions


def bank_put(user_id: int, question_type: str, questions: list[dict]) -> None:
    _conn.executemany(
        "INSERT INTO question_bank (user_id, question_type, payload, created_at)"
        " VALUES (?,?,?,?)",
        [(user_id, question_type, json.dumps(q, ensure_ascii=False),
          db.now_iso()) for q in questions])
    _conn.commit()


async def _build_vocab_question(target: dict, question_type: str) -> dict | None:
    if question_type == "cloze":
        options, answer_index = distractor.cloze_options(_conn, target)
    else:
        options, answer_index = distractor.synonym_options(_conn, target)
    if len(options) != 4:
        return None
    reason = ""
    for _ in range(config.GENERATION_ATTEMPTS):
        raw = await generator.generate(_provider, target, options,
                                       question_type, retry_hint=reason,
                                       answer_index=answer_index)
        reason = validator.check(raw, target, options, question_type)
        if reason is None:
            sentence = raw["sentence"]
            notes = "\n".join(
                f"({LETTERS[i]}) {o}: {raw['option_notes'][o]}"
                for i, o in enumerate(options))
            explanation = (f"{raw['translation']}\n\n{notes}\n\n"
                           f"{raw['reasoning']}")
            return {
                "question_type": question_type,
                "item_id": target["item_id"],
                "sense_index": target["sense_index"],
                "word": target["word"],
                "gloss": target["sense"].get("gloss", ""),
                "item_rating": target["rating"],
                "sentence": sentence,
                "options": options,
                "answer_index": answer_index,
                "explanation": explanation,
                "markable": markable.find_markable(sentence),
                "generated_by": f"{_provider.name}:{_provider.model}",
            }
    return None


async def _build_grammar_question(target: dict, question_type: str) -> dict | None:
    reason = ""
    for _ in range(config.GENERATION_ATTEMPTS):
        raw = await generator.generate(_provider, target, None,
                                       question_type, retry_hint=reason)
        reason = validator.check(raw, target, None, question_type)
        if reason is None:
            base = {
                "question_type": question_type,
                "grammar_point_id": target["grammar_point_id"],
                "grammar_point": target["name"],
                "item_rating": config.GRAMMAR_DEFAULT_RATING,
                "explanation": raw["explanation"],
                "generated_by": f"{_provider.name}:{_provider.model}",
            }
            if question_type == "structure":
                options = [raw["correct_option"]] + [
                    w["text"] for w in raw["wrong_options"]]
                order = list(range(4))
                random.shuffle(order)
                shuffled = [options[i] for i in order]
                base.update({
                    "sentence": raw["stem"],
                    "options": shuffled,
                    "answer_index": order.index(0),
                    "markable": markable.find_markable(raw["stem"]),
                })
            else:
                base.update({
                    "sentence": raw["_display_sentence"],
                    "segments": raw["segments"],
                    "segment_offsets": raw["_segment_offsets"],
                    "corrected_segment": raw["corrected_segment"],
                    "answer_index": raw["wrong_index"],
                    "markable": markable.find_markable(raw["_display_sentence"]),
                })
            return base
    return None


async def generate_quiz(quiz_id: str) -> None:
    """Background task: fill quiz['questions'] until total, bank-first."""
    quiz = store.get(quiz_id)
    if quiz is None:
        return
    user_id, qtype, total = (quiz["user_id"], quiz["question_type"],
                             quiz["total"])
    quiz["questions"].extend(_bank_take(user_id, qtype, total))

    if _provider.name == "fixture":
        need = total - len(quiz["questions"])
        if need > 0:
            quiz["questions"].extend(_provider.take_questions(qtype, need))
        quiz["total"] = len(quiz["questions"])
        return

    user = _conn.execute("SELECT * FROM users WHERE id=?",
                         (user_id,)).fetchone()
    attempts = 0
    while len(quiz["questions"]) < total and attempts < total * 3:
        need = total - len(quiz["questions"])
        exclude = {q.get("item_id") for q in quiz["questions"]
                   if q.get("item_id")}
        if qtype in sampler.VOCAB_TYPES:
            targets = sampler.pick_vocab_targets(_conn, user, qtype, need,
                                                 exclude_ids=exclude)
        else:
            targets = sampler.pick_grammar_targets(_conn, user, need)
        if not targets:
            break
        build = (_build_vocab_question if qtype in sampler.VOCAB_TYPES
                 else _build_grammar_question)
        results = await asyncio.gather(
            *[build(t, qtype) for t in targets], return_exceptions=True)
        for res in results:
            attempts += 1
            if isinstance(res, dict):
                quiz["questions"].append(res)
            else:
                quiz["failed"] += 1
    quiz["total"] = len(quiz["questions"])   # settle even if some failed


# ---------------------------------------------------------------- views

def public_questions(quiz: dict) -> list[dict]:
    """What the frontend may see before submit — no answers, no explanations."""
    out = []
    for i, q in enumerate(quiz["questions"]):
        pub = {"q_index": i, "question_type": q["question_type"],
               "sentence": q["sentence"], "markable": q["markable"]}
        if "options" in q:
            pub["options"] = q["options"]
            if q["question_type"] in ("cloze", "synonym"):
                pub["options_markable"] = [
                    markable.find_markable(o) for o in q["options"]]
        if q["question_type"] == "synonym":
            pub["word"] = q["word"]
        if q["question_type"] == "written_expression":
            pub["segment_offsets"] = q["segment_offsets"]
        out.append(pub)
    return out


# ---------------------------------------------------------------- submit

def submit(quiz_id: str, answers: list[dict],
           marked_item_ids: list[int]) -> dict:
    quiz = store.get(quiz_id)
    if quiz is None:
        raise KeyError("quiz not found or expired")
    if quiz["submitted"]:
        raise ValueError("quiz already submitted")
    quiz["submitted"] = True

    user = _conn.execute("SELECT * FROM users WHERE id=?",
                         (quiz["user_id"],)).fetchone()
    user_rating = user["rating"]
    answer_by_index = {a["q_index"]: a for a in answers}

    scores, expecteds, results = [], [], []
    for i, q in enumerate(quiz["questions"]):
        ans = answer_by_index.get(i, {})
        letter = (ans.get("answer") or "E").strip().upper()
        score = grader.grade(q, letter)
        e_i = rating.expected(user_rating, q["item_rating"],
                              q["question_type"])
        marked = bool(ans.get("marked_unfamiliar")) or letter == grader.IDK
        scores.append(score)
        expecteds.append(e_i)

        _conn.execute(
            """INSERT INTO reviews (user_id, item_id, sense_index,
                 grammar_point_id, question_type, question_payload,
                 user_answer, score, marked_unfamiliar, answered_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (quiz["user_id"], q.get("item_id"), q.get("sense_index"),
             q.get("grammar_point_id"), q["question_type"],
             json.dumps(q, ensure_ascii=False), letter, score,
             int(marked), db.now_iso()))
        state.apply_review(
            _conn, quiz["user_id"],
            item_id=q.get("item_id"),
            grammar_point_id=q.get("grammar_point_id"),
            score=score, marked=marked,
            rating_user=user_rating, rating_item=q["item_rating"],
            question_type=q["question_type"])

        results.append({
            "q_index": i, "question_type": q["question_type"],
            "sentence": q["sentence"],
            "options": q.get("options"),
            "segment_offsets": q.get("segment_offsets"),
            "corrected_segment": q.get("corrected_segment"),
            "word": q.get("word"), "gloss": q.get("gloss"),
            "grammar_point": q.get("grammar_point"),
            "your_answer": letter,
            "correct_answer": LETTERS[q["answer_index"]],
            "correct": score >= 0.5,
            "explanation": q["explanation"],
        })

    for item_id in marked_item_ids:
        row = _conn.execute("SELECT rating FROM vocabulary WHERE id=?",
                            (item_id,)).fetchone()
        if row:
            state.mark_word(_conn, quiz["user_id"], item_id, True,
                            user_rating, row["rating"])

    delta = rating.quiz_delta(scores, expecteds, user["exams_done"])
    new_rating = rating.clamp_rating(user_rating + delta)
    _conn.execute(
        "UPDATE users SET rating=?, exams_done=exams_done+1 WHERE id=?",
        (new_rating, quiz["user_id"]))
    _conn.execute(
        "INSERT INTO rating_history (user_id, rating, delta, recorded_at)"
        " VALUES (?,?,?,?)",
        (quiz["user_id"], new_rating, delta, db.now_iso()))
    _conn.commit()

    return {
        "score": sum(1 for s in scores if s >= 0.5),
        "total": len(scores),
        "rating": {
            "before": round(user_rating), "after": round(new_rating),
            "delta": round(new_rating - user_rating),
            "rank": rating.rank_title(new_rating),
            "estimated_toefl": rating.toefl_estimate(new_rating),
        },
        "questions": results,
    }


def abandon_to_bank(quiz_id: str) -> int:
    """Persist generated-but-unanswered questions for reuse (API quota)."""
    quiz = store.get(quiz_id)
    if quiz is None or quiz["submitted"] or not quiz["questions"]:
        return 0
    count = len(quiz["questions"])
    bank_put(quiz["user_id"], quiz["question_type"], quiz["questions"])
    quiz["questions"] = []
    quiz["submitted"] = True
    return count
