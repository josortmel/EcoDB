"""C26 (B2, #243): the cross-encoder re-orders results but its score was dropped,
so a demotion (Q1: 591f9af5 composite top 0.701 -> reranked #13) was invisible.
Each result now carries reranker_score (None when the reranker is off or failed).
Ordering is exactly the reranker's, as before. Pure: reranker stubbed.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

import reranker  # noqa: E402
import search  # noqa: E402


def _res(content, score):
    return search.SearchResult.model_construct(content=content, score=score, reranker_score=None)


def test_reranker_score_attached_and_order_kept(monkeypatch):
    results = [_res("a", 0.70), _res("b", 0.60), _res("c", 0.50)]
    fake = {"a": 0.1, "b": 2.5, "c": -1.0}

    def _rerank(query, dicts, top_k):
        for d in dicts:
            d["reranker_score"] = fake[d["content"]]
        return sorted(dicts, key=lambda d: d["reranker_score"], reverse=True)[:top_k]

    monkeypatch.setattr(reranker, "rerank", _rerank)
    monkeypatch.setattr(reranker, "is_available", lambda: True)
    out = search._apply_rerank(results, "q", limit=3, enabled=True)
    assert [r.content for r in out] == ["b", "a", "c"]
    assert [r.reranker_score for r in out] == [2.5, 0.1, -1.0]
    assert [r.score for r in out] == [0.60, 0.70, 0.50]   # composite untouched


def test_reranker_off_leaves_none_and_composite_order(monkeypatch):
    results = [_res("a", 0.70), _res("b", 0.60)]
    out = search._apply_rerank(results, "q", limit=1, enabled=False)
    assert [r.content for r in out] == ["a"]
    assert out[0].reranker_score is None


def test_reranker_failure_leaves_none(monkeypatch):
    results = [_res("a", 0.70), _res("b", 0.60)]
    monkeypatch.setattr(reranker, "rerank", lambda q, d, top_k: d[:top_k])  # degraded: no scores
    out = search._apply_rerank(results, "q", limit=2, enabled=True)
    assert [r.reranker_score for r in out] == [None, None]


def test_field_is_additive_default_none():
    assert search.SearchResult.model_fields["reranker_score"].default is None
