"""Cases endpoint — metacognicion v2.0 §7.6."""
from __future__ import annotations

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from auth import get_current_user
from db import get_pool
from pagination import paginate
from permissions import resolve_agent_for_actor, precompute_read_visibility, check_read_memory
from shared_models import CaseResponse


router = APIRouter(prefix="/cases", tags=["cases"])


def _safe_uuid(val) -> UUID | None:
    if val is None:
        return None
    try:
        return UUID(val)
    except (ValueError, AttributeError):
        return None


@router.get("")
async def list_cases(
    agent_identifier: str = Query(..., min_length=1),
    task_type: Optional[str] = Query(None, max_length=200),
    success: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await resolve_agent_for_actor(conn, actor, agent_identifier)
        conditions = ["type = 'caso'", "agent_id = $1"]
        params: list = [agent["id"]]
        if task_type:
            params.append(json.dumps({"task_type": task_type}))
            conditions.append(f"metadata @> ${len(params)}::jsonb")
        if success is not None:
            params.append(json.dumps({"success": success}))
            conditions.append(f"metadata @> ${len(params)}::jsonb")
        where = " AND ".join(conditions)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM memories WHERE {where}", *params)
        items, next_cursor = await paginate(conn,
            f"SELECT * FROM memories WHERE {where}", list(params), limit, cursor)
        vis = await precompute_read_visibility(conn, actor)
        visible = []
        for r in items:
            if check_read_memory(vis, r):
                meta = r["metadata"] or {}
                visible.append(CaseResponse(
                    id=r["id"],
                    content=r["content"],
                    task_type=meta.get("task_type"),
                    steps=meta.get("steps"),
                    result=meta.get("result"),
                    success=meta.get("success"),
                    skill_id=_safe_uuid(meta.get("skill_id")),
                    created_at=r["created_at"],
                ))
    return {"items": visible, "total": total, "cursor_next": next_cursor}
