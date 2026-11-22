import time

from research import (
    cited_numbers,
    is_timeout,
    make_slug,
    parse_domains,
    search_sources,
)


# --- cited_numbers ---------------------------------------------------------

def test_single_citation():
    assert cited_numbers("n8n is open source [2].") == {2}


def test_multiple_citations_in_one_bracket():
    assert cited_numbers("Make charges per operation [1, 3].") == {1, 3}


def test_citation_range():
    assert cited_numbers("Several sources agree [4-6].") == {4, 5, 6}


def test_repeated_citations_are_counted_once():
    text = "First claim [2]. Second claim [2]. Third claim [5]."
    assert cited_numbers(text) == {2, 5}


def test_text_without_citations():
    assert cited_numbers("No sources here.") == set()


def test_brackets_that_are_not_citations():
    assert cited_numbers("See [x] and [ ] for details.") == set()


# --- make_slug -------------------------------------------------------------

def test_slug_removes_accents_and_symbols():
    assert make_slug("¿Qué ventajas tiene n8n?") == "que-ventajas-tiene-n8n"


def test_slug_is_at_most_50_characters():
    long_question = "palabra " * 20
    assert len(make_slug(long_question)) <= 50


def test_slug_falls_back_to_report_when_empty():
    assert make_slug("¿?!") == "report"


# --- search_sources (with a fake Tavily client, no network) ----------------

class FakeTavily:
    """Pretends to be Tavily: returns canned results and can simulate failures."""

    def __init__(self, responses, delay=0.0):
        self.responses = responses  # query -> list of result dicts, or an Exception
        self.delay = delay
        self.calls = []  # records the arguments of every search, to inspect in tests

    def search(self, query, **kwargs):
        self.calls.append(kwargs)
        time.sleep(self.delay)
        response = self.responses[query]
        if isinstance(response, Exception):
            raise response
        return {"results": response}


def test_search_removes_duplicate_urls():
    fake = FakeTavily({
        "q1": [{"url": "https://a.com", "title": "A", "content": "aaa"}],
        "q2": [{"url": "https://a.com", "title": "A", "content": "aaa"},
               {"url": "https://b.com", "title": "B", "content": "bbb"}],
    })
    sources = search_sources(fake, ["q1", "q2"], per_query=3)
    assert [s["url"] for s in sources] == ["https://a.com", "https://b.com"]


def test_search_survives_a_failed_query():
    fake = FakeTavily({
        "ok": [{"url": "https://ok.com", "title": "OK", "content": "fine"}],
        "broken": RuntimeError("API down"),
    })
    sources = search_sources(fake, ["broken", "ok"], per_query=3)
    assert [s["url"] for s in sources] == ["https://ok.com"]


def test_searches_run_in_parallel():
    queries = ["q1", "q2", "q3"]
    fake = FakeTavily({q: [] for q in queries}, delay=0.5)
    started = time.perf_counter()
    search_sources(fake, queries, per_query=3)
    # Sequential would take ~1.5 s; in parallel it should take ~0.5 s.
    assert time.perf_counter() - started < 1.0


# --- is_timeout --------------------------------------------------------------

class ReadTimeout(Exception):
    """Mimics the timeout exception raised by HTTP libraries like httpx."""


def test_builtin_timeout_is_detected():
    assert is_timeout(TimeoutError())


def test_http_library_timeout_is_detected():
    assert is_timeout(ReadTimeout("The read operation timed out"))


def test_other_errors_are_not_timeouts():
    assert not is_timeout(ValueError("bad input"))


# --- domain filters ----------------------------------------------------------

def test_parse_domains_cleans_input():
    assert parse_domains(" YouTube.com, reddit.com ,, ") == ["youtube.com", "reddit.com"]


def test_parse_domains_empty():
    assert parse_domains(None) == []
    assert parse_domains("") == []


def test_exclude_is_sent_to_tavily():
    fake = FakeTavily({"q": []})
    search_sources(fake, ["q"], per_query=3, exclude=["youtube.com"])
    assert fake.calls[0]["exclude_domains"] == ["youtube.com"]
    assert "include_domains" not in fake.calls[0]


def test_no_filters_sends_nothing_extra():
    fake = FakeTavily({"q": []})
    search_sources(fake, ["q"], per_query=3)
    assert "exclude_domains" not in fake.calls[0]
    assert "include_domains" not in fake.calls[0]
