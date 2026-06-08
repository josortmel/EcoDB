"""Foresights endpoint — metacognicion v2.0 §7.5."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user
from db import get_pool
from permissions import resolve_agent_for_actor, precompute_read_visibility, check_read_memory


router = APIRouter(prefix="/foresights", tags=["foresights"])


async def _paginate(conn, base_sql, params, limit, cursor=None):
    if cursor:
        try:
            params.append(datetime.fromisoformat(cursor))
        except (ValueError, TypeError):
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
async def list_foresights(
    agent_identifier: str = Query(..., min_length=1),
    status: str = Query("active", pattern="^(active|expired|dismissed)$"),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await resolve_agent_for_actor(conn, actor, agent_identifier)
        if status == "active":
            where_extra = ("AND foresight_end > NOW() "
                          "AND (metadata->>'foresight_dismissed' IS NULL "
                          "OR metadata->>'foresight_dismissed' != 'true')")
        elif status == "expired":
            where_extra = "AND foresight_end <= NOW()"
        else:  # dismissed
            where_extra = "AND metadata->>'foresight_dismissed' = 'true'"
        base_sql = f"""
            SELECT * FROM memories
            WHERE agent_id = $1 AND foresight_start IS NOT NULL {where_extra}
        """
        params: list = [agent["id"]]
        items, next_cursor = await _paginate(conn, base_sql, params, limit, cursor)
        vis = await precompute_read_visibility(conn, actor)
        visible = [dict(r) for r in items if check_read_memory(vis, r)]
    return {"items": visible, "total": len(visible), "cursor_next": next_cursor}
