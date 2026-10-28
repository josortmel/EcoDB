"""#808 (28-oct, encargo de Pepe «solucionemos de una vez el problema de la memoria»): una semana cargada salía
PARTIDA en dos semanales (Eco 14-17/18-20 sep, Lienzo 5-8/9-11 oct, Prima 19-22/23-25 oct). Medido en cell_runs:
el JSON de la célula llegaba CORTADO («Unterminated string … char 19100») porque la narrativa de todos los grupos
de la semana no cabe en una sola salida, y #393 partía entonces la semana por días.
Ahora, si la respuesta no se puede leer, se piden los grupos en dos mitades (con sus memorias y sus índices
originales) y se juntan: la semana sigue entera. Partir por días queda solo si ni un grupo suelto cabe."""
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from conftest import TEST_DB_URL  # noqa: E402

os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
import cell_worker as cw  # noqa: E402


def _mems(n):
    return [{"id": f"m{i}", "weight": 0.5, "type": "momento", "agent_identifier": "Prima",
             "created_at": datetime(2026, 10, 19, tzinfo=timezone.utc), "content": f"memoria {i}",
             "embedding": None} for i in range(n)]


def _fake_llm(max_groups, calls):
    """Answers like the cell's model, but CUTS the JSON when asked for more than max_groups clusters."""
    async def fake(system_prompt, user_prompt):
        groups = json.loads(re.search(r"Pre-computed clusters \(by memory index\): (\{.*\})", user_prompt).group(1))
        calls.append(sorted(int(k) for k in groups))
        body = {"clusters": [{"label": f"grupo {k}", "member_indices": v, "narrative": "n"}
                             for k, v in groups.items()],
                "arcos_que_cruzan": "arcos", "lo_que_evitas": "evito"}
        raw = json.dumps(body)
        return raw[:len(raw) // 2] if len(groups) > max_groups else raw
    return fake


def test_a_cut_answer_is_asked_again_by_halves_and_the_week_stays_whole(monkeypatch):
    calls = []
    monkeypatch.setattr(cw, "_llm_call", _fake_llm(2, calls))
    mems = _mems(12)
    labels = [i // 3 for i in range(12)]          # 4 groups of 3
    clusters, arcos, evito = asyncio.run(cw._label_clusters_llm(mems, labels, [], "Prima"))
    assert sorted(c["label"] for c in clusters) == ["grupo 0", "grupo 1", "grupo 2", "grupo 3"]
    assert sorted(m for c in clusters for m in c["member_ids"]) == sorted(m["id"] for m in mems)
    assert calls[0] == [0, 1, 2, 3] and [0, 1] in calls and [2, 3] in calls
    assert arcos == "arcos" and evito == "evito"


def test_a_half_only_carries_its_own_memories_with_their_original_index(monkeypatch):
    prompts = []

    async def fake(system_prompt, user_prompt):
        prompts.append(user_prompt)
        groups = json.loads(re.search(r"Pre-computed clusters \(by memory index\): (\{.*\})", user_prompt).group(1))
        if len(groups) > 1:
            return '{"clusters": [{"label": "cort'
        (k, v), = groups.items()
        return json.dumps({"clusters": [{"label": f"g{k}", "member_indices": v}]})
    monkeypatch.setattr(cw, "_llm_call", fake)
    mems = _mems(6)
    clusters, _, _ = asyncio.run(cw._label_clusters_llm(mems, [0, 0, 0, 1, 1, 1], [], "Prima"))
    by_label = {c["label"]: c["member_ids"] for c in clusters}
    assert by_label == {"g0": ["m0", "m1", "m2"], "g1": ["m3", "m4", "m5"]}
    second = [p for p in prompts if '"1": [3, 4, 5]' in p and '"0"' not in p][0]
    assert "[3]" in second and "[0]" not in second


def test_if_not_even_one_group_fits_it_still_fails_as_before(monkeypatch):
    async def always_cut(system_prompt, user_prompt):
        return '{"clusters": [{"label": "cort'
    monkeypatch.setattr(cw, "_llm_call", always_cut)
    with pytest.raises(json.JSONDecodeError):
        asyncio.run(cw._label_clusters_llm(_mems(6), [0, 0, 0, 1, 1, 1], [], "Prima"))


def test_a_good_answer_is_one_call(monkeypatch):
    calls = []
    monkeypatch.setattr(cw, "_llm_call", _fake_llm(99, calls))
    clusters, _, _ = asyncio.run(cw._label_clusters_llm(_mems(9), [0, 0, 0, 1, 1, 1, 2, 2, 2], [], "Prima"))
    assert len(clusters) == 3 and len(calls) == 1
