"""Norma de Pepe (11-nov-2026): «cuando leáis las consolidaciones no veáis qué modelo lo ha escrito; puede estar en
unos metadatos que haya que buscar, pero nunca lo recibáis sin buscarlo explícitamente».
Ninguna respuesta de clusters lleva el modelo ni la célula; GET /clusters/{id}/modelo sí. Sin base de datos.
"""
import json
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import clusters  # noqa: E402
from auth import get_current_user  # noqa: E402

CID = "11111111-1111-1111-1111-111111111111"
META = {"cell_generated": True, "cell_model": "deepseek-flash", "cell_agent": "Hilo.memoria",
        "week_rollup": True, "narrated_by": "owner", "cell_model_before_owner": "deepseek-flash"}
ROW = {"id": UUID(CID), "agent_id": 3, "level": "weekly", "label": "Las llaves", "detail": None,
       "narrative": "texto", "member_count": 2, "source_count": 0, "pattern_flags": None,
       "period_start": date(2026, 11, 2), "period_end": date(2026, 11, 8), "status": "active",
       "narrated_at": None, "created_at": datetime(2026, 11, 9), "cell_model": "deepseek-flash",
       "metadata": json.dumps(META), "member_ids": [], "source_ids": []}


def _sin_rastro(payload):
    texto = json.dumps(payload, default=str)
    assert "deepseek" not in texto
    for clave in ('"model"', '"model_source"', '"cell_model"', '"cell_agent"', '"cell_generated"',
                  '"narrated_by"', '"cell_model_before_owner"'):
        assert clave not in texto, clave


def test_resumen_y_detalle_no_llevan_modelo():
    _sin_rastro(clusters._cluster_summary(ROW).model_dump())
    detalle = clusters._cluster_detail(ROW).model_dump()
    _sin_rastro(detalle)
    assert detalle["metadata"] == {"week_rollup": True}     # el resto de metadatos sigue


def test_vistas_y_zoom_no_tienen_campo_de_modelo():
    for modelo in (clusters.ClusterSummary, clusters.ClusterNarrativeSummary, clusters.FractalZoomCluster):
        assert not [c for c in modelo.model_fields if "model" in c], modelo.__name__


def _client(monkeypatch):
    class _Pool:
        @asynccontextmanager
        async def acquire(self):
            yield None

    async def _pool():
        return _Pool()

    async def _resolve(conn, actor, cid):
        return dict(ROW)

    monkeypatch.setattr(clusters, "get_pool", _pool)
    monkeypatch.setattr(clusters, "resolve_cluster_for_actor", _resolve)
    app = FastAPI()
    app.include_router(clusters.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "1", "is_super": True}
    return TestClient(app, raise_server_exceptions=False)


def test_get_cluster_no_lo_ensena(monkeypatch):
    r = _client(monkeypatch).get(f"/api/v1/clusters/{CID}")
    assert r.status_code == 200, r.text
    _sin_rastro(r.json())


def test_modelo_solo_si_se_pide(monkeypatch):
    r = _client(monkeypatch).get(f"/api/v1/clusters/{CID}/modelo")
    assert r.status_code == 200, r.text
    assert r.json() == {"cluster_id": CID, "cell_model": "deepseek-flash", "model_source": "measured",
                        "cell_agent": "Hilo.memoria", "cell_generated": True, "narrated_by": "owner",
                        "cell_model_before_owner": "deepseek-flash"}
