"""Endpoints agent_identity — .3.1 + §3.1.

Identidad de agentes: fragmentos versionados. Cada `version` es un snapshot
completo (no parche). Schema en init.sql §1.3.1:

    agent_identity(id, agent_id FK agents, organization_id NULLABLE FK orgs,
                   version, fragment_idx, content, timestamps,
                   UNIQUE NULLS NOT DISTINCT (agent_id, org_id, version, fragment_idx))

Single-tenant mode: organization_id is always NULL (global base identity).
Fork multi-tenant futuro: identidad puede variar por org. YAGNI ahora.

Endpoints:
- GET  /agents/{agent_identifier}/identity   → version máxima por default,
                                                ?version=N opcional para histórico.
- POST /agents/{agent_identifier}/identity   → snapshot completo nueva version
                                                auto-incrementada. 201 Created.

Permisos :
- super: cualquier agent.
- propio: agent.user_id == jwt.sub (el user dueño del agent).
- CEO/Lead/Worker: NO. La identidad es del agente, no del negocio.

Design decisions:
- Snapshot completo por version (no parche por fragment_idx). Atomicidad +
  rollback trivial cargando version anterior.
- ORDER BY fragment_idx ASC en GET (orden narrativo identidad).
- Sin truncar fragmentos (TEXT en BD lo cumple naturalmente).
- Una sola llamada (todos los fragmentos en una response).
- Sin headers sintéticos hash|autor falsos en MCP (el schema
  no tiene title/hash, inventarlos sería metadata falsa). Texto concatenado
  con `\\n\\n---\\n\\n` en la tool MCP, no en el endpoint REST.

Hardening:
- 404 sin distinguir "no existe" vs "existe sin permiso" (anti discovery oracle
  de identifiers de agents — adv-seg invariante L1).
- Validación tamaño por fragmento (MAX_FRAGMENT_SIZE = 32KB) y por version
  (MAX_FRAGMENTS_PER_VERSION = 100). Anti-DoS storage.
- Null bytes rechazados en content (rompen JSONB downstream + parsers).
- Auto-increment version dentro de transaction (UNIQUE constraint del schema
  protege contra race; UniqueViolationError → 409 limpio).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth import get_current_user
from db import get_pool
from permissions import can_read_memory, can_write_memory, precompute_read_visibility, check_read_memory


# Límites duros (DoS prevention + sanity).
MAX_FRAGMENT_SIZE = 32_000          # 32KB por fragmento individual.
MAX_FRAGMENTS_PER_VERSION = 100      # Identidad típica = ~10-15 fragmentos.
MAX_AGENT_IDENTIFIER_LEN = 200       # `agents.identifier` es TEXT, sin límite duro en schema.


router = APIRouter(prefix="/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class IdentityFragment(BaseModel):
    """Un fragmento individual de identidad. Devuelto en GET."""
    model_config = ConfigDict(extra="forbid")
    fragment_idx: int = Field(..., ge=0)
    content: str


class IdentityResponse(BaseModel):
    """Response de GET /agents/{id}/identity."""
    agent_identifier: str
    agent_id: int
    version: int
    fragments: list[IdentityFragment]


class IdentityCreate(BaseModel):
    """Body de POST /agents/{id}/identity. Lista de strings — fragment_idx
    auto-asignado por orden (cliente NO gestiona idx)."""
    model_config = ConfigDict(extra="forbid")
    fragments: list[str] = Field(
        ...,
        min_length=1,
        max_length=MAX_FRAGMENTS_PER_VERSION,
        description="Lista de fragmentos en orden narrativo. fragment_idx auto = posición en lista.",
    )


class IdentityCreateResponse(BaseModel):
    """Response de POST /agents/{id}/identity (201)."""
    agent_identifier: str
    agent_id: int
    version: int
    fragments_count: int
    created_at: datetime


class AgentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cognition_class: Optional[str] = Field(None, pattern="^(narrative|work|mixed)$")


class ObservedTrait(BaseModel):
    dimension: str
    observed_value: str
    evidence_count: int
    last_seen: datetime
    confidence: float


class ObservedIdentityResponse(BaseModel):
    agent_identifier: str
    traits: list[ObservedTrait]
    computed_at: Optional[datetime] = None


class TensionAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(..., pattern="^(resolve|dismiss)$")
    note: Optional[str] = Field(None, max_length=1000)

    @field_validator("note")
    @classmethod
    def _no_nulls(cls, v):
        if v is not None and "\x00" in v:
            raise ValueError("note contains null bytes")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_agent_or_404(conn, actor: dict, agent_identifier: str) -> dict:
    """Resuelve agent_identifier → row de agents + verifica permisos.

    404 igual para "no existe" y "existe sin
    permiso" — evita discovery oracle de identifiers válidos. super bypasea.
    """
    row = await conn.fetchrow(
        "SELECT id, identifier, user_id FROM agents WHERE identifier = $1 AND active = true",
        agent_identifier,
    )
    if row is None:
        raise HTTPException(404, f"agent {agent_identifier!r} not found")
    if actor.get("is_super"):
        return dict(row)
    if row["user_id"] is not None and int(row["user_id"]) == int(actor["sub"]):
        return dict(row)
    # Existe pero el actor no es dueño. 404 anti-discovery.
    raise HTTPException(404, f"agent {agent_identifier!r} not found")


# ---------------------------------------------------------------------------
# GET /agents/{agent_identifier}/identity
# ---------------------------------------------------------------------------

@router.get("/{agent_identifier}/identity", response_model=IdentityResponse)
async def get_identity(
    agent_identifier: str = Path(..., min_length=1, max_length=MAX_AGENT_IDENTIFIER_LEN),
    version: Optional[int] = Query(None, ge=1, description="Si None, devuelve version máxima."),
    actor: dict = Depends(get_current_user),
) -> IdentityResponse:
    """Lee identidad del agent. Devuelve version máxima por default + ?version=N
    opcional para histórico. Fragmentos ordenados ASC por fragment_idx (requirement
    Eco vinculante: orden narrativo).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await _resolve_agent_or_404(conn, actor, agent_identifier)
        agent_id = int(agent["id"])

        if version is None:
            target_version = await conn.fetchval(
                "SELECT MAX(version) FROM agent_identity "
                "WHERE agent_id = $1 AND organization_id IS NULL",
                agent_id,
            )
            if target_version is None:
                # Agent existe pero sin fragmentos guardados todavía.
                return IdentityResponse(
                    agent_identifier=agent_identifier,
                    agent_id=agent_id,
                    version=0,
                    fragments=[],
                )
        else:
            target_version = version

        rows = await conn.fetch(
            """
            SELECT fragment_idx, content
            FROM agent_identity
            WHERE agent_id = $1 AND organization_id IS NULL AND version = $2
            ORDER BY fragment_idx ASC
            """,
            agent_id, target_version,
        )

    if not rows:
        raise HTTPException(
            404,
            f"version {target_version} not found for agent {agent_identifier!r}",
        )

    fragments = [
        IdentityFragment(fragment_idx=r["fragment_idx"], content=r["content"])
        for r in rows
    ]
    return IdentityResponse(
        agent_identifier=agent_identifier,
        agent_id=agent_id,
        version=int(target_version),
        fragments=fragments,
    )


# ---------------------------------------------------------------------------
# POST /agents/{agent_identifier}/identity
# ---------------------------------------------------------------------------

@router.post(
    "/{agent_identifier}/identity",
    response_model=IdentityCreateResponse,
    status_code=201,
)
async def create_identity_version(
    body: IdentityCreate,
    agent_identifier: str = Path(..., min_length=1, max_length=MAX_AGENT_IDENTIFIER_LEN),
    actor: dict = Depends(get_current_user),
) -> IdentityCreateResponse:
    """Crea nueva version snapshot. Lista de strings → fragment_idx auto por orden.

    422 si:
    - cualquier fragmento > MAX_FRAGMENT_SIZE.
    - cualquier fragmento contiene null bytes.

    404 si agent no existe / actor no es dueño.

    409 si race condition en auto-increment (UNIQUE violation del schema). Cliente
    reintenta. Single-tenant single-user es escenario raro pero correcto cubrirlo.
    """
    for idx, frag in enumerate(body.fragments):
        if "\x00" in frag:
            raise HTTPException(422, f"fragment {idx} contains null bytes")
        if len(frag.encode("utf-8")) > MAX_FRAGMENT_SIZE:
            raise HTTPException(
                422,
                f"fragment {idx} exceeds MAX_FRAGMENT_SIZE={MAX_FRAGMENT_SIZE} bytes",
            )

    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await _resolve_agent_or_404(conn, actor, agent_identifier)
        agent_id = int(agent["id"])

        try:
            async with conn.transaction():
                current_max = await conn.fetchval(
                    "SELECT COALESCE(MAX(version), 0) FROM agent_identity "
                    "WHERE agent_id = $1 AND organization_id IS NULL",
                    agent_id,
                )
                new_version = int(current_max) + 1

                for idx, content in enumerate(body.fragments):
                    await conn.execute(
                        """
                        INSERT INTO agent_identity
                            (agent_id, organization_id, version, fragment_idx, content)
                        VALUES ($1, NULL, $2, $3, $4)
                        """,
                        agent_id, new_version, idx, content,
                    )
            await conn.execute(
                """INSERT INTO audit_log (user_id, action, resource, resource_id, details, organization_id)
                VALUES ($1, 'save_identity', 'agent', $2, $3::jsonb, $4)""",
                int(actor["sub"]), agent_identifier,
                json.dumps({"version": new_version, "fragments_count": len(body.fragments)}),
                actor.get("organization_id"),
            )
        except asyncpg.UniqueViolationError:
            # Race en auto-increment: otro POST concurrente ganó la version.
            raise HTTPException(409, "version conflict — retry")

    return IdentityCreateResponse(
        agent_identifier=agent_identifier,
        agent_id=agent_id,
        version=new_version,
        fragments_count=len(body.fragments),
        created_at=datetime.now(timezone.utc),
    )


@router.patch("/{agent_identifier}")
async def patch_agent(
    agent_identifier: str,
    body: AgentPatch,
    actor: dict = Depends(get_current_user),
) -> dict:
    if body.cognition_class is None:
        raise HTTPException(400, "no fields to update")
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await _resolve_agent_or_404(conn, actor, agent_identifier)
        await conn.execute(
            "UPDATE agents SET cognition_class=$1 WHERE id=$2",
            body.cognition_class, agent["id"])
    return {"ok": True, "agent_identifier": agent_identifier}


@router.get("/{agent_identifier}/observed-identity")
async def get_observed_identity(
    agent_identifier: str = Path(..., min_length=1, max_length=200),
    actor: dict = Depends(get_current_user),
) -> ObservedIdentityResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await _resolve_agent_or_404(conn, actor, agent_identifier)
        agent_id = agent["id"]
        traits = []

        # 1. Type distribution (last 90 days)
        type_dist = await conn.fetch("""
            SELECT type::text, COUNT(*) AS cnt FROM memories
            WHERE agent_id=$1 AND created_at > NOW()-INTERVAL '90 days'
            GROUP BY type ORDER BY cnt DESC
        """, agent_id)
        if type_dist:
            total = sum(r["cnt"] for r in type_dist)
            traits.append({
                "dimension": "type_distribution",
                "observed_value": ", ".join(f"{r['type']}:{r['cnt']}" for r in type_dist),
                "evidence_count": total,
                "last_seen": datetime.now(timezone.utc),
                "confidence": min(total / 50, 1.0),
            })

        # 2. Top entities via memory_entity_links
        top_entities = await conn.fetch("""
            SELECT n.name, COUNT(*) AS cnt FROM memory_entity_links mel
            JOIN memories m ON m.id = mel.memory_id
            JOIN nodes n ON n.id = mel.entity_node_id
            WHERE m.agent_id=$1 AND m.created_at > NOW()-INTERVAL '90 days'
              AND n.status='active'
            GROUP BY n.name ORDER BY cnt DESC LIMIT 10
        """, agent_id)
        if top_entities:
            traits.append({
                "dimension": "top_entities",
                "observed_value": ", ".join(f"{r['name']}:{r['cnt']}" for r in top_entities),
                "evidence_count": sum(r["cnt"] for r in top_entities),
                "last_seen": datetime.now(timezone.utc),
                "confidence": min(len(top_entities) / 10, 1.0),
            })

        # 3. Top predicates via triples
        top_preds = await conn.fetch("""
            SELECT t.predicate, COUNT(*) AS cnt FROM triples t
            WHERE t.author = $1
            GROUP BY t.predicate ORDER BY cnt DESC LIMIT 10
        """, agent_identifier)
        if top_preds:
            traits.append({
                "dimension": "top_predicates",
                "observed_value": ", ".join(f"{r['predicate']}:{r['cnt']}" for r in top_preds),
                "evidence_count": sum(r["cnt"] for r in top_preds),
                "last_seen": datetime.now(timezone.utc),
                "confidence": min(len(top_preds) / 10, 1.0),
            })

        # 4. Weight distribution
        weight_stats = await conn.fetchrow("""
            SELECT AVG(weight) AS avg_w, STDDEV(weight) AS std_w,
                   MIN(weight) AS min_w, MAX(weight) AS max_w
            FROM memories WHERE agent_id=$1 AND created_at > NOW()-INTERVAL '90 days'
        """, agent_id)
        if weight_stats and weight_stats["avg_w"]:
            traits.append({
                "dimension": "weight_distribution",
                "observed_value": f"avg:{weight_stats['avg_w']:.2f} std:{(weight_stats['std_w'] or 0):.2f} min:{weight_stats['min_w']:.2f} max:{weight_stats['max_w']:.2f}",
                "evidence_count": await conn.fetchval(
                    "SELECT COUNT(*) FROM memories WHERE agent_id=$1 AND created_at > NOW()-INTERVAL '90 days'",
                    agent_id),
                "last_seen": datetime.now(timezone.utc),
                "confidence": 0.9,
            })

        # 5. Temporal patterns (day of week activity)
        temporal = await conn.fetch("""
            SELECT EXTRACT(DOW FROM created_at)::int AS dow, COUNT(*) AS cnt
            FROM memories WHERE agent_id=$1 AND created_at > NOW()-INTERVAL '90 days'
            GROUP BY dow ORDER BY cnt DESC
        """, agent_id)
        if temporal:
            day_names = ["dom", "lun", "mar", "mie", "jue", "vie", "sab"]
            traits.append({
                "dimension": "temporal_pattern",
                "observed_value": ", ".join(f"{day_names[r['dow']]}:{r['cnt']}" for r in temporal),
                "evidence_count": sum(r["cnt"] for r in temporal),
                "last_seen": datetime.now(timezone.utc),
                "confidence": min(len(temporal) / 7, 1.0),
            })

        # Check precomputed observed_identity from latest cluster
        precomp = await conn.fetchrow("""
            SELECT metadata->'observed_identity' AS obs, created_at
            FROM memory_clusters
            WHERE agent_id=$1 AND status='active' AND metadata ? 'observed_identity'
            ORDER BY created_at DESC LIMIT 1
        """, agent_id)
        computed_at = precomp["created_at"] if precomp else None

    return {"agent_identifier": agent_identifier, "traits": traits,
            "computed_at": computed_at}


@router.get("/{agent_identifier}/tensions")
async def get_tensions(
    agent_identifier: str = Path(..., min_length=1, max_length=200),
    status: Optional[str] = Query(None, pattern="^(open|resolved|dismissed)$"),
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await _resolve_agent_or_404(conn, actor, agent_identifier)
        conditions = ["agent_id = $1", "'identity_tension' = ANY(tags)"]
        params: list = [agent["id"]]
        if status:
            if status == "open":
                conditions.append(
                    "(metadata->>'tension_status' IS NULL OR metadata->>'tension_status' = 'open')")
            else:
                params.append(status)
                conditions.append(f"metadata->>'tension_status' = ${len(params)}")
        where = " AND ".join(conditions)
        rows = await conn.fetch(f"""
            SELECT * FROM memories WHERE {where}
            ORDER BY created_at DESC LIMIT 20
        """, *params)
        vis = await precompute_read_visibility(conn, actor)
        visible = [dict(r) for r in rows if check_read_memory(vis, r)]
    return {"items": visible, "total": len(visible)}


@router.put("/{agent_identifier}/tensions/{tension_id}")
async def resolve_tension(
    agent_identifier: str, tension_id: UUID,
    body: TensionAction, actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await _resolve_agent_or_404(conn, actor, agent_identifier)
        mem = await conn.fetchrow("SELECT * FROM memories WHERE id=$1", tension_id)
        if mem is None or 'identity_tension' not in (mem["tags"] or []):
            raise HTTPException(404)
        if mem["agent_id"] != agent["id"]:
            raise HTTPException(404)
        if not await can_write_memory(conn, actor, mem):
            raise HTTPException(403)
        status_map = {"resolve": "resolved", "dismiss": "dismissed"}
        update = {"tension_status": status_map[body.action]}
        if body.action == "dismiss":
            update["tension_cooldown_until"] = (
                datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        if body.note:
            update["tension_note"] = body.note
        await conn.execute("""
            UPDATE memories SET metadata = coalesce(metadata,'{}'::jsonb) || $1::jsonb,
              updated_at = NOW() WHERE id = $2
        """, json.dumps(update), tension_id)
    return {"ok": True}
