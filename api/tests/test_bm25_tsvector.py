"""#243: Postgres' parser turns `RunResult.structured` / `api/search.py` into ONE
host/file lexeme, so the bare identifier is never indexed and BM25 can't match
it. Every BM25 tsvector must also index the text with '.' and '/' split.
Pure test (no DB): the SQL builder and every BM25 site in search.py.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from search import _bm25_tsvector  # noqa: E402

SEARCH_SRC = (Path(__file__).parent.parent / "search.py").read_text(encoding="utf-8")


def test_builder_indexes_original_and_split_forms():
    sql = _bm25_tsvector("dc.content")
    assert "to_tsvector('spanish', dc.content)" in sql
    assert r"regexp_matches(dc.content, '(\w+(?:[./]\w+)+)', 'g')" in sql
    assert "||" in sql


def test_no_bare_single_form_tsvector_left_in_search():
    """Every to_tsvector in search.py must come from the builder."""
    bare = [m.group(0) for m in re.finditer(r"to_tsvector\('spanish',\s*[\w.]+\)", SEARCH_SRC)]
    # the builder itself contains exactly one literal template
    assert len(bare) == 0, f"single-form tsvector still used: {bare}"
