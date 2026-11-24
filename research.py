#!/usr/bin/env python3
"""
research - a personal research assistant for the terminal.

Pipeline:
  1. Plan:       the LLM splits your question into focused web searches.
  2. Search:     Tavily runs each search and returns the page content.
  3. Synthesize: the LLM writes a report that cites sources as [n].
  4. Save:       the report is stored as Markdown in ./reports/

Usage:
  python research.py "What are the trade-offs of n8n vs Make for enterprises?"
  python research.py "question" --lang es
  python research.py "question" --searches 5 --results 4 --no-save
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

try:
    from google import genai
    from google.genai import errors
    from tavily import TavilyClient
except ImportError:
    sys.exit("Missing dependencies. Run: pip install -r requirements.txt")

try:  # optional: load variables from a .env file if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

MODELS = [m.strip() for m in os.getenv(
    "GEMINI_MODEL", "gemini-3.5-flash,gemini-3.7-flash,gemini-3.5-flash-lite"
).split(",") if m.strip()]
MAX_CHARS_PER_SOURCE = 4000  # truncate each page to keep token usage under control
LANGUAGES = {"en": "English", "es": "Spanish"}
SOURCES_HEADING = {"en": "Sources", "es": "Fuentes"}


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        sys.exit(f"Missing environment variable: {name} (see .env.example)")
    return value


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


def merge_sources(existing: list[dict], new: list[dict]) -> list[dict]:
    """Append new sources whose URL isn't already present, keeping existing numbering."""
    seen = {s["url"] for s in existing}
    return existing + [s for s in new if s["url"] not in seen]


def parse_domains(value: str | None) -> list[str]:
    """Turn 'youtube.com, Reddit.com' into ['youtube.com', 'reddit.com']."""
    if not value:
        return []
    return [d.strip().lower() for d in value.split(",") if d.strip()]


def search_one(tavily, query: str, per_query: int, filters: dict):
    """Run a single search. Returns the result, or the exception if it failed."""
    try:
        return tavily.search(
            query, max_results=per_query, include_raw_content=True, **filters
        )
    except Exception as e:  # one failed search shouldn't stop the rest
        return e


def search_sources(
    tavily,
    queries: list[str],
    per_query: int,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[dict]:
    """Step 2: run all queries in parallel and collect unique sources."""
    filters = {}
    if include:
        filters["include_domains"] = include
    if exclude:
        filters["exclude_domains"] = exclude

    with ThreadPoolExecutor(max_workers=max(1, len(queries))) as pool:
        # map() returns results in the same order as `queries`,
        # so source numbering stays stable regardless of which search finishes first.
        results = list(pool.map(lambda q: search_one(tavily, q, per_query, filters), queries))

    sources, seen = [], set()
    for query, result in zip(queries, results):
        print(f"  🔎 {query}")
        if isinstance(result, Exception):
            print(f"     ⚠️  failed: {result}")
            continue
        for item in result.get("results", []):
            url = item.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            content = item.get("raw_content") or item.get("content") or ""
            sources.append({
                "title": item.get("title") or url,
                "url": url,
                "content": content[:MAX_CHARS_PER_SOURCE],
            })
    return sources


def cited_numbers(text: str) -> set[int]:
    """Return the source numbers cited in the text, e.g. [2], [1, 3], [4-6]."""
    cited = set()
    for group in re.findall(r"\[([\d,\s\-–]+)\]", text):
        for part in group.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part or "–" in part:  # ranges like [4-6]
                start, end = re.split(r"[-–]", part, maxsplit=1)
                if start.strip().isdigit() and end.strip().isdigit():
                    cited.update(range(int(start), int(end) + 1))
            elif part.isdigit():
                cited.add(int(part))
    return cited


def synthesize(client, question: str, sources: list[dict], lang: str) -> str:
    """Step 3: write the report, citing sources by number."""
    context = "\n\n".join(
        f"[{i}] {s['title']} ({s['url']})\n{s['content']}"
        for i, s in enumerate(sources, 1)
    )
    prompt = (
        "You are a rigorous research assistant. Answer the question using ONLY "
        "the sources provided.\n"
        f"- Write in {LANGUAGES[lang]}, in Markdown: start with a 2-3 sentence "
        "summary, then sections with the details.\n"
        "- Cite every claim with the source number in brackets, e.g. [2].\n"
        "- If sources contradict each other, say so. If something isn't covered "
        "by the sources, state that there isn't enough information; never make "
        "things up.\n"
        "- Flag sources with a commercial interest in the topic (vendors about their "
        "own product, or companies selling related services) as potentially biased, "
        "and prefer independent sources when they disagree.\n\n"
        f"Question: {question}\n\nSources:\n{context}"
    )
    report = ask_llm(client, prompt)
    cited = cited_numbers(report)
    source_list = "\n".join(
        f"- [{i}] [{s['title']}]({s['url']})"
        for i, s in enumerate(sources, 1)
        if i in cited or not cited  # if no citations are detected, list them all
    )
    return f"# {question}\n\n{report}\n\n## {SOURCES_HEADING[lang]}\n\n{source_list}\n"


def make_slug(question: str) -> str:
    """Turn a question into a safe, accent-free file name."""
    ascii_text = unicodedata.normalize("NFKD", question).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower())[:50].strip("-") or "report"


def save_report(question: str, report: str) -> Path:
    """Step 4: store the report as a timestamped Markdown file."""
    folder = Path("reports")
    folder.mkdir(exist_ok=True)
    slug = make_slug(question)
    path = folder / f"{datetime.now():%Y%m%d-%H%M}-{slug}.md"
    path.write_text(report, encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="Personal research assistant for the terminal")
    parser.add_argument("question", help="what you want to research (in quotes)")
    parser.add_argument("--lang", choices=LANGUAGES, default="en", help="report language (default: en)")
    parser.add_argument("--searches", type=int, default=3, help="number of web searches (default: 3)")
    parser.add_argument("--results", type=int, default=3, help="results per search (default: 3)")
    parser.add_argument("--no-save", action="store_true", help="print only, don't save a .md file")
    parser.add_argument("--exclude", help="domains to skip, comma-separated (e.g. youtube.com,reddit.com)")
    parser.add_argument("--include", help="only search these domains, comma-separated")
    parser.add_argument("--deep", action="store_true",
                        help="review the draft, search for missing information and rewrite")
    args = parser.parse_args()

    client = genai.Client(
        api_key=require_env("GEMINI_API_KEY"),
        http_options={"timeout": 120_000},  # 120 s per request (milliseconds)
    )
    tavily = TavilyClient(api_key=require_env("TAVILY_API_KEY"))

    print("🧠 Planning searches...")
    queries = plan_searches(client, args.question, args.searches)

    print("🌐 Searching sources...")
    started = time.perf_counter()
    exclude = parse_domains(args.exclude or os.getenv("EXCLUDE_DOMAINS"))
    include = parse_domains(args.include)
    if exclude:
        print(f"   excluding: {', '.join(exclude)}")
    if include:
        print(f"   only: {', '.join(include)}")
    sources = search_sources(tavily, queries, args.results, include=include, exclude=exclude)
    elapsed = time.perf_counter() - started
    if not sources:
        sys.exit("No sources found. Try rephrasing the question.")
    print(f"   {len(sources)} unique sources in {elapsed:.1f}s")

    if args.deep:
        print("✍️  Writing draft...")
        draft = synthesize(client, args.question, sources, args.lang)

        print("🔍 Looking for gaps...")
        gaps = find_gaps(client, args.question, draft, args.searches)
        if gaps:
            new_sources = search_sources(
                tavily, gaps, args.results, include=include, exclude=exclude
            )
            before = len(sources)
            sources = merge_sources(sources, new_sources)
            print(f"   {len(sources) - before} new sources")
        else:
            print("   no important gaps found")

    print("✍️  Writing report...\n")
    report = synthesize(client, args.question, sources, args.lang)
    print(report)

    if not args.no_save:
        print(f"💾 Saved to {save_report(args.question, report)}")


if __name__ == "__main__":
    main()
