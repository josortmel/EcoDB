"""C30 (F1): one ordering rule. The reranker chooses top-k MEMBERSHIP (and its score
stays visible), but the final order is ALWAYS the composite score — with or without
document chunks. Before, include_documents=true re-sorted by composite while
include_documents=false kept the reranker's order (ms-marco degrades Spanish, #374).
Pure: reranker stubbed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import reranker  # noqa: E402
import search  # noqa: E402


def _res(content, score, source_type="memory"):
    return search.SearchResult.model_construct(content=content, score=score,
                                               reranker_score=None, source_type=source_type)


def _pipeline(monkeypatch, with_docs: bool, limit=3):
    # composite order a > b > c > d; the reranker prefers d, c, b and drops a
    fake = {"a": -5.0, "b": 1.0, "c": 2.0, "d": 3.0}

    def _rerank(q, dicts, top_k):
        for d in dicts:
            d["reranker_score"] = fake[d["content"]]
        return sorted(dicts, key=lambda d: d["reranker_score"], reverse=True)[:top_k]

    monkeypatch.setattr(reranker, "rerank", _rerank)
    results = [_res("a", 0.9), _res("b", 0.8), _res("c", 0.7), _res("d", 0.6)]
    results = search._apply_rerank(results, "q", limit, enabled=True)
    if with_docs:
        results.append(_res("doc", 0.75, "document_chunk"))
    return search._final_order(results, limit)


def test_docs_off_final_order_is_composite(monkeypatch):
    out = _pipeline(monkeypatch, with_docs=False)
    assert [r.content for r in out] == ["b", "c", "d"]          # membership: reranker; order: composite
    assert [r.reranker_score for r in out] == [1.0, 2.0, 3.0]    # still visible


def test_docs_on_and_off_give_the_same_memory_order(monkeypatch):
    off = [r.content for r in _pipeline(monkeypatch, with_docs=False, limit=4)]
    on = [r.content for r in _pipeline(monkeypatch, with_docs=True, limit=5) if r.source_type == "memory"]
    assert on == off


def test_final_order_caps_after_sorting():
    out = search._final_order([_res("x", 0.1), _res("y", 0.9), _res("z", 0.5)], 2)
    assert [r.content for r in out] == ["y", "z"]
