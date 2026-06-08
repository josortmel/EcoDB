"""Cell telemetry endpoint — metacognicion v2.0 §7.9."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from auth import get_current_user
from db import get_pool


router = APIRouter(prefix="/cells", tags=["cells"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CellRunSummary(BaseModel):
    run_id: UUID
    cell_type: str
    agent_identifier: Optional[str] = None
    model: str
    prompt_version: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    tokens_used: Optional[int] = None
    cost_usd: Optional[float] = None
    items_created: int
    errors: list = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)


class CellHealthResponse(BaseModel):
    last_run_by_type: dict[str, Optional[datetime]]
    errors_24h: int
    total_cost_30d: Optional[float] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _paginate(conn, base_sql, params, limit, cursor=None):
    if cursor:
        try:
            params.append(datetime.fromisoformat(cursor))
        except (ValueError, TypeError):
            from fastapi import HTTPException
            raise HTTPException(422, "invalid cursor format")
        base_sql += f" AND cr.created_at < ${len(params)}"
    base_sql += f" ORDER BY cr.created_at DESC LIMIT ${len(params)+1}"
    params.append(limit + 1)
    rows = await conn.fetch(base_sql, *params)
    has_next = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1]["created_at"].isoformat() if has_next and items else None
    return items, next_cursor


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/runs")
async def list_cell_runs(
    cell_type: Optional[str] = Query(None),
    agent_identifier: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    actor: dict = Depends(get_current_user),
) -> dict:
    is_super = actor.get("is_super")
    pool = await get_pool()
    async with pool.acquire() as conn:
        conditions = ["1=1"]
        params: list = []
        if not is_super:
            params.append(int(actor["sub"]))
            conditions.append(f"a.user_id = ${len(params)}")
        if cell_type:
            params.append(cell_type)
            conditions.append(f"cr.cell_type = ${len(params)}")
        if agent_identifier:
            params.append(agent_identifier)
            conditions.append(f"a.identifier = ${len(params)}")
        where = " AND ".join(conditions)
        items, next_cursor = await _paginate(conn, f"""
            SELECT cr.*, a.identifier AS agent_identifier
            FROM cell_runs cr LEFT JOIN agents a ON a.id = cr.agent_id
            WHERE {where}
        """, params, limit, cursor)
    return {"items": [dict(r) for r in items], "cursor_next": next_cursor}


@router.get("/health")
async def cell_health(actor: dict = Depends(get_current_user)) -> CellHealthResponse:
    is_super = actor.get("is_super")
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent_filter = ""
        params: list = []
        if not is_super:
            params.append(int(actor["sub"]))
            agent_filter = f"AND cr.agent_id IN (SELECT id FROM agents WHERE user_id=${len(params)})"

        last_by_type = {}
        for ct in ('consolidation', 'foresight', 'skill_distillation'):
            row = await conn.fetchrow(f"""
                SELECT MAX(finished_at) AS last FROM cell_runs cr
                WHERE cr.cell_type=$1 AND cr.status='completed' {agent_filter}
            """, ct, *params)
            last_by_type[ct] = row["last"].isoformat() if row and row["last"] else None

        errors_24h = await conn.fetchval(f"""
            SELECT COUNT(*) FROM cell_runs cr
            WHERE cr.status='failed' AND cr.started_at > NOW()-INTERVAL '24 hours' {agent_filter}
        """, *params)

        cost_30d = await conn.fetchval(f"""
            SELECT SUM(cost_usd) FROM cell_runs cr
            WHERE cr.started_at > NOW()-INTERVAL '30 days' {agent_filter}
        """, *params)

    return {"last_run_by_type": last_by_type, "errors_24h": errors_24h,
            "total_cost_30d": float(cost_30d) if cost_30d else None}
