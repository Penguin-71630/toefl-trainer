"""One-time setup: create + seed the SQLite database, create .env.

Usage:  python init.py
"""

import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def main() -> None:
    env = BASE / ".env"
    if not env.exists():
        shutil.copy(BASE / ".env.example", env)
        print("Created .env — fill in LLM_API_KEY to use a real LLM "
              "(otherwise fixture questions are used).")

    from backend import db
    conn = db.ensure_db()
    vocab = conn.execute("SELECT COUNT(*) AS n FROM vocabulary").fetchone()["n"]
    grammar = conn.execute(
        "SELECT COUNT(*) AS n FROM grammar_points").fetchone()["n"]
    conn.close()
    print(f"Database ready: {vocab} words, {grammar} grammar points.")
    print("""1. Open the file '.env' and modify LLM_PROVIDER, LLM_API_KEY, LLM_MODEL
       2. Start the app with:  python run.py
    """)


if __name__ == "__main__":
    main()
