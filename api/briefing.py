"""Briefing endpoint — metacognicion v2.0 §7.4."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from auth import get_current_user
from clusters import ClusterSummary
from db import get_pool
from permissions import precompute_read_visibility, check_read_memory, can_write_memory, resolve_agent_for_actor


def _safe_uuid_list(items: list) -> list[UUID]:
    result = []
    for x in items:
        try:
            result.append(UUID(x))
        except (ValueError, AttributeError):
            pass
    return result


router = APIRouter(prefix="/briefing", tags=["briefing"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ForesightItem(BaseModel):
    memory_id: UUID
    content: str
    foresight_start: datetime
    foresight_end: datetime
    urgency_score: float
    evidence: str


class TensionItem(BaseModel):
    id: UUID
    observed_trait: str
    declared_trait: str
    tension_type: str
    evidence_memory_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    status: str


class TelescopicSummary(BaseModel):
    weeklies: list[ClusterSummary]
    monthlies: list[ClusterSummary]
    quarterlies: list[ClusterSummary]
    yearlies: list[ClusterSummary]


class BriefingResponse(BaseModel):
    agent_identifier: str
    foresights: list[ForesightItem]
    identity_tensions: list[TensionItem]
    pending_clusters: list[ClusterSummary]
    telescopic_summary: TelescopicSummary


class DismissBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(..., min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def _no_nulls(cls, v):
        if "\x00" in v:
            raise ValueError("reason contains null bytes")
        return v


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

def _briefing_score(item, now):
    delta_days = max((item["foresight_start"] - now).total_seconds() / 86400, 1.0)
    urgency = 1.0 / delta_days
    evidence = 1.0 if item.get("content") and len(item["content"]) > 20 else 0.5
    meta = item.get("metadata") or {}
    confidence = float(meta.get("foresight_confidence", 1.0))
    usefulness = 1.0
    if item.get("access_count", 0) == 0:
        age_days = (now - item["created_at"]).total_seconds() / 86400
        if age_days > 7:
            usefulness = 0.7
    contradiction = 0.0
    nuisance = float(meta.get("nuisance_penalty", 0))
    return round(evidence * confidence * urgency * usefulness - contradiction - nuisance, 4)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def get_briefing(
    agent_identifier: str = Query(..., min_length=1),
    actor: dict = Depends(get_current_user),
) -> BriefingResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await resolve_agent_for_actor(conn, actor, agent_identifier)
        aid = agent["id"]
        now = datetime.now(timezone.utc)

        # 1. Active foresights
        foresight_rows = await conn.fetch("""
            SELECT * FROM memories WHERE agent_id = $1
              AND foresight_start IS NOT NULL AND foresight_end > NOW()
              AND (metadata->>'foresight_dismissed' IS NULL
                   OR metadata->>'foresight_dismissed' != 'true')
              AND staleness != 'archived'
            ORDER BY foresight_start ASC LIMIT 50
        """, aid)
        vis = await precompute_read_visibility(conn, actor)
        foresights = []
        for r in foresight_rows:
            if check_read_memory(vis, r):
                item = dict(r)
                item["urgency_score"] = _briefing_score(item, now)
                item["evidence"] = item["content"][:200] if item["content"] else ""
                foresights.append(item)
        foresights.sort(key=lambda x: x["urgency_score"], reverse=True)
        foresights = foresights[:10]

        # 2. Open tensions
        tension_rows = await conn.fetch("""
            SELECT * FROM memories WHERE agent_id = $1
              AND 'identity_tension' = ANY(tags)
              AND (metadata->>'tension_status' IS NULL
                   OR metadata->>'tension_status' = 'open')
            ORDER BY created_at DESC LIMIT 10
        """, aid)
        tensions = [dict(r) for r in tension_rows
                    if check_read_memory(vis, r)][:5]

        # 3. Pending clusters (CANDIDATE — separate section, NEVER in telescopic)
        pending = await conn.fetch("""
            SELECT id, agent_id, level, label, detail,
                   array_length(member_ids,1) AS member_count,
                   coalesce(array_length(source_ids,1),0) AS source_count,
                   period_start, period_end, status, created_at
            FROM memory_clusters
            WHERE agent_id=$1 AND status='candidate' AND narrative IS NULL
            ORDER BY created_at DESC LIMIT 5
        """, aid)

        # 4. Telescopic (ONLY status='active')
        _level_key = {"weekly": "weeklies", "monthly": "monthlies",
                      "quarterly": "quarterlies", "yearly": "yearlies"}
        telescopic = {}
        for lvl, lim in [('weekly', 4), ('monthly', 3), ('quarterly', 4), ('yearly', 100)]:
            rows = await conn.fetch("""
                SELECT id, agent_id, level, label, detail, narrative,
                       array_length(member_ids,1) AS member_count,
                       coalesce(array_length(source_ids,1),0) AS source_count,
                       pattern_flags, period_start, period_end, status,
                       narrated_at, created_at
                FROM memory_clusters
                WHERE agent_id=$1 AND level=$2 AND status='active'
                ORDER BY period_end DESC LIMIT $3
            """, aid, lvl, lim)
            telescopic[_level_key[lvl]] = [
                ClusterSummary(**dict(r)) for r in rows
            ]

        foresight_items = [
            ForesightItem(
                memory_id=f["id"],
                content=f["content"],
                foresight_start=f["foresight_start"],
                foresight_end=f["foresight_end"],
                urgency_score=f["urgency_score"],
                evidence=f.get("evidence", ""),
            ) for f in foresights
        ]

        tension_items = [
            TensionItem(
                id=t["id"],
                observed_trait=(t.get("metadata") or {}).get("observed_trait", ""),
                declared_trait=(t.get("metadata") or {}).get("declared_trait", ""),
                tension_type=(t.get("metadata") or {}).get("tension_type", ""),
                evidence_memory_ids=_safe_uuid_list(
                    (t.get("metadata") or {}).get("evidence_memory_ids", [])
                ),
                created_at=t["created_at"],
                status=(t.get("metadata") or {}).get("tension_status", "open"),
            ) for t in tensions
        ]

        pending_items = [ClusterSummary(**dict(r)) for r in pending]

    return BriefingResponse(
        agent_identifier=agent_identifier,
        foresights=foresight_items,
        identity_tensions=tension_items,
        pending_clusters=pending_items,
        telescopic_summary=TelescopicSummary(**telescopic),
    )


@router.put("/foresights/{memory_id}/dismiss")
async def dismiss_foresight(
    memory_id: UUID, body: DismissBody,
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        mem = await conn.fetchrow("SELECT * FROM memories WHERE id=$1", memory_id)
        if mem is None:
            raise HTTPException(404)
        if not await can_write_memory(conn, actor, mem):
            raise HTTPException(403)
        current_penalty = float((mem["metadata"] or {}).get("nuisance_penalty", 0))
        update_obj = {
            "foresight_dismissed": "true",
            "foresight_dismiss_reason": body.reason,
            "nuisance_penalty": current_penalty + 0.1,
        }
        await conn.execute("""
            UPDATE memories SET metadata = coalesce(metadata,'{}'::jsonb) || $2::jsonb,
              updated_at = NOW()
            WHERE id = $1
        """, memory_id, json.dumps(update_obj))
    return {"ok": True}


@router.put("/tensions/{memory_id}/dismiss")
async def dismiss_tension(
    memory_id: UUID, body: TensionAction,
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        mem = await conn.fetchrow("SELECT * FROM memories WHERE id=$1", memory_id)
        if mem is None or 'identity_tension' not in (mem["tags"] or []):
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
        """, json.dumps(update), memory_id)
    return {"ok": True}
