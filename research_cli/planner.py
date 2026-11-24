"""Deciding what to search: the initial plan and, in deep mode, the gaps."""

from .llm import ask_llm, parse_json_list


def plan_searches(client, question: str, n: int) -> list[str]:
    """Step 1: turn the question into n focused web searches."""
    prompt = (
        f"Split this research question into {n} short, distinct web search "
        f"queries that together cover every aspect of it.\n"
        f"Return ONLY a JSON array of strings, with no extra text.\n\n"
        f"Question: {question}"
    )
    queries = parse_json_list(ask_llm(client, prompt))
    return queries[:n] or [question]  # fallback: search the question as-is


def find_gaps(client, question: str, draft: str, n: int) -> list[str]:
    """Deep mode: ask the LLM what the draft is missing, as new search queries."""
    prompt = (
        "You are reviewing a research report draft. Identify the most important "
        "aspects of the question that the draft does NOT answer well: missing "
        "information, claims backed by a single source, or points where sources "
        "disagree and more evidence is needed.\n"
        f"Return up to {n} short web search queries that would fill those gaps, as "
        "ONLY a JSON array of strings. If nothing important is missing, return [].\n\n"
        f"Question: {question}\n\nDraft:\n{draft}"
    )
    return parse_json_list(ask_llm(client, prompt))[:n]
