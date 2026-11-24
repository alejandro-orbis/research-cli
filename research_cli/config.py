"""Settings read from the environment (.env file or shell variables)."""

import os
import sys

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

DB_PATH = os.getenv("RESEARCH_DB", "research_history.db")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        sys.exit(f"Missing environment variable: {name} (see .env.example)")
    return value
