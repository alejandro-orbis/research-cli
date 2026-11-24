"""Web search with Tavily: parallel queries, domain filters and de-duplication."""

from concurrent.futures import ThreadPoolExecutor

from .config import MAX_CHARS_PER_SOURCE


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


def merge_sources(existing: list[dict], new: list[dict]) -> list[dict]:
    """Append new sources whose URL isn't already present, keeping existing numbering."""
    seen = {s["url"] for s in existing}
    return existing + [s for s in new if s["url"] not in seen]
