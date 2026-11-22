from research import cited_numbers, make_slug


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
