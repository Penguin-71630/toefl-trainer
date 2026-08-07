"""SQLite connection, DDL, and seeding from data/*.json (§2)."""

import json
import sqlite3
from datetime import datetime, timezone

from backend import config

DDL = """
CREATE TABLE IF NOT EXISTS vocabulary (
    id             INTEGER PRIMARY KEY,
    word           TEXT    NOT NULL,
    difficulty     REAL    NOT NULL,
    rating         REAL    NOT NULL,
    word_family_id INTEGER,
    phrase_head    TEXT,
    phrase_particles TEXT,
    sources        TEXT NOT NULL,
    exam_tags      TEXT NOT NULL,
    senses         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vocab_rating ON vocabulary(rating);

CREATE TABLE IF NOT EXISTS grammar_points (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    category       TEXT NOT NULL,
    description    TEXT NOT NULL,
    example        TEXT NOT NULL,
    error_patterns TEXT NOT NULL,
    exam_tags      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL UNIQUE,
    rating     REAL    NOT NULL DEFAULT 1400,
    exams_done INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rating_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    rating      REAL    NOT NULL,
    delta       REAL    NOT NULL,
    recorded_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS user_items (
    user_id          INTEGER NOT NULL,
    item_id          INTEGER NOT NULL,
    correct_count    INTEGER NOT NULL DEFAULT 0,
    wrong_count      INTEGER NOT NULL DEFAULT 0,
    proficiency      REAL    NOT NULL,
    streak           INTEGER NOT NULL DEFAULT 0,
    unfamiliar_score INTEGER NOT NULL DEFAULT 0,
    last_seen_at     TEXT,
    PRIMARY KEY (user_id, item_id)
);

CREATE TABLE IF NOT EXISTS user_grammar_points (
    user_id          INTEGER NOT NULL,
    grammar_point_id INTEGER NOT NULL,
    correct_count    INTEGER NOT NULL DEFAULT 0,
    wrong_count      INTEGER NOT NULL DEFAULT 0,
    proficiency      REAL    NOT NULL,
    streak           INTEGER NOT NULL DEFAULT 0,
    unfamiliar_score INTEGER NOT NULL DEFAULT 0,
    last_seen_at     TEXT,
    PRIMARY KEY (user_id, grammar_point_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    item_id          INTEGER,
    sense_index      INTEGER,
    grammar_point_id INTEGER,
    question_type    TEXT NOT NULL,
    question_payload TEXT NOT NULL,
    user_answer      TEXT NOT NULL,
    score            REAL NOT NULL,
    grader_payload   TEXT,
    marked_unfamiliar INTEGER NOT NULL DEFAULT 0,
    answered_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews(user_id, answered_at);
CREATE INDEX IF NOT EXISTS idx_reviews_item ON reviews(item_id);

CREATE TABLE IF NOT EXISTS question_bank (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    question_type TEXT NOT NULL,
    payload       TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path=None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)


def is_seeded(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) AS n FROM vocabulary").fetchone()
    return row["n"] > 0


def seed(conn: sqlite3.Connection) -> None:
    """Load vocabulary/grammar JSON; compute static Elo rating per word
    from the empirical difficulty percentile (§3, frozen at seed time)."""
    vocab = json.loads((config.DATA_DIR / "vocabulary.json").read_text())
    grammar = json.loads((config.DATA_DIR / "grammar.json").read_text())

    difficulties = sorted(it["difficulty"] for it in vocab)
    n = len(difficulties)

    def percentile(d: float) -> float:
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            if difficulties[mid] < d:
                lo = mid + 1
            else:
                hi = mid
        return lo / n

    rows = []
    for it in vocab:
        pct = percentile(it["difficulty"])
        word_rating = config.WORD_RATING_MIN + config.WORD_RATING_SPAN * pct
        phrase = it.get("phrase_attribute") or {}
        rows.append((
            it["id"], it["word"], it["difficulty"], round(word_rating, 1),
            it.get("word_family_id"),
            phrase.get("head"),
            json.dumps(phrase.get("particles"), ensure_ascii=False)
            if phrase else None,
            json.dumps(it["sources"], ensure_ascii=False),
            json.dumps(it["exam_tags"], ensure_ascii=False),
            json.dumps(it["senses"], ensure_ascii=False),
        ))
    conn.executemany(
        "INSERT INTO vocabulary VALUES (?,?,?,?,?,?,?,?,?,?)", rows)

    conn.executemany(
        "INSERT INTO grammar_points VALUES (?,?,?,?,?,?,?)",
        [(g["id"], g["name"], g["category"], g["description"],
          json.dumps(g["example"], ensure_ascii=False),
          json.dumps(g["error_patterns"], ensure_ascii=False),
          json.dumps(g["exam_tags"], ensure_ascii=False))
         for g in grammar])
    conn.commit()


def ensure_db(path=None) -> sqlite3.Connection:
    conn = connect(path)
    init_schema(conn)
    if not is_seeded(conn):
        seed(conn)
    return conn
