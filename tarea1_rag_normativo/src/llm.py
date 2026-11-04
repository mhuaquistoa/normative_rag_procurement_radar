"""Generation model client (DeepSeek, OpenAI-compatible API). Every call is logged with its cost.

Errors are raised to the caller (the engine turns them into result["error"]); they are never
returned as if they were an answer.
"""
import json
import os
import time

from openai import OpenAI

from config import cfg
from costs import log_call

_CLIENT = None


def client() -> OpenAI:
    global _CLIENT
    if _CLIENT is None:
        c = cfg()["llm"]
        key = os.environ.get(c["api_key_env"], "").strip()
        if not key:
            raise RuntimeError(f"{c['api_key_env']} is missing in .env")
        _CLIENT = OpenAI(api_key=key, base_url=c["base_url"], timeout=c["timeout_s"])
    return _CLIENT


def chat_json(system: str, user: str) -> dict:
    """One JSON-mode call. Returns {"data", "tokens_in", "tokens_cached", "tokens_out", "cost_usd",
    "price_window", "latency_s", "model"}."""
    c = cfg()["llm"]
    t0 = time.perf_counter()
    try:
        r = client().chat.completions.create(
            model=c["model"], max_tokens=c["max_tokens"], temperature=c["temperature"],
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": c["thinking"]}},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    except Exception as e:
        log_call("generation", c["model"], 0, 0, time.perf_counter() - t0, ok=False, note=f"{type(e).__name__}: {e}"[:200])
        raise
    latency = time.perf_counter() - t0
    u = r.usage
    cached = getattr(u, "prompt_cache_hit_tokens", 0) or 0
    content = (r.choices[0].message.content or "").strip()
    if not content:  # JSON mode can return blanks when the model fails to produce JSON
        log_call("generation", c["model"], u.prompt_tokens, u.completion_tokens, latency, ok=False, note="empty JSON content")
        raise ValueError("the model returned empty content")
    cost, window = log_call("generation", c["model"], u.prompt_tokens, u.completion_tokens, latency, ok=True,
                            tokens_cached=cached)
    return {"data": json.loads(content), "tokens_in": u.prompt_tokens, "tokens_cached": cached,
            "tokens_out": u.completion_tokens, "cost_usd": cost, "latency_s": round(latency, 3),
            "price_window": window, "model": r.model}
