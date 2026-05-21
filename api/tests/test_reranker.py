"""Tests for reranker module: loading, degradation, SHA pinning."""
import pytest
from unittest.mock import patch, MagicMock


def test_reranker_disabled_by_env():
    """RERANKER_ENABLED=false → rerank returns input unchanged."""
    with patch.dict("os.environ", {"RERANKER_ENABLED": "false"}):
        import importlib
        import reranker
        importlib.reload(reranker)
        assert not reranker.is_available()
        results = [{"content": "a", "score": 0.5}, {"content": "b", "score": 0.8}]
        out = reranker.rerank("query", results, top_k=2)
        assert out == results


def test_rerank_graceful_on_load_failure():
    """If model fails to load, rerank returns input unchanged with WARNING."""
    with patch.dict("os.environ", {"RERANKER_ENABLED": "true", "RERANKER_MODEL": "nonexistent/model"}):
        import importlib
        import reranker
        importlib.reload(reranker)
        assert not reranker.is_available()
        results = [{"content": "a"}, {"content": "b"}]
        out = reranker.rerank("query", results, top_k=2)
        assert out == results


def test_rerank_truncates_to_top_k():
    """Reranker returns exactly top_k results."""
    with patch("reranker._available", True), \
         patch("reranker._model") as mock_model:
        mock_model.predict.return_value = [0.9, 0.1, 0.5]
        import reranker
        results = [{"content": "a"}, {"content": "b"}, {"content": "c"}]
        out = reranker.rerank("query", results, top_k=2)
        assert len(out) == 2
        assert out[0]["content"] == "a"  # highest score 0.9
        assert out[1]["content"] == "c"  # second highest 0.5
