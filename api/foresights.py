"""Foresights endpoint — metacognicion v2.0 §7.5."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from auth import get_current_user
from briefing import ForesightItem, _briefing_score
from db import get_pool
from pagination import paginate
from permissions import resolve_agent_for_actor, precompute_read_visibility, check_read_memory


router = APIRouter(prefix="/foresights", tags=["foresights"])


def _to_foresight_item(row, now) -> ForesightItem:
    item = dict(row)
    return ForesightItem(
        memory_id=item["id"],
        content=item["content"],
        foresight_start=item["foresight_start"],
        foresight_end=item["foresight_end"],
        urgency_score=_briefing_score(item, now),
        evidence=item["content"][:200] if item["content"] else "",
    )


@router.get("")
async def list_foresights(
    agent_identifier: str = Query(..., min_length=1),
    status: str = Query("active", pattern="^(active|expired|dismissed)$"),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    now = datetime.now(timezone.utc)
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
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM memories WHERE agent_id = $1 AND foresight_start IS NOT NULL {where_extra}",
            agent["id"])
        items, next_cursor = await paginate(conn, base_sql, params, limit, cursor)
        vis = await precompute_read_visibility(conn, actor)
        visible = [_to_foresight_item(r, now) for r in items if check_read_memory(vis, r)]
    return {"items": visible, "total": total, "cursor_next": next_cursor}
