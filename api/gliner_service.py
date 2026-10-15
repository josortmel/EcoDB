"""Servicio GLiNER para extraccion de entidades multilingual.

Architecture E (lookup-first GLiNER): dictionary lookup runs first; unmatched
spans go to GLiNER. This avoids post-processing overrides on GLiNER output.

Flujo:
1. Cache del diccionario en RAM al arranque uvicorn (lifespan FastAPI).
   Endpoint /admin/entity-dictionary/reload super-only para invalidacion.
2. `_match_dictionary(text, dict_cache)`:
   - Diccionario ordenado por len(name) DESC → longest-match wins
     (e.g. "eco consulting" matches before standalone "eco").
   - Regex `(?<!\\w){re.escape(name)}(?!\\w)` por entry — borde de palabra CRITICO
     (coord+verificador+adv-seg convergentes: sin el "Eco" matchea
     "Ecosistema" → falso positivo silencioso), buscado sobre el texto plegado
     sin tildes y de la misma longitud (#478).
3. Spans matcheados → tipo del diccionario, sin GLiNER.
4. Texto residual: spans REEMPLAZADOS con espacios mismo largo (NO eliminados).
   Coord+adv-seg: preserva offsets + evita fusion tokens fantasma en frontera.
5. GLiNER procesa el texto-con-espacios. Whitespace redundante normalizado por
   tokenizer naturalmente.
6. Merge: lista final con `source="dictionary"|"gliner"` por entidad
   (provenance — coord+verificador+adv-code, coste cero, valor audit + debug).

GLiNER labels: 6 categories (persona, organizacion, lugar, producto, proyecto,
agente_ia). Threshold 0.7 (raised from 0.5 — discards weak classifications that
appear confident in polysemous Spanish).

Architectural decision: GLiNER runs INSIDE the API container (dedicated container
discarded — symmetry with embeddings is cargo cult, GLiNER is CPU 209MB with no
GPU justification). Lazy load: FastAPI starts,
/health responde, GLiNER carga al primer use desde named volume api_hf_cache.

Modelo: urchade/gliner_multi-v2.1 (multilingual con español).
"""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import re
from typing import Optional

import asyncpg
import httpx

from entity_normalization import normalize_name
from settings import NER_SERVICE_URL


logger = logging.getLogger(__name__)


# GLiNER entity labels in Spanish. Must match the allowlist in entity_normalization.py.
DEFAULT_LABELS = ["persona", "organizacion", "lugar", "producto", "proyecto", "agente_ia"]
# Threshold subido de 0.5 a 0.7.
DEFAULT_THRESHOLD = 0.7

MODEL_NAME = os.getenv("GLINER_MODEL", "urchade/gliner_multi-v2.1")

_ALIAS_SIM_THRESHOLD = 0.65
_ALIAS_MAX_CANDIDATES = 3


async def _call_ner(text: str, labels: list[str], threshold: float) -> list[dict]:
    """Call GLiNER microservice for entity extraction."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{NER_SERVICE_URL}/extract",
                json={"text": text, "labels": labels, "threshold": threshold},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        logger.warning("NER service call failed: %r — returning empty entities", exc)
        return []


# Cache RAM del diccionario entity_dictionary.
# Estructura: lista de tuplas (name_original, name_normalized, entity_type)
# ordenada por len(name_normalized) DESC — longest-match wins.
# Compilado: lista de tuplas (regex_compilada, entity_type, name_original).
_dictionary_cache: list[tuple[re.Pattern, str, str]] = []
_dictionary_lock = asyncio.Lock()


async def load_dictionary_to_cache(pool: asyncpg.Pool) -> int:
    """Carga el diccionario desde BD al cache RAM, ordenado y precompilado.

    Llamada al arranque uvicorn (lifespan FastAPI) y al endpoint
    /admin/entity-dictionary/reload (super-only). Invalidacion explicita.

    Returns: numero de entradas cargadas en cache.
    """
    global _dictionary_cache
    async with _dictionary_lock:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT name, name_normalized, entity_type FROM entity_dictionary"
            )
        # Ordenar por len(name_normalized) DESC — longest match wins.
        sorted_rows = sorted(rows, key=lambda r: len(r["name_normalized"]), reverse=True)
        compiled: list[tuple[re.Pattern, str, str]] = [
            (_compile_dictionary_pattern(r["name_normalized"]), r["entity_type"], r["name"])
            for r in sorted_rows
        ]
        _dictionary_cache = compiled
        logger.info("Entity dictionary cache loaded: %d entries", len(compiled))
        return len(compiled)


def _compile_dictionary_pattern(name_normalized: str) -> re.Pattern:
    """Regex de una entrada, buscada sobre el texto plegado (_fold_same_length).

    #478: bordes con (?<!\\w)…(?!\\w) y no con \\b…\\b. \\b exige una letra al lado, así que
    una entrada que empieza o acaba en un signo («… (Shakker-Labs)») no casaba nunca.
    re.escape evita que los caracteres especiales del nombre rompan el regex.
    """
    return re.compile(r"(?<!\w)" + re.escape(name_normalized) + r"(?!\w)")


@functools.lru_cache(maxsize=8192)
def _fold_char(c: str) -> str:
    n = normalize_name(c)
    if len(n) == 1:
        return n
    low = c.lower()
    return low if len(low) == 1 else c


def _fold_same_length(text: str) -> str:
    """Minúsculas y sin tildes carácter a carácter, CONSERVANDO la longitud (#478).

    Cada carácter pasa por normalize_name si eso da exactamente un carácter («É»→«e»,
    «ñ»→«n», «ō»→«o»); si no (una ligadura como «ﬁ», una tilde suelta de un texto NFD,
    un espacio), se queda en minúscula o como está, y simplemente no casa. Al tener la
    misma longitud, los offsets del texto plegado son los del original.
    """
    return "".join(_fold_char(c) for c in text)


def dictionary_rows_to_renormalize(rows) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """(arreglos, choques) para las entradas cuyo name_normalized no es normalize_name(name).

    La siembra del 15-may no pasó por normalize_name (17 entradas con la tilde dentro).
    Si la clave buena ya la tiene otra entrada (índice único), no se toca y se avisa.
    """
    taken = {r["name_normalized"] for r in rows}
    fixes: list[tuple[int, str]] = []
    collisions: list[tuple[int, str]] = []
    for r in rows:
        want = normalize_name(r["name"])
        if want == r["name_normalized"]:
            continue
        if want in taken:
            collisions.append((r["id"], want))
            continue
        taken.discard(r["name_normalized"])
        taken.add(want)
        fixes.append((r["id"], want))
    return fixes, collisions


async def renormalize_dictionary(pool: asyncpg.Pool) -> int:
    """Pone name_normalized = normalize_name(name) donde no lo está. Idempotente.

    Va en el arranque, antes de cargar el cache: el arreglo de la búsqueda (#478) y el de
    estas entradas tienen que entrar a la vez, porque por separado cada uno rompe algo.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, name_normalized FROM entity_dictionary")
        fixes, collisions = dictionary_rows_to_renormalize(rows)
        for entry_id, want in collisions:
            logger.warning("entity_dictionary %d: normalize_name gives %r, already taken; left as is",
                           entry_id, want)
        if fixes:
            async with conn.transaction():
                for entry_id, want in fixes:
                    await conn.execute(
                        "UPDATE entity_dictionary SET name_normalized = $2, updated_at = now() WHERE id = $1",
                        entry_id, want,
                    )
            logger.info("entity_dictionary: %d entries renormalized", len(fixes))
    return len(fixes)


def _match_dictionary(text: str) -> tuple[list[dict], str]:
    """Busca matches del diccionario en el texto y devuelve (entidades, texto_residual).

    El texto_residual tiene los spans matcheados REEMPLAZADOS con espacios de
    la misma longitud. Preserva offsets del texto original para que las
    entidades de GLiNER mantengan posiciones correctas. Tokens en frontera no
    se fusionan (if "foo bar" is deleted, "foobar" tokens recombine; with spaces
    "      bar" tokens stay separated).

    Returns:
        (entities, text_residual): entities con source="dictionary".
        text_residual con espacios donde habia matches.
    """
    if not text or not _dictionary_cache:
        return [], text
    # Las entradas están sin tildes (normalize_name). Se busca sobre el texto plegado
    # carácter a carácter, que tiene la MISMA longitud que el original: los offsets del
    # match sirven tal cual para sacar text[start:end] con su tilde y su mayúscula (#478;
    # antes se buscaba sobre text.lower(), que conserva las tildes, y «España» no casaba
    # con «espana»).
    text_folded = _fold_same_length(text)
    entities: list[dict] = []
    consumed_ranges: list[tuple[int, int]] = []
    # Iterar diccionario ordenado por longitud DESC (longest-match wins).
    for pattern, entity_type, name_original in _dictionary_cache:
        for match in pattern.finditer(text_folded):
            start, end = match.start(), match.end()
            # Verificar que este span no se solapa con uno ya consumido (un
            # match mas largo que ya pillo este rango). Como iteramos DESC,
            # los mas largos van primero — los cortos solo entran si no
            # solapan.
            if any(cs <= start < ce or cs < end <= ce for cs, ce in consumed_ranges):
                continue
            consumed_ranges.append((start, end))
            entities.append({
                "text": text[start:end],  # extraido del original con case/tilde
                "label": entity_type,
                "start": start,
                "end": end,
                "score": 1.0,  # diccionario = 100% confianza
                "source": "dictionary",
            })
    # Construir texto residual: reemplazar spans consumidos con espacios mismo largo.
    consumed_ranges.sort()
    chars = list(text)
    for start, end in consumed_ranges:
        for i in range(start, end):
            chars[i] = " "
    text_residual = "".join(chars)
    return entities, text_residual


async def extract_entities(
    text: str,
    labels: Optional[list[str]] = None,
    threshold: float = DEFAULT_THRESHOLD,
    dictionary_only: bool = False,
) -> list[dict]:
    """Extrae entidades del texto via arquitectura E lookup-first.

    Args:
        text: contenido a procesar.
        labels: etiquetas a buscar para GLiNER. Si None, usa DEFAULT_LABELS.
        threshold: score minimo para GLiNER (0.0-1.0). Default 0.7.
        dictionary_only: si True, retorna solo matches del diccionario
            sin invocar GLiNER. Usado para re-indexado retroactivo seguro.

    Returns:
        Lista de dicts con keys: text, label, start, end, score, source.
        source = "dictionary" | "gliner" (provenance — coste cero, valor audit).
    """
    if not text or not text.strip():
        return []
    if labels is None:
        labels = DEFAULT_LABELS

    # Paso 1-3: lookup-first contra diccionario en cache RAM.
    dict_entities, text_residual = _match_dictionary(text)

    if dictionary_only is True:
        if not dict_entities and not _dictionary_cache:
            logger.warning("dictionary_only=True but dictionary cache is empty — returning []")
        return dict_entities

    # Paso 4-5: GLiNER procesa el texto residual (con espacios donde estaban
    # los matches del diccionario).
    if not text_residual.strip():
        # El diccionario consumio todo el contenido relevante — no hay nada
        # mas que GLiNER pueda detectar. Skip GLiNER inferencia.
        return dict_entities

    gliner_raw = await _call_ner(text_residual, labels, threshold)
    # Anadir provenance.
    gliner_entities = [
        {
            "text": str(e["text"]),
            "label": str(e["label"]),
            "start": int(e["start"]),
            "end": int(e["end"]),
            "score": float(e["score"]),
            "source": "gliner",
        }
        for e in gliner_raw
    ]

    # Paso 6: merge. Diccionario primero, GLiNER segundo. Los offsets del
    # residual coinciden con los del original porque reemplazamos con espacios
    # (no eliminamos), preservando posiciones.
    return dict_entities + gliner_entities


# ---------------------------------------------------------------------------
# Task 4.5 — Sub-chunking + stop filter for ingestion pipeline
# ---------------------------------------------------------------------------

_SUB_CHUNK_MAX = 512
_SUB_CHUNK_OVERLAP_START = 448  # 512 - 64 overlap


def filter_stop_entities(entities: list[dict], stop_set: set[str]) -> list[dict]:
    """Remove entities matching stop_entities. stop_set = preloaded name_normalized values."""
    return [e for e in entities if normalize_name(e["text"]) not in stop_set]


async def extract_entities_from_chunks(chunks: list, pool: asyncpg.Pool) -> list[dict]:
    """Extract entities from document chunks using 2x512 sub-chunking.

    Each 960-token chunk → 2 windows of 512 tokens with 64 overlap:
      Window 1: tokens[0:512]
      Window 2: tokens[448:960]
    Chunk < 960 tokens: single window of actual size.

    Dedup: same entity (same text, case-insensitive) in both windows → keep higher score.
    Pipeline: entity_dictionary lookup-first → GLiNER residual → merge → stop filter.

    Returns: list of {chunk_index, entities: [{text, label, score, source}]}
    """
    import tiktoken as _tiktoken
    enc = _tiktoken.get_encoding("cl100k_base")

    # Load stop_set once for all chunks (BC2 — avoid N+1 DB queries)
    async with pool.acquire() as conn:
        stop_rows = await conn.fetch("SELECT name_normalized FROM stop_entities")
    stop_set = {r["name_normalized"] for r in stop_rows}

    results: list[dict] = []

    for chunk in chunks:
        tokens = enc.encode(chunk.content)

        if len(tokens) > _SUB_CHUNK_MAX:
            windows = [
                enc.decode(tokens[:_SUB_CHUNK_MAX]),
                enc.decode(tokens[_SUB_CHUNK_OVERLAP_START:]),
            ]
        else:
            windows = [chunk.content]

        # Extract entities per window, then dedup keeping higher score
        merged: dict[str, dict] = {}
        for window_text in windows:
            window_entities = await extract_entities(window_text)
            for ent in window_entities:
                key = normalize_name(ent["text"])
                if key not in merged or ent["score"] > merged[key]["score"]:
                    merged[key] = ent

        # Filter stop entities (stop_set already loaded — no extra DB query)
        chunk_entities = filter_stop_entities(list(merged.values()), stop_set)

        results.append({
            "chunk_index": chunk.chunk_index,
            "entities": chunk_entities,
        })

    # Task 5.9 — detect alias candidates across all extracted entities
    all_chunk_entities = [e for r in results for e in r["entities"]]
    await detect_alias_candidates(all_chunk_entities, pool)

    return results


async def detect_alias_candidates(entities: list[dict], pool: asyncpg.Pool) -> None:
    """Task 5.9 — Check extracted entity names against existing nodes via pg_trgm.

    Finds nodes with 0.80 ≤ similarity < 1.0 (similar but not identical).
    Inserts new pending candidates or increments occurrences on existing ones.
    Best-effort: logs and returns on any error.
    """
    if not entities:
        return
    names = list({e["text"] for e in entities if e.get("text")})
    if not names:
        return
    try:
        async with pool.acquire() as conn:
            for name in names:
                similar_rows = await conn.fetch(
                    """
                    SELECT id, similarity(name, $1) AS sim
                    FROM nodes
                    WHERE similarity(name, $1) >= $2
                      AND lower(name) != lower($1)
                      AND status = 'active'
                    ORDER BY sim DESC
                    LIMIT $3
                    """,
                    name, _ALIAS_SIM_THRESHOLD, _ALIAS_MAX_CANDIDATES,
                )
                for node in similar_rows:
                    confidence = float(node["sim"])
                    existing = await conn.fetchrow(
                        """SELECT id FROM entity_alias_candidates
                           WHERE source_name = $1 AND target_node_id = $2
                             AND status = 'pending'""",
                        name, node["id"],
                    )
                    if existing:
                        await conn.execute(
                            """UPDATE entity_alias_candidates
                               SET occurrences = occurrences + 1,
                                   confidence = GREATEST(confidence, $2),
                                   last_seen = now()
                               WHERE id = $1""",
                            existing["id"], confidence,
                        )
                    else:
                        await conn.execute(
                            """INSERT INTO entity_alias_candidates
                                   (source_name, target_node_id, confidence, occurrences)
                               VALUES ($1, $2, $3, 1)""",
                            name, node["id"], confidence,
                        )
    except Exception as exc:
        logger.warning("detect_alias_candidates failed: %r", exc)


async def scan_all_alias_candidates(
    pool: asyncpg.Pool,
    threshold: float = 0.65,
    max_per_name: int = 3,
    name_filter: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Scan all active nodes for alias candidates. User-triggered from dashboard.

    Args:
        pool: database pool.
        threshold: pg_trgm similarity threshold (0.0-1.0).
        max_per_name: max candidates per source name.
        name_filter: optional ILIKE pattern to filter node names.
        dry_run: if True, return candidates without inserting.

    Returns: {found, inserted, updated, total_existing_pending, candidates: [...]}
    """
    found = 0
    inserted = 0
    updated = 0
    preview: list[dict] = []

    try:
        async with pool.acquire() as conn:
            # Get candidate source names
            if name_filter:
                name_rows = await conn.fetch(
                    "SELECT name FROM nodes WHERE status = 'active' AND name ILIKE $1",
                    f"%{name_filter}%",
                )
            else:
                name_rows = await conn.fetch(
                    "SELECT name FROM nodes WHERE status = 'active'"
                )
            names = sorted({r["name"] for r in name_rows})

            for name in names:
                similar_rows = await conn.fetch(
                    """
                    SELECT id, name AS target_name, similarity(name, $1) AS sim
                    FROM nodes
                    WHERE similarity(name, $1) >= $2
                      AND lower(name) != lower($1)
                      AND status = 'active'
                    ORDER BY sim DESC
                    LIMIT $3
                    """,
                    name, threshold, max_per_name,
                )
                for node in similar_rows:
                    found += 1
                    confidence = float(node["sim"])
                    info = {
                        "source_name": name,
                        "target_node_id": node["id"],
                        "target_node_name": node["target_name"],
                        "confidence": round(confidence, 4),
                    }
                    if dry_run:
                        preview.append(info)
                        continue

                    existing = await conn.fetchrow(
                        """SELECT id, status FROM entity_alias_candidates
                           WHERE source_name = $1 AND target_node_id = $2
                           ORDER BY id DESC LIMIT 1""",
                        name, node["id"],
                    )
                    if existing:
                        new_status = "pending"
                        await conn.execute(
                            """UPDATE entity_alias_candidates
                               SET occurrences = occurrences + 1,
                                   confidence = GREATEST(confidence, $2),
                                   status = $3,
                                   last_seen = now(),
                                   reviewed_by = NULL
                               WHERE id = $1""",
                            existing["id"], confidence, new_status,
                        )
                        updated += 1
                    else:
                        await conn.execute(
                            """INSERT INTO entity_alias_candidates
                                   (source_name, target_node_id, confidence, occurrences)
                               VALUES ($1, $2, $3, 1)""",
                            name, node["id"], confidence,
                        )
                        inserted += 1

        existing_pending = 0
        if not dry_run:
            async with pool.acquire() as conn:
                existing_pending = await conn.fetchval(
                    "SELECT count(*) FROM entity_alias_candidates WHERE status = 'pending'"
                )

        result: dict = {
            "found": found,
            "inserted": inserted,
            "updated": updated,
            "total_pending": existing_pending,
        }
        if dry_run:
            result["candidates"] = preview
        return result

    except Exception as exc:
        logger.warning("scan_all_alias_candidates failed: %r", exc)
        raise


