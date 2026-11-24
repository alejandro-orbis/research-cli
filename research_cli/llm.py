"""Calls to the language model: retries, model fallback and reply parsing."""

import json
import re
import sys
import time

from google.genai import errors

from .config import MODELS


def is_timeout(error: Exception) -> bool:
    """True for network timeouts, whatever HTTP library raised them."""
    return isinstance(error, TimeoutError) or "timeout" in type(error).__name__.lower()


# What ask_llm() learns during a run, so later calls don't repeat failed attempts.
_exhausted: set[str] = set()   # models that ran out of quota in this run
_preferred: str | None = None  # last model that answered successfully


def model_order() -> list[str]:
    """Models to try, in order: last successful one first, exhausted ones skipped."""
    order = [m for m in MODELS if m not in _exhausted]
    if _preferred in order:
        order.remove(_preferred)
        order.insert(0, _preferred)
    return order


def is_quota_error(error: Exception) -> bool:
    """True when the API says we ran out of quota (HTTP 429) for this model."""
    return getattr(error, "code", None) == 429


def ask_llm(client, prompt: str, retries: int = 3) -> str:
    """Call the LLM with retries and model fallback.

    - 5xx server errors: retry the same model with backoff.
    - Timeouts: switch straight to the next model (retrying would likely be just as slow).
    - Quota exhausted (429): switch to the next model (quotas are per model).
    - Anything else (bad key, unknown model...): fail immediately.

    Within a run it remembers which model worked last and which ran out of quota.
    """
    global _preferred
    for model in model_order():
        for attempt in range(retries):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                _preferred = model
                return (response.text or "").strip()
            except errors.ServerError:
                if attempt < retries - 1:
                    wait = 5 * 2 ** attempt  # 5s, 10s
                    print(f"   ⏳ {model} is busy, retrying in {wait}s...")
                    time.sleep(wait)
            except Exception as e:
                if is_quota_error(e):
                    print(f"   🚫 {model} is out of quota for today.")
                    _exhausted.add(model)
                    break
                if is_timeout(e):
                    print(f"   ⌛ {model} took too long to respond.")
                    break
                raise
        print(f"   ↪️  {model} unavailable, switching to the next model...")
    sys.exit("All Gemini models are unavailable right now. Try again later.")


def parse_json_list(text: str) -> list[str]:
    """Extract a JSON array of strings from an LLM reply. Returns [] if it isn't one."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]
