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

from datetime import datetime, timezone
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from auth import get_current_user
from db import get_pool


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
