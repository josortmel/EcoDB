"""#702, cobertura (28-oct). Prima midió en producción que entre el 17 % y el 46 % de las memorias de cada agente no
estaban en NINGÚN semanal: el núcleo de «perdemos recuerdos» de Pepe. Se caían en cuatro sitios: el grupo de una sola
memoria (muere en MIN_CLUSTER_SIZE), el índice que el LLM no devuelve, la deduplicación que se lleva un cluster
solapado con sus miembros, y la semana con menos memorias que un cluster. Ahora, después de todo eso, cada memoria
que sigue fuera entra de forma determinista en el cluster de centroide más parecido; sin embedding o sin ningún
cluster, en «Sueltas de la semana», que no tiene narrativa (no entra en prev_narratives). El rollup las ve."""
import asyncio
import inspect
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from conftest import TEST_DB_URL  # noqa: E402

os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
import cell_worker as cw  # noqa: E402

A, B = [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]


def _m(i, emb):
    return {"id": f"m{i}", "weight": 0.5, "type": "momento", "agent_identifier": "Prima",
            "created_at": datetime(2026, 4, 6, tzinfo=timezone.utc), "content": f"memoria {i}",
            "embedding": cw._vec_literal(emb) if emb is not None else None}


def _llm(answer):
    async def fake(system_prompt, user_prompt):
        return json.dumps(answer)
    return fake


def _covered(clusters):
    return sorted(str(x) for c in clusters for x in c["member_ids"])


def _run(monkeypatch, mems, labels, answer):
    monkeypatch.setattr(cw, "_llm_call", _llm(answer))
    clusters, _, _ = asyncio.run(cw._label_clusters_llm(mems, labels, [], "Prima"))
    return cw._cover_uncovered(mems, clusters)


def test_a_memory_the_llm_leaves_out_joins_the_closest_cluster(monkeypatch):
    mems = [_m(0, A), _m(1, A), _m(2, B), _m(3, B), _m(4, [0.1, 0.9, 0.0])]
    ans = {"clusters": [{"label": "a", "member_indices": [0, 1]}, {"label": "b", "member_indices": [2, 3]}]}
    clusters, added = _run(monkeypatch, mems, [0, 0, 1, 1, 1], ans)
    assert added == ["m4"] and _covered(clusters) == [f"m{i}" for i in range(5)]
    b = [c for c in clusters if c["label"] == "b"][0]
    assert "m4" in b["member_ids"] and b["metadata"]["coverage_added"] == ["m4"]


def test_a_singleton_group_is_not_lost(monkeypatch):
    mems = [_m(0, A), _m(1, A), _m(2, B)]
    ans = {"clusters": [{"label": "a", "member_indices": [0, 1]}, {"label": "solo", "member_indices": [2]}]}
    clusters, added = _run(monkeypatch, mems, [0, 0, 1], ans)
    assert added == ["m2"] and _covered(clusters) == ["m0", "m1", "m2"]


def test_the_dedup_does_not_take_members_with_it(monkeypatch):
    # «b» overlaps «a» by 4/5 > 0.8 and is dropped by the dedup; m4 was only in «b».
    mems = [_m(i, A) for i in range(5)]
    ans = {"clusters": [{"label": "a", "member_indices": [0, 1, 2, 3]},
                        {"label": "b", "member_indices": [0, 1, 2, 3, 4]}]}
    clusters, added = _run(monkeypatch, mems, [0, 0, 0, 0, 0], ans)
    assert [c["label"] for c in clusters] == ["a"] and added == ["m4"]
    assert _covered(clusters) == [f"m{i}" for i in range(5)]


def test_no_cluster_at_all_goes_to_the_weeks_loose_cluster():
    clusters, added = cw._cover_uncovered([_m(0, A)], [])
    assert len(clusters) == 1 and added == ["m0"]
    c = clusters[0]
    assert c["label"] == cw.LOOSE_LABEL and c["narrative"] is None and c["member_ids"] == ["m0"]
    assert c["metadata"]["assigned_by"] == "coverage" and "memoria 0" in c["detail"]


def test_a_memory_without_embedding_goes_to_the_loose_cluster(monkeypatch):
    mems = [_m(0, A), _m(1, A), _m(2, None)]
    ans = {"clusters": [{"label": "a", "member_indices": [0, 1]}]}
    clusters, added = _run(monkeypatch, mems, [0, 0, 1], ans)
    assert added == ["m2"] and [c["label"] for c in clusters] == ["a", cw.LOOSE_LABEL]


def test_nothing_is_added_when_everything_is_covered(monkeypatch):
    mems = [_m(0, A), _m(1, A)]
    clusters, added = _run(monkeypatch, mems, [0, 0], {"clusters": [{"label": "a", "member_indices": [0, 1]}]})
    assert added == [] and len(clusters) == 1


def test_the_loose_cluster_never_enters_the_next_weeks_context():
    src = inspect.getsource(cw.run_consolidation)
    prev = re.search(r"prev_narratives = await conn\.fetch\(\"\"\"(.*?)\"\"\"", src, re.S).group(1)
    assert "narrative IS NOT NULL" in prev        # the loose cluster has narrative None


def test_a_small_week_skips_the_thematic_llm_and_is_covered():
    src = inspect.getsource(cw.run_consolidation)
    assert "if _small_week:" in src and "_cover_uncovered(memories, cluster_data)" in src
