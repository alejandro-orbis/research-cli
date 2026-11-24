#!/usr/bin/env python3
"""
Entry point kept for convenience: `python research.py "question"`.

The code lives in the research_cli/ package:
  config.py   settings from the environment
  llm.py      model calls, retries and fallback
  planner.py  search planning and gap detection (--deep)
  search.py   parallel web search with Tavily
  writer.py   report synthesis, citations and saving
  history.py  SQLite history
  chat.py     follow-up questions (--chat)
  cli.py      command-line interface
"""

from research_cli.cli import main

if __name__ == "__main__":
    main()
