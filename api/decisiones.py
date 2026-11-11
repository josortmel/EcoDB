"""#919 · GET /api/v1/decisiones/vigentes — las decisiones y acuerdos que VALEN HOY sobre un tema.

Capa fina sobre vigentes.py (lógica pura). Solo lectura: busca candidatas con la misma búsqueda que
POST /search (tipos decision y acuerdo), lee las cadenas «superada por» con la visibilidad de quien
pregunta y le pasa todo a vigentes.vigentes(). No escribe nada propio ni pide rol de super o CEO:
cada clave ve lo que ya podía ver. Los topes devuelven un aviso en «avisos», nunca un error.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

import search
import vigentes as _vig
from auth import get_current_user
from db import get_pool

router = APIRouter(prefix="/decisiones", tags=["decisiones"])

MAX_LIMIT = 50
MAX_LEIDAS = 500          # memorias leídas en total (candidatas + cadenas)
MAX_POR_BUSQUEDA = 100    # el tope de POST /search

_LEER_SQL = """
SELECT m.id, m.type, m.content, m.created_at, m.metadata, a.identifier AS agent_identifier
FROM memories m
LEFT JOIN agents a ON a.id = m.agent_id
WHERE m.id = ANY($1::uuid[])
  AND check_visibility(
    m.user_id, m.visibility::text, m.workspace_id, m.project_id,
    $2, $3::bool, $4::bool, $5, $6::int[], false
  )
"""


def _uuid(valor) -> Optional[str]:
    try:
        return str(uuid.UUID(str(valor)))
    except (ValueError, TypeError):
        return None


def _memoria(row) -> dict:
    m = dict(row)
    m["id"] = str(m["id"])
    meta = m.get("metadata")
    m["metadata"] = json.loads(meta) if isinstance(meta, str) else (dict(meta) if meta else {})
    return m


async def _leer(ids: list[str], actor: dict) -> dict[str, dict]:
    if not ids:
        return {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _LEER_SQL, [uuid.UUID(i) for i in ids], int(actor["sub"]), bool(actor.get("is_super")),
            bool(actor.get("is_ceo")), actor.get("organization_id"), list(actor.get("lead_workspaces") or []),
        )
    return {str(r["id"]): _memoria(r) for r in rows}


@router.get("/vigentes")
async def decisiones_vigentes(
    tema: str = Query(..., min_length=search.MIN_QUERY_LEN, max_length=search.MAX_QUERY_LEN,
                      description="De qué trata (texto libre)."),
    agente: Optional[str] = Query(None, min_length=1, max_length=128, description="Solo las de este agente."),
    incluir_superadas: bool = Query(False, description="Añade «superadas» con por quién y por qué."),
    limit: int = Query(10, description=f"Máximo de vigentes (1-{MAX_LIMIT}; fuera de rango se ajusta con aviso)."),
    actor: dict = Depends(get_current_user),
) -> dict:
    avisos: list[str] = []
    if not 1 <= limit <= MAX_LIMIT:
        ajustado = max(1, min(limit, MAX_LIMIT))
        avisos.append(f"limit {limit} fuera de 1-{MAX_LIMIT}: se usa {ajustado}")
        limit = ajustado

    async def buscar(tipo: str):
        body = search.SearchRequest(query_text=tema, type=tipo, agent_identifier=agente,
                                    limit=min(limit * 3, MAX_POR_BUSQUEDA), include_documents=False)
        return await search.search_memories(body, actor)

    respuestas = await asyncio.gather(buscar("decision"), buscar("acuerdo"))
    encontradas = sorted((r for resp in respuestas for r in resp.results), key=lambda r: r.score, reverse=True)
    orden = list(dict.fromkeys(str(r.id) for r in encontradas))

    # Lee las candidatas y sigue las cadenas por rondas, con tope de saltos y de memorias leídas.
    vistas: dict[str, dict] = {}
    pedidas: set[str] = set()
    pendientes = orden
    for _ in range(_vig.MAX_SALTOS + 1):
        nuevas = [i for i in dict.fromkeys(pendientes) if i not in pedidas]
        if not nuevas:
            break
        if len(pedidas) + len(nuevas) > MAX_LEIDAS:
            avisos.append(f"más de {MAX_LEIDAS} memorias que leer: se cortó la lectura; "
                          "las cadenas sin terminar salen en «errores»")
            nuevas = nuevas[:MAX_LEIDAS - len(pedidas)]
        pedidas.update(nuevas)
        leidas = await _leer(nuevas, actor)
        vistas.update(leidas)
        pendientes = [u for u in (_uuid(m["metadata"].get("superseded_by")) for m in leidas.values()) if u]
        if len(pedidas) >= MAX_LEIDAS:
            break

    candidatas = [vistas[i] for i in orden if i in vistas]
    resultado = _vig.vigentes(candidatas, vistas.get, incluir_superadas=incluir_superadas, limit=limit)
    # vigentes() apunta como «ciclo» también la cadena que llega al tope de saltos; sin ninguna
    # memoria repetida no es un ciclo, es el tope, y se dice.
    if any("ciclo" in e and len(set(e["ciclo"])) == len(e["ciclo"]) for e in resultado["errores"]):
        avisos.append(f"una cadena pasa de {_vig.MAX_SALTOS} saltos: se cortó y sale en «errores»")
    resultado["avisos"] = avisos
    return resultado
