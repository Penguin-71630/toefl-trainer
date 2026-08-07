"""Generate data/fixtures/questions.json by running the REAL generation
pipeline (sampler → distractor → LLM → validator) with a live API key.
Fixtures are complete validated question payloads, replayed in mock mode.

Usage:  LLM_API_KEY=... python pipeline/make_fixtures.py [n_per_type]
"""

import asyncio
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from backend import config, db, llm, orchestrator  # noqa: E402

TYPES = ["cloze", "synonym", "structure", "written_expression"]


async def main(n: int) -> None:
    conn = db.ensure_db(":memory:")
    provider = llm.build_provider()
    if provider.name == "fixture":
        raise SystemExit("Set LLM_API_KEY — fixtures must come from a real LLM")
    orchestrator.setup(conn, provider)
    cur = conn.execute(
        "INSERT INTO users (username, rating, created_at) "
        "VALUES ('fixture', ?, ?)", (config.RATING_INIT, db.now_iso()))
    conn.commit()
    uid = cur.lastrowid

    store: dict[str, list[dict]] = {}
    for qtype in TYPES:
        quiz_id = orchestrator.store.create(uid, qtype, n)
        await orchestrator.generate_quiz(quiz_id)
        quiz = orchestrator.store.get(quiz_id)
        store[qtype] = quiz["questions"]
        print(f"{qtype}: {len(quiz['questions'])} generated, "
              f"{quiz['failed']} failed")

    config.FIXTURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.FIXTURES_PATH.write_text(
        json.dumps(store, ensure_ascii=False, indent=1))
    print(f"Wrote {config.FIXTURES_PATH}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 12))
