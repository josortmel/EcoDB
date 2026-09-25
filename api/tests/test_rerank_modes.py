"""C32 (#243): rerank_mode decides how the cross-encoder picks top-k MEMBERSHIP.
  replace (the _apply_rerank function default; the pre-#243 server behaviour): reranker's top-k.
  Server default (settings) is blend alpha 0.7 since 25-sep, chosen by the rerank-variant benchmark.
  blend: top-k by alpha*norm(composite) + (1-alpha)*norm(reranker), min-max in the pool.
  off: no reranker; composite top-k.
Final order is composite in every mode (C30). Pure: reranker stubbed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import reranker  # noqa: E402
import search  # noqa: E402

# Q1 shape: T is top composite but the English cross-encoder scores it low.
COMPOSITE = {"T": 0.701, "a": 0.60, "b": 0.58, "c": 0.55, "d": 0.50, "e": 0.45}
RERANK = {"T": -4.0, "a": 3.0, "b": 2.9, "c": 2.8, "d": 2.7, "e": 2.6}


def _results():
    return [search.SearchResult.model_construct(content=k, score=v, reranker_score=None)
            for k, v in sorted(COMPOSITE.items(), key=lambda kv: -kv[1])]


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def _rerank(q, dicts, top_k):
        seen.append(top_k)
        for d in dicts:
            d["reranker_score"] = RERANK[d["content"]]
        return sorted(dicts, key=lambda d: d["reranker_score"], reverse=True)[:top_k]

    monkeypatch.setattr(reranker, "rerank", _rerank)
    return seen


def _members(out):
    return {r.content for r in out}


def test_replace_is_todays_behaviour(calls):
    out = search._apply_rerank(_results(), "q", 5, enabled=True, mode="replace")
    assert _members(out) == {"a", "b", "c", "d", "e"}          # T cut — the #243 symptom
    assert calls == [5]


def test_function_default_mode_is_replace(calls):
    assert _members(search._apply_rerank(_results(), "q", 5, enabled=True)) == {"a", "b", "c", "d", "e"}


def test_blend_keeps_top_composite_the_reranker_alone_would_cut(calls):
    out = search._apply_rerank(_results(), "q", 5, enabled=True, mode="blend", alpha=0.5)
    assert "T" in _members(out)
    assert len(out) == 5
    assert all(r.reranker_score is not None for r in out)      # still reported
    assert calls == [6]                                        # whole pool scored


def test_blend_alpha_extremes(calls):
    assert _members(search._apply_rerank(_results(), "q", 5, enabled=True, mode="blend", alpha=1.0)) \
        == {"T", "a", "b", "c", "d"}                           # pure composite
    assert _members(search._apply_rerank(_results(), "q", 5, enabled=True, mode="blend", alpha=0.0)) \
        == {"a", "b", "c", "d", "e"}                           # pure reranker


def test_off_ignores_reranker(calls):
    out = search._apply_rerank(_results(), "q", 5, enabled=True, mode="off")
    assert _members(out) == {"T", "a", "b", "c", "d"}
    assert calls == []
    assert all(r.reranker_score is None for r in out)


def test_blend_degraded_reranker_falls_back_to_composite(monkeypatch):
    monkeypatch.setattr(reranker, "rerank", lambda q, d, top_k: d[:top_k])   # no scores
    out = search._apply_rerank(_results(), "q", 5, enabled=True, mode="blend")
    assert _members(out) == {"T", "a", "b", "c", "d"}


def test_request_fields_and_settings_default():
    f = search.SearchRequest.model_fields
    assert f["rerank_mode"].default is None and f["rerank_alpha"].default is None
    import settings
    assert settings.RERANK_MODE in ("replace", "blend", "off")
    assert 0.0 <= settings.RERANK_BLEND_ALPHA <= 1.0


def test_server_default_is_blend_0_7(monkeypatch):
    """#243: settings default chosen by the benchmark (env unset)."""
    import importlib, settings as st
    monkeypatch.delenv("RERANK_MODE", raising=False)
    monkeypatch.delenv("RERANK_BLEND_ALPHA", raising=False)
    st = importlib.reload(st)
    assert st.RERANK_MODE == "blend"
    assert st.RERANK_BLEND_ALPHA == 0.7
