"""C8c: when document chunks are excluded (include_documents=False, user_id
filter, image/audio modality), the document chunks carried in graph_context
must be dropped too. Pure test — no DB.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from search import _graph_context_for_response  # noqa: E402

GC = [
    {"entity": "Eco", "hop": 0},
    {"source_type": "document_chunk", "document_id": "d1", "chunk_index": 1},
]


def test_docs_excluded_drops_document_chunks():
    assert _graph_context_for_response(GC, include_docs=False) == [{"entity": "Eco", "hop": 0}]


def test_docs_included_keeps_everything():
    assert _graph_context_for_response(GC, include_docs=True) == GC
