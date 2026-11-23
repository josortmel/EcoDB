"""#919 · GET /api/v1/decisiones/vigentes — las decisiones y acuerdos que VALEN HOY sobre un tema.

Capa fina sobre vigentes.py (lógica pura). Solo lectura: busca candidatas con la misma búsqueda que
POST /search (tipos decision y acuerdo), lee las cadenas «superada por» con la visibilidad de quien
pregunta y le pasa todo a vigentes.vigentes(). No escribe nada propio ni pide rol de super o CEO:
cada clave ve lo que ya podía ver. Los topes devuelven un aviso en «avisos», nunca un error.
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query

import search
import vigentes as _vig
from auth import get_current_user
from db import get_pool
from embeddings_client import embed_text

router = APIRouter(prefix="/decisiones", tags=["decisiones"])

MAX_LIMIT = 50
MAX_LEIDAS = 500  # memorias leídas en total (candidatas + cadenas)
MAX_POR_BUSQUEDA = 100  # el tope de POST /search

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


# #1118: al revés, las memorias de cualquier tipo que nombran como sustituta a alguna de $1.
_PREVIAS_SQL = """
SELECT m.id, m.type, m.content, m.created_at, m.metadata, a.identifier AS agent_identifier
FROM memories m
LEFT JOIN agents a ON a.id = m.agent_id
WHERE m.metadata->>'superseded_by' = ANY($1::text[])
  AND check_visibility(
    m.user_id, m.visibility::text, m.workspace_id, m.project_id,
    $2, $3::bool, $4::bool, $5, $6::int[], false
  )
ORDER BY m.created_at
"""


# #1098: camino propio de candidatas. search_memories tarda 12,5 s por llamada y 9-10 s son del grafo (#486),
# que a vigentes no le sirve; aquí, una consulta: vector y texto sobre decision/acuerdo, fusionados por rango
# recíproco (RRF), con la misma visibilidad. Diseño sellado antes de medir: Hilo/Documentacion/diseno_1098_vigentes.md.
RRF_K = 60
TOPE_LISTA = 50
SUELO = 0.60  # coseno mínimo para que una fila de EcoDB cuente como relevante (ajuste con el set de desarrollo)
MARGEN = 0.06  # y no más lejos que esto de la mejor de su mitad
_VACIAS = {
    "de",
    "la",
    "el",
    "en",
    "y",
    "a",
    "que",
    "los",
    "las",
    "del",
    "por",
    "con",
    "para",
    "un",
    "una",
    "se",
    "no",
    "lo",
    "al",
    "es",
}

_CANDIDATAS_SQL = f"""
WITH vis AS (
  SELECT m.id, m.content
  FROM memories m
  LEFT JOIN agents a ON a.id = m.agent_id
  WHERE m.type IN ('decision', 'acuerdo')
    AND {search.DORMANT_EXCLUSION_CLAUSE}
    AND ($7::text IS NULL OR a.identifier = $7)
    AND check_visibility(
      m.user_id, m.visibility::text, m.workspace_id, m.project_id,
      $2, $3::bool, $4::bool, $5, $6::int[], false
    )
),
vec AS (
  SELECT v.id, row_number() OVER (ORDER BY e.embedding <=> $1::vector) AS r
  FROM vis v JOIN memory_embeddings e ON e.memory_id = v.id AND e.modality = 'text'
  ORDER BY e.embedding <=> $1::vector
  LIMIT {TOPE_LISTA}
),
txt AS (
  SELECT v.id, row_number() OVER (ORDER BY ts_rank({search._bm25_tsvector("v.content")}, q) DESC) AS r
  FROM vis v, plainto_tsquery('spanish', $8) q
  WHERE {search._bm25_tsvector("v.content")} @@ q
  ORDER BY ts_rank({search._bm25_tsvector("v.content")}, q) DESC
  LIMIT {TOPE_LISTA}
)
SELECT u.id, vec.r AS r_vec, txt.r AS r_txt, mm.content,
       1 - (e.embedding <=> $1::vector) AS cos,
       coalesce(1.0 / ({RRF_K} + vec.r), 0) + coalesce(1.0 / ({RRF_K} + txt.r), 0) AS rrf
FROM (SELECT id FROM vec UNION SELECT id FROM txt) u
LEFT JOIN vec ON vec.id = u.id
LEFT JOIN txt ON txt.id = u.id
LEFT JOIN memory_embeddings e ON e.memory_id = u.id AND e.modality = 'text'
JOIN memories mm ON mm.id = u.id
ORDER BY rrf DESC
"""


def _palabras(texto: str) -> set[str]:
    import re

    return {w for w in re.findall(r"\w+", (texto or "").lower()) if len(w) > 2 and w not in _VACIAS}


def _relevantes(filas: list[dict], tema: str) -> list[dict]:
    """#1098, umbral POR MITAD (Prima, 10-nov): de las candidatas de EcoDB, solo las que se parecen de verdad
    al tema. Por vector: coseno ≥ SUELO y a menos de MARGEN de la mejor. Solo por texto: además comparte al
    menos la mitad de las palabras con contenido del tema. Si ninguna pasa, la mitad no aporta nada."""
    if not filas:
        return []
    mejor = max((f["cos"] or 0) for f in filas)
    pide = _palabras(tema)
    salen = []
    for f in filas:
        cos = f["cos"] or 0
        if cos < SUELO or cos < mejor - MARGEN:
            continue
        if f["r_vec"] is None and pide:
            comun = pide & _palabras(f.get("content", ""))
            if len(comun) * 2 < len(pide):
                continue
        salen.append(f)
    return salen


async def _candidatas(tema: str, agente: Optional[str], actor: dict) -> list[dict]:
    vector = await embed_text(tema, prompt_name="query")
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            _CANDIDATAS_SQL,
            vector,
            int(actor["sub"]),
            bool(actor.get("is_super")),
            bool(actor.get("is_ceo")),
            actor.get("organization_id"),
            list(actor.get("lead_workspaces") or []),
            agente,
            tema,
        )
    return [
        {
            "id": str(r["id"]),
            "r_vec": r["r_vec"],
            "r_txt": r["r_txt"],
            "content": r["content"],
            "cos": float(r["cos"]) if r["cos"] is not None else None,
            "rrf": float(r["rrf"]),
        }
        for r in rows
    ]


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
            _LEER_SQL,
            [uuid.UUID(i) for i in ids],
            int(actor["sub"]),
            bool(actor.get("is_super")),
            bool(actor.get("is_ceo")),
            actor.get("organization_id"),
            list(actor.get("lead_workspaces") or []),
        )
    return {str(r["id"]): _memoria(r) for r in rows}


async def _previas(raices: list[str], conocidas: set[str], actor: dict, presupuesto: int) -> tuple[dict, bool]:
    """#1118: para cada vigente, las memorias que la sustituye buscando al revés por la marca, ronda a
    ronda (A→B→vigente da B y A), con la visibilidad de quien pregunta. Devuelve ({vigente: [memorias]},
    si se cortó por el tope de memorias leídas). Lo ya visto por el camino de delante no se repite."""
    previas: dict[str, list[dict]] = {r: [] for r in raices}
    raiz_de = {r: r for r in raices}
    frontera, cortado = list(raices), False
    pool = await get_pool()
    for _ in range(_vig.MAX_SALTOS):
        if not frontera or presupuesto <= 0:
            cortado = cortado or bool(frontera)
            break
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                _PREVIAS_SQL,
                frontera,
                int(actor["sub"]),
                bool(actor.get("is_super")),
                bool(actor.get("is_ceo")),
                actor.get("organization_id"),
                list(actor.get("lead_workspaces") or []),
            )
        frontera = []
        for r in rows:
            m = _memoria(r)
            if m["id"] in raiz_de:  # ciclo o ya encontrada
                continue
            if presupuesto <= 0:
                cortado = True
                break
            presupuesto -= 1
            raiz = raiz_de[str(m["metadata"]["superseded_by"])]
            raiz_de[m["id"]] = raiz
            if m["id"] not in conocidas:  # las del camino de delante ya están; solo abren camino hacia atrás
                previas[raiz].append(m)
            frontera.append(m["id"])
    return previas, cortado


@router.get("/vigentes")
async def decisiones_vigentes(
    tema: str = Query(
        ..., min_length=search.MIN_QUERY_LEN, max_length=search.MAX_QUERY_LEN, description="De qué trata (texto libre)."
    ),
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

    # #1098: candidatas por el camino propio (vector + texto, sin grafo) y umbral de esta mitad.
    candidatas_puntuadas = _relevantes(await _candidatas(tema, agente, actor), tema)
    puntos = {c["id"]: c for c in candidatas_puntuadas}
    orden = [c["id"] for c in candidatas_puntuadas][: min(limit * 3, MAX_POR_BUSQUEDA)]
    if not orden:
        avisos.append("sin decisiones relevantes en EcoDB para este tema")

    # Lee las candidatas y sigue las cadenas por rondas, con tope de saltos y de memorias leídas.
    vistas: dict[str, dict] = {}
    pedidas: set[str] = set()
    pendientes = orden
    for _ in range(_vig.MAX_SALTOS + 1):
        nuevas = [i for i in dict.fromkeys(pendientes) if i not in pedidas]
        if not nuevas:
            break
        if len(pedidas) + len(nuevas) > MAX_LEIDAS:
            avisos.append(
                f"más de {MAX_LEIDAS} memorias que leer: se cortó la lectura; "
                "las cadenas sin terminar salen en «errores»"
            )
            nuevas = nuevas[: MAX_LEIDAS - len(pedidas)]
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
    # #1118: lo que sustituye cada vigente aunque no sea decisión ni acuerdo (las candidatas no cambian).
    raices = [f["id"] for f in resultado["vigentes"]]
    previas, cortado = await _previas(raices, set(vistas), actor, MAX_LEIDAS - len(pedidas))
    _vig.con_previas(resultado, previas)
    for fila in resultado["vigentes"]:  # #1098: la puntuación de la candidata que llevó a esta fila
        origen = next((puntos[i] for i in [fila["id"], *fila.get("sustituye_a", [])] if i in puntos), None)
        if origen is not None:
            fila["puntuacion"] = round(origen["cos"] or 0.0, 3)
            fila["por"] = "ambos" if origen["r_vec"] and origen["r_txt"] else ("vector" if origen["r_vec"] else "texto")
    if cortado:
        avisos.append(f"más de {MAX_LEIDAS} memorias que leer: «sustituye_a» puede venir incompleto")
    resultado["avisos"] = avisos
    return resultado
