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


def ask_llm(client, prompt: str, retries: int = 3) -> str:
    """Call the LLM, retrying 5xx errors and falling back to the next model."""
    for model in MODELS:
        for attempt in range(retries):
            try:
                response = client.models.generate_content(model=model, contents=prompt)
                return (response.text or "").strip()
            except errors.ServerError:
                if attempt < retries - 1:
                    wait = 5 * 2 ** attempt  # 5s, 10s
                    print(f"   ⏳ {model} is busy, retrying in {wait}s...")
                    time.sleep(wait)
        print(f"   ↪️  {model} unavailable, switching to the next model...")
    sys.exit("All Gemini models are unavailable right now. Try again later.")


def plan_searches(client, question: str, n: int) -> list[str]:
    """Step 1: turn the question into n focused web searches."""
    prompt = (
        f"Split this research question into {n} short, distinct web search "
        f"queries that together cover every aspect of it.\n"
        f"Return ONLY a JSON array of strings, with no extra text.\n\n"
        f"Question: {question}"
    )
    text = ask_llm(client, prompt)
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        queries = json.loads(text)
        if isinstance(queries, list) and queries:
            return [str(q) for q in queries][:n]
    except json.JSONDecodeError:
        pass
    return [question]  # fallback: search the question as-is


def search_sources(tavily, queries: list[str], per_query: int) -> list[dict]:
    """Step 2: run every query and collect unique sources."""
    sources, seen = [], set()
    for query in queries:
        print(f"  🔎 {query}")
        try:
            result = tavily.search(query, max_results=per_query, include_raw_content=True)
        except Exception as e:  # one failed search shouldn't stop the rest
            print(f"     ⚠️  failed: {e}")
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
        "- Flag sources published by a vendor about its own product as potentially "
        "biased, and prefer independent sources when they disagree.\n\n"
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
    args = parser.parse_args()

    client = genai.Client(
        api_key=require_env("GEMINI_API_KEY"),
        http_options={"timeout": 60_000},  # 60 s per request (milliseconds)
    )
    tavily = TavilyClient(api_key=require_env("TAVILY_API_KEY"))

    print("🧠 Planning searches...")
    queries = plan_searches(client, args.question, args.searches)

    print("🌐 Searching sources...")
    sources = search_sources(tavily, queries, args.results)
    if not sources:
        sys.exit("No sources found. Try rephrasing the question.")
    print(f"   {len(sources)} unique sources")

    print("✍️  Writing report...\n")
    report = synthesize(client, args.question, sources, args.lang)
    print(report)

    if not args.no_save:
        print(f"💾 Saved to {save_report(args.question, report)}")


if __name__ == "__main__":
    main()
