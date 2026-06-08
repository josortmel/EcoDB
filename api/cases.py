"""Cases endpoint — metacognicion v2.0 §7.6."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth import get_current_user
from db import get_pool
from permissions import resolve_agent_for_actor, precompute_read_visibility, check_read_memory


router = APIRouter(prefix="/cases", tags=["cases"])


class CaseResponse(BaseModel):
    id: UUID
    content: str
    task_type: Optional[str] = None
    steps: Optional[list[str]] = None
    result: Optional[str] = None
    success: Optional[bool] = None
    skill_id: Optional[UUID] = None
    created_at: datetime


def _safe_uuid(val) -> UUID | None:
    if val is None:
        return None
    try:
        return UUID(val)
    except (ValueError, AttributeError):
        return None


async def _paginate(conn, base_sql, params, limit, cursor=None):
    if cursor:
        try:
            params.append(datetime.fromisoformat(cursor))
        except (ValueError, TypeError):
            from fastapi import HTTPException
            raise HTTPException(422, "invalid cursor format")
        base_sql += f" AND created_at < ${len(params)}"
    base_sql += f" ORDER BY created_at DESC LIMIT ${len(params)+1}"
    params.append(limit + 1)
    rows = await conn.fetch(base_sql, *params)
    has_next = len(rows) > limit
    items = rows[:limit]
    next_cursor = items[-1]["created_at"].isoformat() if has_next and items else None
    return items, next_cursor


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
        items, next_cursor = await _paginate(conn,
            f"SELECT * FROM memories WHERE {where}", params, limit, cursor)
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
    return {"items": visible, "total": len(visible), "cursor_next": next_cursor}
