"""Writing the report: synthesis with citations, cited-source list and saving."""

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from .config import LANGUAGES, SOURCES_HEADING
from .llm import ask_llm


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
