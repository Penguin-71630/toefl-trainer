"""FastAPI endpoints — thin HTTP layer over orchestrator (§9)."""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend import config, db, llm, orchestrator, rating, state


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.ensure_db()
    provider = llm.build_provider()
    orchestrator.setup(conn, provider)
    app.state.conn = conn
    yield
    conn.close()


app = FastAPI(title="TOEFL Quiz System", lifespan=lifespan)

QUESTION_TYPES = {"cloze", "synonym", "structure", "written_expression"}


class UserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=40)


class QuizRequest(BaseModel):
    user_id: int
    question_type: str
    n: int = config.QUIZ_SIZE


class Answer(BaseModel):
    q_index: int
    answer: str = "E"
    marked_unfamiliar: bool = False


class SubmitRequest(BaseModel):
    answers: list[Answer]
    marked_item_ids: list[int] = []


@app.get("/health")
def health():
    conn = app.state.conn
    return {
        "vocabulary": conn.execute(
            "SELECT COUNT(*) AS n FROM vocabulary").fetchone()["n"],
        "grammar_points": conn.execute(
            "SELECT COUNT(*) AS n FROM grammar_points").fetchone()["n"],
    }


@app.post("/users")
def create_user(req: UserRequest):
    conn = app.state.conn
    row = conn.execute("SELECT * FROM users WHERE username=?",
                       (req.username,)).fetchone()
    if row:
        return {"user_id": row["id"], "is_new": False,
                "rating": round(row["rating"]),
                "rank": rating.rank_title(row["rating"])}
    cur = conn.execute(
        "INSERT INTO users (username, rating, created_at) VALUES (?,?,?)",
        (req.username, config.RATING_INIT, db.now_iso()))
    conn.commit()
    return {"user_id": cur.lastrowid, "is_new": True,
            "rating": config.RATING_INIT,
            "rank": rating.rank_title(config.RATING_INIT)}


@app.post("/quizzes")
async def create_quiz(req: QuizRequest):
    if req.question_type not in QUESTION_TYPES:
        raise HTTPException(422, f"unknown question type: {req.question_type}")
    conn = app.state.conn
    if not conn.execute("SELECT 1 FROM users WHERE id=?",
                        (req.user_id,)).fetchone():
        raise HTTPException(404, "user not found")
    quiz_id = orchestrator.store.create(req.user_id, req.question_type, req.n)
    asyncio.create_task(orchestrator.generate_quiz(quiz_id))
    return {"quiz_id": quiz_id}


@app.get("/quizzes/{quiz_id}/status")
def quiz_status(quiz_id: str):
    quiz = orchestrator.store.get(quiz_id)
    if quiz is None:
        raise HTTPException(404, "quiz not found or expired")
    return {"ready": len(quiz["questions"]), "total": quiz["total"],
            "failed": quiz["failed"]}


@app.get("/quizzes/{quiz_id}")
def get_quiz(quiz_id: str):
    quiz = orchestrator.store.get(quiz_id)
    if quiz is None:
        raise HTTPException(404, "quiz not found or expired")
    if len(quiz["questions"]) < quiz["total"]:
        raise HTTPException(409, "quiz still generating")
    return {"quiz_id": quiz_id,
            "question_type": quiz["question_type"],
            "questions": orchestrator.public_questions(quiz)}


@app.post("/quizzes/{quiz_id}/submit")
def submit_quiz(quiz_id: str, req: SubmitRequest):
    try:
        return orchestrator.submit(
            quiz_id, [a.model_dump() for a in req.answers],
            req.marked_item_ids)
    except KeyError as exc:
        raise HTTPException(404, "quiz not found or expired") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/quizzes/{quiz_id}/abandon")
def abandon_quiz(quiz_id: str):
    return {"banked": orchestrator.abandon_to_bank(quiz_id)}


@app.get("/stats")
def stats(user_id: int):
    conn = app.state.conn
    user = conn.execute("SELECT * FROM users WHERE id=?",
                        (user_id,)).fetchone()
    if user is None:
        raise HTTPException(404, "user not found")
    by_type = {row["question_type"]: row["n"] for row in conn.execute(
        "SELECT question_type, COUNT(*) AS n FROM reviews "
        "WHERE user_id=? GROUP BY question_type", (user_id,))}
    accuracy = conn.execute(
        "SELECT AVG(score) AS acc, COUNT(*) AS n FROM reviews WHERE user_id=?",
        (user_id,)).fetchone()
    history = [{"rating": round(r["rating"]), "delta": round(r["delta"]),
                "recorded_at": r["recorded_at"]}
               for r in conn.execute(
                   "SELECT * FROM rating_history WHERE user_id=? "
                   "ORDER BY recorded_at", (user_id,))]
    weak = [{"word": r["word"], "proficiency": round(r["proficiency"], 2)}
            for r in conn.execute(
                """SELECT v.word, ui.proficiency FROM user_items ui
                   JOIN vocabulary v ON v.id = ui.item_id
                   WHERE ui.user_id=? ORDER BY ui.proficiency LIMIT 10""",
                (user_id,))]
    return {
        "username": user["username"],
        "rating": round(user["rating"]),
        "rank": rating.rank_title(user["rating"]),
        "estimated_toefl": rating.toefl_estimate(user["rating"]),
        "exams_done": user["exams_done"],
        "answered_by_type": {t: by_type.get(t, 0)
                             for t in sorted(QUESTION_TYPES)},
        "accuracy": round(accuracy["acc"], 3) if accuracy["n"] else None,
        "total_answered": accuracy["n"],
        "rating_history": history,
        "weakest_words": weak,
    }


@app.get("/reviews")
def reviews(user_id: int, only_wrong: bool = False, limit: int = 100):
    conn = app.state.conn
    sql = "SELECT * FROM reviews WHERE user_id=?"
    if only_wrong:
        sql += " AND score < 0.5"
    sql += " ORDER BY answered_at DESC LIMIT ?"
    out = []
    for row in conn.execute(sql, (user_id, limit)):
        payload = json.loads(row["question_payload"])
        out.append({
            "review_id": row["id"],
            "question_type": row["question_type"],
            "sentence": payload.get("sentence"),
            "options": payload.get("options"),
            "word": payload.get("word"),
            "gloss": payload.get("gloss"),
            "grammar_point": payload.get("grammar_point"),
            "segment_offsets": payload.get("segment_offsets"),
            "your_answer": row["user_answer"],
            "correct_answer": "ABCDE"[payload["answer_index"]],
            "explanation": payload.get("explanation"),
            "answered_at": row["answered_at"],
        })
    return {"reviews": out}


@app.get("/heatmap")
def heatmap(user_id: int):
    conn = app.state.conn
    out = []
    for row in conn.execute(
            "SELECT * FROM user_items WHERE user_id=?", (user_id,)):
        out.append({
            "item_id": row["item_id"],
            "p_eff": round(state.effective_proficiency(
                row["proficiency"], row["streak"], row["last_seen_at"]), 3),
            "unfamiliar_score": row["unfamiliar_score"],
        })
    return {"items": out}
