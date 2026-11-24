"""Command-line interface: parses arguments and runs the research pipeline."""

import argparse
import os
import sys
import time

try:
    from google import genai
    from tavily import TavilyClient
except ImportError:
    sys.exit("Missing dependencies. Run: pip install -r requirements.txt")

from .chat import chat
from .config import LANGUAGES, require_env
from .history import (
    get_report,
    latest_report_id,
    list_history,
    open_db,
    print_history,
    save_to_history,
)
from .planner import find_gaps, plan_searches
from .search import merge_sources, parse_domains, search_sources
from .writer import save_report, synthesize


def main():
    parser = argparse.ArgumentParser(description="Personal research assistant for the terminal")
    parser.add_argument("question", nargs="?", help="what you want to research (in quotes)")
    parser.add_argument("--lang", choices=LANGUAGES, default="en", help="report language (default: en)")
    parser.add_argument("--searches", type=int, default=3, help="number of web searches (default: 3)")
    parser.add_argument("--results", type=int, default=3, help="results per search (default: 3)")
    parser.add_argument("--no-save", action="store_true", help="print only, don't save a .md file")
    parser.add_argument("--exclude", help="domains to skip, comma-separated (e.g. youtube.com,reddit.com)")
    parser.add_argument("--include", help="only search these domains, comma-separated")
    parser.add_argument("--deep", action="store_true",
                        help="review the draft, search for missing information and rewrite")
    history = parser.add_argument_group("history (no API calls)")
    history.add_argument("--history", action="store_true", help="list past reports")
    history.add_argument("--search", metavar="TERM", help="search past questions and reports")
    history.add_argument("--show", type=int, metavar="ID", help="print a past report")
    history.add_argument("--chat", type=int, nargs="?", const=0, metavar="ID",
                         help="ask follow-up questions about a report (default: the latest)")
    args = parser.parse_args()

    # History commands work offline and don't need API keys.
    if args.history or args.search or args.show:
        conn = open_db()
        if args.show:
            row = get_report(conn, args.show)
            if row is None:
                sys.exit(f"No report with id {args.show}.")
            print(row["report"])
        else:
            print_history(list_history(conn, term=args.search))
        return

    if args.chat is not None:
        conn = open_db()
        report_id = args.chat or latest_report_id(conn)
        row = get_report(conn, report_id) if report_id else None
        if row is None:
            sys.exit("No report to chat about. Run a research first, or check --history.")
        client = genai.Client(
            api_key=require_env("GEMINI_API_KEY"),
            http_options={"timeout": 120_000},
        )
        chat(client, row)
        return

    if not args.question:
        parser.error("a question is required (or use --history / --search / --show)")

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
        report_id = save_to_history(
            open_db(), args.question, args.lang, args.deep, report, sources
        )
        print(f"🗂️  Saved to history as #{report_id}")
