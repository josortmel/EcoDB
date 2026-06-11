"""Skills endpoint — metacognicion v2.0 §7.7."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from auth import get_current_user
from db import get_pool
from pagination import paginate
from permissions import resolve_agent_for_actor, precompute_read_visibility, check_read_memory, can_read_memory
from clusters import _parse_jsonb
from shared_models import CaseResponse


router = APIRouter(prefix="/skills", tags=["skills"])


class SkillCard(BaseModel):
    id: UUID
    task_signature: str
    steps: list[str]
    tools: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    validation_checklist: list[str] = Field(default_factory=list)
    success_rate: float
    source_case_ids: list[UUID] = Field(default_factory=list)
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class SkillDetailResponse(SkillCard):
    source_cases: list[CaseResponse]


class SkillStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(..., pattern="^(active|stale|deprecated)$")


def _safe_uuid(val) -> UUID | None:
    if val is None:
        return None
    try:
        return UUID(val)
    except (ValueError, AttributeError):
        return None


def _safe_uuid_list(items: list) -> list[UUID]:
    result = []
    for c in items:
        try:
            result.append(UUID(c))
        except (ValueError, AttributeError):
            pass
    return result


@router.get("")
async def list_skills(
    agent_identifier: str = Query(..., min_length=1),
    status: Optional[str] = Query(None, pattern="^(active|stale|candidate|deprecated)$"),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await resolve_agent_for_actor(conn, actor, agent_identifier)
        conditions = ["type = 'skill'", "agent_id = $1"]
        params: list = [agent["id"]]
        if status:
            params.append(json.dumps({"status": status}))
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
                meta = _parse_jsonb(r["metadata"])
                if not isinstance(meta, dict):
                    meta = {}  # defensive: malformed/partial metadata never 500s the list
                visible.append(SkillCard(
                    id=r["id"],
                    task_signature=meta.get("task_signature", ""),
                    steps=meta.get("steps", []),
                    tools=meta.get("tools", []),
                    failure_modes=meta.get("failure_modes", []),
                    validation_checklist=meta.get("validation_checklist", []),
                    success_rate=meta.get("success_rate", 0.0),
                    source_case_ids=_safe_uuid_list(meta.get("source_case_ids", [])),
                    status=meta.get("status", "active"),
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                ))
    return {"items": visible, "total": total, "cursor_next": next_cursor}


@router.get("/{skill_id}")
async def get_skill(
    skill_id: UUID, actor: dict = Depends(get_current_user),
) -> SkillDetailResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        mem = await conn.fetchrow(
            "SELECT * FROM memories WHERE id=$1 AND type='skill'", skill_id)
        if mem is None:
            raise HTTPException(404)
        vis = await precompute_read_visibility(conn, actor)
        if not check_read_memory(vis, mem):
            raise HTTPException(404)
        meta = _parse_jsonb(mem["metadata"])
        case_ids = meta.get("source_case_ids", [])
        source_cases = []
        if case_ids:
            case_rows = await conn.fetch(
                "SELECT * FROM memories WHERE id = ANY($1::uuid[]) AND type='caso'",
                _safe_uuid_list(case_ids))
            for cr in case_rows:
                if check_read_memory(vis, cr):
                    cr_meta = _parse_jsonb(cr["metadata"])
                    source_cases.append(CaseResponse(
                        id=cr["id"], content=cr["content"],
                        task_type=cr_meta.get("task_type"),
                        steps=cr_meta.get("steps"),
                        result=cr_meta.get("result"),
                        success=cr_meta.get("success"),
                        skill_id=_safe_uuid(cr_meta.get("skill_id")),
                        created_at=cr["created_at"],
                    ))
    return SkillDetailResponse(
        id=mem["id"],
        task_signature=meta.get("task_signature", ""),
        steps=meta.get("steps", []),
        tools=meta.get("tools", []),
        failure_modes=meta.get("failure_modes", []),
        validation_checklist=meta.get("validation_checklist", []),
        success_rate=meta.get("success_rate", 0.0),
        source_case_ids=[sc.id for sc in source_cases],
        status=meta.get("status", "active"),
        created_at=mem["created_at"],
        updated_at=mem["updated_at"],
        source_cases=source_cases,
    )


@router.put("/{skill_id}/status")
async def update_skill_status(
    skill_id: UUID, body: SkillStatusBody,
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        mem = await conn.fetchrow(
            "SELECT * FROM memories WHERE id=$1 AND type='skill'", skill_id)
        if mem is None:
            raise HTTPException(404)
        if not await can_read_memory(conn, actor, mem):
            raise HTTPException(404)
        agent = await conn.fetchrow(
            "SELECT user_id FROM agents WHERE id=$1", mem["agent_id"])
        if not actor.get("is_super") and (agent is None or agent["user_id"] is None or int(agent["user_id"]) != int(actor["sub"])):
            raise HTTPException(403)
        meta = dict(mem["metadata"] or {})
        meta["status"] = body.status
        await conn.execute(
            "UPDATE memories SET metadata=$1::jsonb, updated_at=NOW() WHERE id=$2",
            json.dumps(meta), skill_id)
    return {"ok": True}
