"""All tunable coefficients in one place. See docs/mvp-architecture.md."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "app.db"
FIXTURES_PATH = DATA_DIR / "fixtures" / "questions.json"

# --- Elo (§3) ---
RATING_INIT = 1400
RATING_CAP = 2500
RATING_FLOOR = 0
WORD_RATING_MIN = 1100
WORD_RATING_SPAN = 1150            # top of deck = 1100 + 1150 = 2250
GRAMMAR_DEFAULT_RATING = 1800
GUESS_FLOOR = 0.25                 # four-choice guessing floor
TOEFL_ANCHOR_SCORE = 627
TOEFL_ANCHOR_RATING = 2100
TOEFL_PER_RATING = 6               # 1 TOEFL point = 6 rating
K_FACTORS = [(10, 12), (40, 8), (None, 4)]   # (exams_done <, K)

RANKS = [
    (1200, "Newbie"),
    (1400, "Pupil"),
    (1600, "Specialist"),
    (1900, "Expert"),
    (2100, "Candidate Master"),
    (2400, "Master"),
    (2700, "Grandmaster"),
    (None, "Native Speaker"),
]

# --- proficiency (§4) ---
ALPHA_UP = 0.3
ALPHA_DOWN = 0.5
GRAMMAR_P_INIT = 0.4
HALF_LIFE_BASE = 5                 # days
HALF_LIFE_GROWTH = 1.8
HALF_LIFE_MAX = 180
UNFAMILIAR_MARK_BONUS = 3
UNFAMILIAR_DECAY = 1

# --- sampler (§5) ---
POOL_RATING_WINDOW = 350
W_LEVEL_SIGMA = 175
W_RECENCY_DAYS = 14
NEW_ITEM_QUOTA = 3
TEMPERATURE = 1.0
QUIZ_SIZE = 10

# --- distractor (§6) ---
DISTRACTOR_DIFFICULTY_WINDOW = 1.5
FAMILY_SAME_POS_WEIGHT = 3
SIMILARITY_WEIGHT = 5

# --- quiz store (§9) ---
QUIZ_TTL_SECONDS = 2 * 3600

# --- markable words (§11) ---
MARKABLE_MIN_DIFFICULTY = 10.0

# --- llm (§8) ---
MAX_CONCURRENCY = 4
MAX_RPM = 12
MAX_RETRIES = 2
GENERATION_ATTEMPTS = 2            # per question, before fallback
