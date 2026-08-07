"""LLM gateway: provider switch, fixture playback, throttling, retries (§8)."""

import asyncio
import json
import os
import random

from openai import AsyncOpenAI

from backend import config

PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.0-flash",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
    },
}


class FixtureProvider:
    """Replays pre-recorded questions when no API key is configured."""

    name = "fixture"

    def __init__(self):
        self._store: dict[str, list[dict]] = {}
        if config.FIXTURES_PATH.exists():
            self._store = json.loads(config.FIXTURES_PATH.read_text())
        self._cursors: dict[str, int] = {}

    async def complete_json(self, question_type: str, system: str,
                            user: str) -> dict:
        pool = self._store.get(question_type, [])
        if not pool:
            raise RuntimeError(
                f"no fixtures for question type '{question_type}' "
                f"(and no LLM API key configured)")
        i = self._cursors.get(question_type, random.randrange(len(pool)))
        self._cursors[question_type] = (i + 1) % len(pool)
        return dict(pool[i])

    @property
    def model(self) -> str:
        return "fixture"


class OpenAICompatProvider:
    def __init__(self, name: str, api_key: str, model: str):
        self.name = name
        self.model = model
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=PROVIDERS[name]["base_url"])
        self._semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY)

    async def complete_json(self, question_type: str, system: str,
                            user: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(config.MAX_RETRIES + 1):
            try:
                async with self._semaphore:
                    resp = await self._client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "system", "content": system},
                                  {"role": "user", "content": user}],
                        response_format={"type": "json_object"},
                        temperature=0.9,
                    )
                return json.loads(resp.choices[0].message.content)
            except Exception as exc:  # noqa: BLE001 - retry then surface
                last_error = exc
                await asyncio.sleep(2 ** attempt + random.random())
        raise RuntimeError(f"LLM call failed after retries: {last_error}")


def _guess_provider(api_key: str) -> str:
    if api_key.startswith("AIza"):
        return "gemini"
    if api_key.startswith("gsk_"):
        return "groq"
    return "gemini"


def build_provider():
    provider_name = os.environ.get("LLM_PROVIDER", "").strip().lower()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if provider_name == "mock" or not api_key:
        return FixtureProvider()
    if provider_name not in PROVIDERS:
        provider_name = _guess_provider(api_key)
    model = (os.environ.get("LLM_MODEL", "").strip()
             or PROVIDERS[provider_name]["default_model"])
    return OpenAICompatProvider(provider_name, api_key, model)
