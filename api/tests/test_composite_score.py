"""Test that compute_composite_score reads weights from GAMR_WEIGHTS_BM25 dict."""
import pytest


def test_factual_uses_dict_freshness():
    """Freshness weight for 'factual' must come from GAMR_WEIGHTS_BM25, not hardcoded 0.02."""
    from search import compute_composite_score
    from settings import GAMR_WEIGHTS_BM25

    expected_freshness_weight = GAMR_WEIGHTS_BM25["factual"]["freshness"]

    result = compute_composite_score(
        semantic_score=0.5,
        graph_score=0.0,
        memory_weight=0.0,
        freshness_score=1.0,
        query_type="factual",
        bm25_score=0.0,
    )
    expected_composite = 0.5 * (1.0 + expected_freshness_weight)
    assert result["breakdown"]["freshness"] == pytest.approx(expected_freshness_weight, abs=0.001)
    assert result["composite"] == pytest.approx(expected_composite, abs=0.001)


def test_contextual_uses_dict_freshness():
    """Different query_type should use different weight from dict."""
    from search import compute_composite_score
    from settings import GAMR_WEIGHTS_BM25

    factual_w = GAMR_WEIGHTS_BM25["factual"]["freshness"]
    contextual_w = GAMR_WEIGHTS_BM25["contextual"]["freshness"]

    r_factual = compute_composite_score(0.5, 0.0, 0.0, 1.0, "factual")
    r_contextual = compute_composite_score(0.5, 0.0, 0.0, 1.0, "contextual")

    assert r_factual["breakdown"]["freshness"] == pytest.approx(factual_w, abs=0.001)
    assert r_contextual["breakdown"]["freshness"] == pytest.approx(contextual_w, abs=0.001)


def test_all_weights_come_from_dict():
    """Every bonus (bm25, graph, weight, freshness) must use dict values."""
    from search import compute_composite_score
    from settings import GAMR_WEIGHTS_BM25

    w = GAMR_WEIGHTS_BM25["analytical"]
    result = compute_composite_score(
        semantic_score=0.8,
        graph_score=1.0,
        memory_weight=1.0,
        freshness_score=1.0,
        query_type="analytical",
        bm25_score=1.0,
    )
    assert result["breakdown"]["bm25"] == pytest.approx(w["bm25"], abs=0.001)
    assert result["breakdown"]["graph"] == pytest.approx(w["graph"], abs=0.001)
    assert result["breakdown"]["weight"] == pytest.approx(w["weight"], abs=0.001)
    assert result["breakdown"]["freshness"] == pytest.approx(w["freshness"], abs=0.001)


def test_unknown_query_type_falls_back_to_contextual():
    """Unknown query_type must fall back to contextual weights."""
    from search import compute_composite_score
    from settings import GAMR_WEIGHTS_BM25

    w = GAMR_WEIGHTS_BM25["contextual"]
    result = compute_composite_score(
        semantic_score=0.5,
        graph_score=1.0,
        memory_weight=1.0,
        freshness_score=1.0,
        query_type="unknown_type",
        bm25_score=1.0,
    )
    assert result["breakdown"]["bm25"] == pytest.approx(w["bm25"], abs=0.001)
    assert result["breakdown"]["graph"] == pytest.approx(w["graph"], abs=0.001)
    assert result["breakdown"]["weight"] == pytest.approx(w["weight"], abs=0.001)
    assert result["breakdown"]["freshness"] == pytest.approx(w["freshness"], abs=0.001)
