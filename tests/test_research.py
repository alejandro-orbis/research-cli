import time

import pytest

import research
from research import (
    cited_numbers,
    ask_llm,
    build_chat_prompt,
    chat,
    find_gaps,
    get_report,
    latest_report_id,
    list_history,
    open_db,
    save_to_history,
    is_quota_error,
    is_timeout,
    make_slug,
    merge_sources,
    parse_domains,
    parse_json_list,
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


# --- deep mode ---------------------------------------------------------------

def test_parse_json_list_plain():
    assert parse_json_list('["a", "b"]') == ["a", "b"]


def test_parse_json_list_inside_code_fence():
    assert parse_json_list('```json\n["a", "b"]\n```') == ["a", "b"]


def test_parse_json_list_invalid_returns_empty():
    assert parse_json_list("Sure! Here are some queries: a, b") == []
    assert parse_json_list('{"not": "a list"}') == []


def test_merge_sources_skips_known_urls_and_keeps_order():
    existing = [{"url": "https://a.com"}, {"url": "https://b.com"}]
    new = [{"url": "https://b.com"}, {"url": "https://c.com"}]
    merged = merge_sources(existing, new)
    assert [s["url"] for s in merged] == ["https://a.com", "https://b.com", "https://c.com"]


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, reply):
        self.reply = reply

    def generate_content(self, model, contents):
        return FakeResponse(self.reply)


class FakeGemini:
    """Pretends to be the Gemini client: always answers with the same text."""

    def __init__(self, reply):
        self.models = FakeModels(reply)


def test_find_gaps_returns_at_most_n_queries():
    client = FakeGemini('["gap 1", "gap 2", "gap 3", "gap 4"]')
    assert find_gaps(client, "question", "draft", n=2) == ["gap 1", "gap 2"]


def test_find_gaps_with_nothing_missing():
    client = FakeGemini("[]")
    assert find_gaps(client, "question", "draft", n=3) == []


# --- quota errors and model fallback -----------------------------------------

class QuotaError(Exception):
    """Mimics the API error raised when a model's daily quota is exhausted."""
    code = 429


def test_quota_error_is_detected():
    assert is_quota_error(QuotaError())
    assert not is_quota_error(ValueError())


class ModelAwareModels:
    """Fake Gemini models: some models fail with an error, others answer."""

    def __init__(self, behaviour):
        self.behaviour = behaviour  # model name -> reply text, or an Exception
        self.tried = []

    def generate_content(self, model, contents):
        self.tried.append(model)
        outcome = self.behaviour[model]
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


@pytest.fixture(autouse=True)
def reset_llm_memory(monkeypatch):
    """Start every test with a clean ask_llm() memory, so tests don't affect each other."""
    monkeypatch.setattr(research, "_exhausted", set())
    monkeypatch.setattr(research, "_preferred", None)


def test_ask_llm_falls_back_when_a_model_is_out_of_quota(monkeypatch):
    monkeypatch.setattr(research, "MODELS", ["model-a", "model-b"])
    client = FakeGemini("")
    client.models = ModelAwareModels({"model-a": QuotaError(), "model-b": "hello"})
    assert ask_llm(client, "prompt") == "hello"
    assert client.models.tried == ["model-a", "model-b"]  # no pointless retries of model-a


def test_exhausted_model_is_not_retried_in_later_calls(monkeypatch):
    monkeypatch.setattr(research, "MODELS", ["model-a", "model-b"])
    client = FakeGemini("")
    client.models = ModelAwareModels({"model-a": QuotaError(), "model-b": "ok"})
    ask_llm(client, "first call")
    ask_llm(client, "second call")
    # model-a is tried once; the second call goes straight to model-b
    assert client.models.tried == ["model-a", "model-b", "model-b"]


def test_last_successful_model_is_tried_first(monkeypatch):
    monkeypatch.setattr(research, "MODELS", ["model-a", "model-b", "model-c"])
    monkeypatch.setattr(research, "_preferred", "model-c")
    assert research.model_order() == ["model-c", "model-a", "model-b"]


# --- history (SQLite, in memory) ---------------------------------------------

@pytest.fixture
def db():
    """A throwaway in-memory database for each test."""
    conn = open_db(":memory:")
    yield conn
    conn.close()


def test_saved_report_can_be_read_back(db):
    sources = [{"title": "A", "url": "https://a.com"}]
    report_id = save_to_history(db, "What is n8n?", "en", False, "# Report", sources)
    row = get_report(db, report_id)
    assert row["question"] == "What is n8n?"
    assert row["report"] == "# Report"
    assert row["deep"] == 0


def test_sources_are_stored_with_their_numbers(db):
    sources = [{"title": "A", "url": "https://a.com"}, {"title": "B", "url": "https://b.com"}]
    report_id = save_to_history(db, "q", "en", True, "r", sources)
    rows = db.execute(
        "SELECT num, url FROM sources WHERE report_id = ? ORDER BY num", (report_id,)
    ).fetchall()
    assert [(r["num"], r["url"]) for r in rows] == [(1, "https://a.com"), (2, "https://b.com")]


def test_history_lists_newest_first(db):
    save_to_history(db, "first", "en", False, "r", [])
    save_to_history(db, "second", "en", False, "r", [])
    assert [r["question"] for r in list_history(db)] == ["second", "first"]


def test_history_search_matches_question_and_report(db):
    save_to_history(db, "n8n vs Make", "en", False, "about automation", [])
    save_to_history(db, "Best laptops", "en", False, "mentions n8n once", [])
    save_to_history(db, "Python tips", "en", False, "nothing related", [])
    found = [r["question"] for r in list_history(db, term="n8n")]
    assert found == ["Best laptops", "n8n vs Make"]


def test_missing_report_returns_none(db):
    assert get_report(db, 999) is None


# --- follow-up chat ----------------------------------------------------------

def test_latest_report_id(db):
    assert latest_report_id(db) is None
    save_to_history(db, "first", "en", False, "r", [])
    second = save_to_history(db, "second", "en", False, "r", [])
    assert latest_report_id(db) == second


def test_chat_prompt_contains_report_and_question():
    prompt = build_chat_prompt("# Report about n8n", [], "Is it free?")
    assert "# Report about n8n" in prompt
    assert "User: Is it free?" in prompt
    assert "Conversation so far" not in prompt  # no history yet


def test_chat_prompt_keeps_only_recent_turns():
    history = [(f"q{i}", f"a{i}") for i in range(10)]
    prompt = build_chat_prompt("report", history, "new question")
    assert "q9" in prompt and "q4" in prompt
    assert "q3" not in prompt  # older than the last 6 turns


def test_chat_loop_answers_until_exit(monkeypatch):
    monkeypatch.setattr(research, "MODELS", ["model-a"])
    answers = iter(["What does it cost?", "", "exit"])  # empty input is ignored
    client = FakeGemini("It's free when self-hosted [2].")
    row = {"id": 1, "question": "n8n vs Make", "report": "# Report"}
    history = chat(client, row, ask=lambda _prompt: next(answers))
    assert history == [("What does it cost?", "It's free when self-hosted [2].")]


def test_chat_ends_cleanly_on_ctrl_c():
    def press_ctrl_c(_prompt):
        raise KeyboardInterrupt
    row = {"id": 1, "question": "q", "report": "r"}
    assert chat(FakeGemini("unused"), row, ask=press_ctrl_c) == []
