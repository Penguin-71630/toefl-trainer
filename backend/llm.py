"""LLM gateway: provider switch, fixture playback, throttling, retries (§8)."""

import asyncio
import json
import os
import random
import time

from openai import AsyncOpenAI

from backend import config

PROVIDERS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        # free tier: flash-lite has a much higher daily quota than flash
        "default_model": "gemini-2.5-flash-lite",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
    },
}


class FixtureProvider:
    """Replays pre-recorded, fully validated question payloads when no API
    key is configured. Not a chat provider: the orchestrator detects it and
    skips generation entirely."""

    name = "fixture"
    model = "fixture"

    def __init__(self):
        self._store: dict[str, list[dict]] = {}
        if config.FIXTURES_PATH.exists():
            self._store = json.loads(config.FIXTURES_PATH.read_text())
        self._cursors: dict[str, int] = {}

    def take_questions(self, question_type: str, n: int) -> list[dict]:
        pool = self._store.get(question_type, [])
        if not pool:
            return []
        start = self._cursors.get(question_type,
                                  random.randrange(len(pool)))
        out = [dict(pool[(start + i) % len(pool)]) for i in range(n)]
        self._cursors[question_type] = (start + n) % len(pool)
        return out

    async def complete_json(self, question_type: str, system: str,
                            user: str) -> dict:
        raise RuntimeError("fixture provider does not generate")


def _extract_json(content: str) -> dict:
    """Parse a JSON object from a completion, tolerating markdown fences
    and surrounding prose (models without JSON mode, e.g. Gemma)."""
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(content[start:end + 1])


class OpenAICompatProvider:
    def __init__(self, name: str, api_key: str, model: str):
        self.name = name
        self.model = model
        # Gemma models on the Gemini API don't support JSON mode
        self.supports_json_mode = not model.startswith("gemma")
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=PROVIDERS[name]["base_url"])
        self._semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY)
        self._request_times: list[float] = []
        self._pace_lock = asyncio.Lock()

    async def _pace(self) -> None:
        """Keep under MAX_RPM requests per minute (free-tier limits)."""
        async with self._pace_lock:
            now = time.monotonic()
            self._request_times = [t for t in self._request_times
                                   if now - t < 60]
            if len(self._request_times) >= config.MAX_RPM:
                wait = 60 - (now - self._request_times[0]) + 0.1
                await asyncio.sleep(wait)
            self._request_times.append(time.monotonic())

    async def complete_json(self, question_type: str, system: str,
                            user: str) -> dict:
        last_error: Exception | None = None
        for attempt in range(config.MAX_RETRIES + 1):
            try:
                async with self._semaphore:
                    await self._pace()
                    kwargs = {}
                    if self.supports_json_mode:
                        kwargs["response_format"] = {"type": "json_object"}
                    else:
                        user = (user + "\n\nRespond with a single JSON "
                                "object only — no markdown, no commentary.")
                    resp = await self._client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "system", "content": system},
                                  {"role": "user", "content": user}],
                        temperature=0.9,
                        **kwargs,
                    )
                return _extract_json(resp.choices[0].message.content)
            except Exception as exc:  # noqa: BLE001 - retry then surface
                last_error = exc
                backoff = 2 ** attempt + random.random()
                if "429" in str(exc):
                    backoff = 20 * (attempt + 1)
                await asyncio.sleep(backoff)
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
