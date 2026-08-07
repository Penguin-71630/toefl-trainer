"""Async HTTP client for the local backend."""

import os

import httpx

BASE_URL = os.environ.get("TOEFL_API", "http://127.0.0.1:8000")

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=BASE_URL, timeout=30)
    return _client


async def health() -> dict:
    resp = await client().get("/health")
    resp.raise_for_status()
    return resp.json()


async def login(username: str) -> dict:
    resp = await client().post("/users", json={"username": username})
    resp.raise_for_status()
    return resp.json()


async def start_quiz(user_id: int, question_type: str, n: int = 10) -> str:
    resp = await client().post("/quizzes", json={
        "user_id": user_id, "question_type": question_type, "n": n})
    resp.raise_for_status()
    return resp.json()["quiz_id"]


async def quiz_status(quiz_id: str) -> dict:
    resp = await client().get(f"/quizzes/{quiz_id}/status")
    resp.raise_for_status()
    return resp.json()


async def get_quiz(quiz_id: str) -> dict:
    resp = await client().get(f"/quizzes/{quiz_id}")
    resp.raise_for_status()
    return resp.json()


async def submit_quiz(quiz_id: str, answers: list[dict],
                      marked_item_ids: list[int]) -> dict:
    resp = await client().post(f"/quizzes/{quiz_id}/submit", json={
        "answers": answers, "marked_item_ids": marked_item_ids})
    resp.raise_for_status()
    return resp.json()


async def abandon_quiz(quiz_id: str) -> dict:
    resp = await client().post(f"/quizzes/{quiz_id}/abandon")
    resp.raise_for_status()
    return resp.json()


async def stats(user_id: int) -> dict:
    resp = await client().get("/stats", params={"user_id": user_id})
    resp.raise_for_status()
    return resp.json()


async def reviews(user_id: int, only_wrong: bool = True,
                  limit: int = 50) -> dict:
    resp = await client().get("/reviews", params={
        "user_id": user_id, "only_wrong": only_wrong, "limit": limit})
    resp.raise_for_status()
    return resp.json()
