"""Clusters endpoint — metacognicion v2.0 §7.3 + Memory Agent v1.3 search+telescopic."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from auth import get_current_user
from db import get_pool
from embeddings_client import embed_text
from events import broadcast_event
from pagination import paginate
from permissions import (
    precompute_read_visibility,
    check_read_memory,
    resolve_agent_for_actor,
    resolve_cluster_for_actor,
)

_log = logging.getLogger("ecodb.clusters")


router = APIRouter(prefix="/clusters", tags=["clusters"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ClusterSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    agent_id: int
    level: str
    label: str
    detail: Optional[str] = None
    narrative: Optional[str] = None
    member_count: int
    source_count: int
    pattern_flags: dict = Field(default_factory=dict)
    period_start: date
    period_end: date
    status: str
    narrated_at: Optional[datetime] = None
    created_at: datetime


class ClusterDetail(ClusterSummary):
    metadata: dict = Field(default_factory=dict)


class ClusterMember(BaseModel):
    memory_id: UUID
    content: str
    tags: list[str]
    type: str
    created_at: datetime
    distances: dict = Field(default_factory=dict)


class ClusterMembersResponse(BaseModel):
    cluster_id: UUID
    members: list[ClusterMember]
    total: int
    cursor_next: Optional[str] = None


class ClusterSourcesResponse(BaseModel):
    cluster_id: UUID
    sources: list[ClusterSummary]
    parent_clusters: list[ClusterSummary]


class NarrateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    narrative: str = Field(..., min_length=1, max_length=5000)


class ClusterStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = Field(..., pattern="^(active|rejected|superseded)$")
    reason: Optional[str] = Field(None, max_length=500)


class ClustersListResponse(BaseModel):
    items: list[ClusterSummary]
    total: int
    cursor_next: Optional[str] = None


class ClusterStatsResponse(BaseModel):
    total_by_level: dict[str, int]
    total_by_status: dict[str, int]
    pending_narration: int
    graph_led_pct: Optional[float] = None
    last_run: Optional[datetime] = None
    avg_cluster_size: Optional[float] = None


class ClusterSearchResult(BaseModel):
    id: UUID
    level: str
    label: str
    narrative_preview: Optional[str] = None
    agent_identifier: Optional[str] = None
    period_start: date
    period_end: date
    member_count: int
    vector_score: float
    bm25_score: float


class ClusterSearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query_text: str = Field(..., min_length=3, max_length=2000)
    agent_identifier: Optional[str] = None
    level: Optional[str] = Field(None, pattern="^(weekly|monthly|quarterly|yearly)$")
    status: str = Field("active", pattern="^(active|candidate|rejected|superseded)$")
    limit: int = Field(10, ge=1, le=50)


class ClusterSearchResponse(BaseModel):
    results: list[ClusterSearchResult]
    count: int
    duration_ms: float


class ClusterNarrativeSummary(BaseModel):
    id: UUID
    label: str
    narrative: Optional[str] = None
    period_start: date
    period_end: date
    member_count: int
    source_count: int


class TelescopicViewResponse(BaseModel):
    # Boot order — oldest/broadest first: yearly → quarterly → monthly → weekly → recent_days.
    agent_identifier: str
    yearly: list[ClusterNarrativeSummary] = Field(default_factory=list)
    quarterly: list[ClusterNarrativeSummary] = Field(default_factory=list)
    monthly: list[ClusterNarrativeSummary] = Field(default_factory=list)
    weekly: list[ClusterNarrativeSummary] = Field(default_factory=list)
    recent_days: list[dict] = Field(default_factory=list, description="Raw memories from the last 3 complete days, oldest-first")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_jsonb(val):
    if val is None:
        return {}
    if isinstance(val, str):
        import json
        return json.loads(val)
    return val


def _cluster_summary(row) -> ClusterSummary:
    return ClusterSummary(
        id=row["id"],
        agent_id=row["agent_id"],
        level=row["level"],
        label=row["label"],
        detail=row.get("detail"),
        narrative=row.get("narrative"),
        member_count=row["member_count"],
        source_count=row["source_count"],
        pattern_flags=_parse_jsonb(row.get("pattern_flags")),
        period_start=row["period_start"],
        period_end=row["period_end"],
        status=row["status"],
        narrated_at=row.get("narrated_at"),
        created_at=row["created_at"],
    )


def _cluster_detail(row) -> ClusterDetail:
    base = _cluster_summary(row).model_dump()
    return ClusterDetail(**base, metadata=_parse_jsonb(row.get("metadata")))


# ---------------------------------------------------------------------------
# Endpoints — search + telescopic (Memory Agent v1.3)
# ---------------------------------------------------------------------------

@router.post("/search")
async def search_clusters(
    body: ClusterSearchBody,
    actor: dict = Depends(get_current_user),
) -> ClusterSearchResponse:
    import time
    t0 = time.time()
    pool = await get_pool()

    query_embedding = await embed_text(body.query_text, prompt_name="query")

    async with pool.acquire() as conn:
        # $1 = embedding vector, $2 = query text (BM25), $3 = status
        conditions = ["mc.status = $3"]
        params: list = [query_embedding, body.query_text, body.status]

        # Contamination prevention — Pepe's "mesa" rule (Spec §2):
        #   with agent_identifier -> that agent's own clusters + SIN_AUTOR
        #   without, non-super     -> only SIN_AUTOR (generic/technical)
        #   without, super         -> no agent filter (sees all)
        if body.agent_identifier:
            agent = await resolve_agent_for_actor(conn, actor, body.agent_identifier)
            params.append(agent["identifier"])
            conditions.append(
                f"(a.identifier = ${len(params)} OR a.identifier = 'SIN_AUTOR')")
        elif not actor.get("is_super"):
            conditions.append("a.identifier = 'SIN_AUTOR'")

        if body.level:
            params.append(body.level)
            conditions.append(f"mc.level = ${len(params)}")

        params.append(body.limit)
        where = " AND ".join(conditions)

        rows = await conn.fetch(f"""
            SELECT mc.id, mc.level, mc.label, mc.narrative,
                   a.identifier AS agent_identifier,
                   mc.period_start, mc.period_end,
                   coalesce(array_length(mc.member_ids, 1), 0) AS member_count,
                   1 - (mc.centroid <=> $1::vector) AS vector_score,
                   ts_rank(to_tsvector('spanish', mc.label),
                           plainto_tsquery('spanish', $2)) AS bm25_score
            FROM memory_clusters mc
            JOIN agents a ON a.id = mc.agent_id
            WHERE {where}
              AND mc.centroid IS NOT NULL
              AND (1 - (mc.centroid <=> $1::vector) > 0.3
                   OR ts_rank(to_tsvector('spanish', mc.label),
                              plainto_tsquery('spanish', $2)) > 0.05)
            ORDER BY (1 - (mc.centroid <=> $1::vector)) DESC
            LIMIT ${len(params)}
        """, *params)

    results = []
    for r in rows:
        narrative = r["narrative"]
        results.append(ClusterSearchResult(
            id=r["id"],
            level=r["level"],
            label=r["label"],
            narrative_preview=narrative[:200] if narrative else None,
            agent_identifier=r["agent_identifier"],
            period_start=r["period_start"],
            period_end=r["period_end"],
            member_count=r["member_count"],
            vector_score=float(r["vector_score"]),
            bm25_score=float(r["bm25_score"]),
        ))

    duration = (time.time() - t0) * 1000
    return ClusterSearchResponse(results=results, count=len(results), duration_ms=round(duration, 1))


@router.get("/telescopic")
async def get_telescopic_view(
    agent_identifier: str = Query(..., min_length=1),
    levels: str = Query("weekly,monthly,quarterly,yearly"),
    actor: dict = Depends(get_current_user),
) -> TelescopicViewResponse:
    requested_levels = [lv.strip() for lv in levels.split(",") if lv.strip()]
    valid_levels = {"weekly", "monthly", "quarterly", "yearly"}
    for lv in requested_levels:
        if lv not in valid_levels:
            raise HTTPException(422, f"invalid level: {lv}")

    limits = {"weekly": 4, "monthly": 3, "quarterly": 4, "yearly": 100}
    pool = await get_pool()

    async with pool.acquire() as conn:
        agent = await resolve_agent_for_actor(conn, actor, agent_identifier)
        aid = agent["id"]

        result: dict[str, list] = {}
        for lv in requested_levels:
            lim = limits.get(lv, 4)
            # Take the N most-recent clusters, then return them OLDEST-FIRST so the
            # boot reads chronologically (yearly→quarterly→monthly→weekly = old→recent).
            rows = await conn.fetch("""
                SELECT id, label, narrative, period_start, period_end,
                       member_count, source_count FROM (
                    SELECT mc.id, mc.label, mc.narrative,
                           mc.period_start, mc.period_end,
                           coalesce(array_length(mc.member_ids, 1), 0) AS member_count,
                           coalesce(array_length(mc.source_ids, 1), 0) AS source_count
                    FROM memory_clusters mc
                    WHERE mc.agent_id = $1 AND mc.level = $2 AND mc.status = 'active'
                    ORDER BY mc.period_end DESC
                    LIMIT $3
                ) sub
                ORDER BY period_end ASC
            """, aid, lv, lim)
            result[lv] = [ClusterNarrativeSummary(
                id=r["id"], label=r["label"], narrative=r["narrative"],
                period_start=r["period_start"], period_end=r["period_end"],
                member_count=r["member_count"], source_count=r["source_count"],
            ) for r in rows]

        # Last 3 complete days of raw memories (finest, most-recent layer of the boot).
        recent_rows = await conn.fetch("""
            SELECT id, type, content, weight, tags, created_at
            FROM memories
            WHERE agent_id = $1 AND created_at >= (CURRENT_DATE - INTERVAL '3 days')
            ORDER BY created_at ASC
        """, aid)
        recent_days = [{
            "id": str(r["id"]), "type": r["type"],
            "content": r["content"], "weight": float(r["weight"]),
            "tags": list(r["tags"]), "created_at": r["created_at"].isoformat(),
        } for r in recent_rows]

    return TelescopicViewResponse(
        agent_identifier=agent_identifier,
        yearly=result.get("yearly", []),
        quarterly=result.get("quarterly", []),
        monthly=result.get("monthly", []),
        weekly=result.get("weekly", []),
        recent_days=recent_days,
    )


# ---------------------------------------------------------------------------
# Endpoints — CRUD (existing v2.0)
# ---------------------------------------------------------------------------

@router.get("")
async def list_clusters(
    agent_identifier: str = Query(..., min_length=1),
    level: Optional[str] = Query(None, pattern="^(weekly|monthly|quarterly|yearly)$"),
    status: Optional[str] = Query(None, pattern="^(candidate|active|rejected|superseded)$"),
    pending_narration: bool = Query(False),
    pattern_flags: Optional[str] = Query(None),
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    actor: dict = Depends(get_current_user),
) -> ClustersListResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await resolve_agent_for_actor(conn, actor, agent_identifier)
        conditions = ["mc.agent_id = $1"]
        params: list = [agent["id"]]
        if level:
            params.append(level)
            conditions.append(f"mc.level = ${len(params)}")
        if status:
            params.append(status)
            conditions.append(f"mc.status = ${len(params)}")
        if pending_narration:
            conditions.append("mc.narrative IS NULL AND mc.status = 'candidate'")
        if pattern_flags:
            import json as _json
            try:
                _json.loads(pattern_flags)
            except (_json.JSONDecodeError, TypeError):
                raise HTTPException(422, "pattern_flags must be valid JSON")
            params.append(pattern_flags)
            conditions.append(f"mc.pattern_flags @> ${len(params)}::jsonb")
        if period_start:
            params.append(period_start)
            conditions.append(f"mc.period_start >= ${len(params)}")
        if period_end:
            params.append(period_end)
            conditions.append(f"mc.period_end <= ${len(params)}")
        where = " AND ".join(conditions)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM memory_clusters mc WHERE {where}", *params)
        items, next_cursor = await paginate(conn, f"""
            SELECT mc.*, array_length(member_ids, 1) AS member_count,
                   coalesce(array_length(source_ids, 1), 0) AS source_count
            FROM memory_clusters mc WHERE {where}
        """, list(params), limit, cursor)
    return {"items": [_cluster_summary(r) for r in items], "total": total, "cursor_next": next_cursor}


# /stats BEFORE /{cluster_id} — otherwise FastAPI matches "stats" as UUID
@router.get("/stats")
async def cluster_stats(
    agent_identifier: str = Query(..., min_length=1),
    actor: dict = Depends(get_current_user),
) -> ClusterStatsResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await resolve_agent_for_actor(conn, actor, agent_identifier)
        aid = agent["id"]
        by_level = await conn.fetch(
            "SELECT level, COUNT(*) AS cnt FROM memory_clusters WHERE agent_id=$1 GROUP BY level", aid)
        by_status = await conn.fetch(
            "SELECT status, COUNT(*) AS cnt FROM memory_clusters WHERE agent_id=$1 GROUP BY status", aid)
        pending = await conn.fetchval(
            "SELECT COUNT(*) FROM memory_clusters WHERE agent_id=$1 AND narrative IS NULL AND status='candidate'", aid)
        avg_size = await conn.fetchval(
            "SELECT AVG(array_length(member_ids,1)) FROM memory_clusters WHERE agent_id=$1 AND status='active'", aid)
        last_run_row = await conn.fetchrow("""
            SELECT finished_at, metrics FROM cell_runs
            WHERE agent_id=$1 AND cell_type='consolidation' AND status='completed'
            ORDER BY finished_at DESC LIMIT 1
        """, aid)
        _raw_m = last_run_row["metrics"] if last_run_row else {}
        if isinstance(_raw_m, str):
            import json as _json
            _raw_m = _json.loads(_raw_m)
        graph_led = (_raw_m or {}).get("graph_led_pct")
        last_run = last_run_row["finished_at"] if last_run_row else None
    return {
        "total_by_level": {r["level"]: r["cnt"] for r in by_level},
        "total_by_status": {r["status"]: r["cnt"] for r in by_status},
        "pending_narration": pending,
        "graph_led_pct": graph_led,
        "last_run": last_run,
        "avg_cluster_size": float(avg_size) if avg_size else None,
    }


@router.get("/{cluster_id}")
async def get_cluster(cluster_id: UUID, actor: dict = Depends(get_current_user)) -> ClusterDetail:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cluster = await resolve_cluster_for_actor(conn, actor, cluster_id)
        cluster["member_count"] = len(cluster["member_ids"])
        cluster["source_count"] = len(cluster["source_ids"] or [])
    return _cluster_detail(cluster)


@router.get("/{cluster_id}/members")
async def get_cluster_members(
    cluster_id: UUID, limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    actor: dict = Depends(get_current_user),
) -> ClusterMembersResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cluster = await resolve_cluster_for_actor(conn, actor, cluster_id)
        all_ids = cluster["member_ids"]
        rows = await conn.fetch(
            "SELECT * FROM memories WHERE id = ANY($1::uuid[]) ORDER BY created_at DESC",
            all_ids)
        md = (cluster.get("metadata") or {}).get("member_distances", {})
        vis = await precompute_read_visibility(conn, actor)
        visible = []
        for mem in rows:
            if check_read_memory(vis, mem):
                visible.append(ClusterMember(
                    memory_id=mem["id"],
                    content=mem["content"],
                    tags=list(mem["tags"]),
                    type=mem["type"],
                    created_at=mem["created_at"],
                    distances=md.get(str(mem["id"]), {}),
                ))
        if cursor:
            try:
                cursor_dt = datetime.fromisoformat(cursor)
            except (ValueError, TypeError):
                raise HTTPException(422, "invalid cursor format")
            visible = [m for m in visible if m.created_at < cursor_dt]
        page = visible[:limit]
        next_cursor = page[-1].created_at.isoformat() if len(visible) > limit else None
    return ClusterMembersResponse(
        cluster_id=cluster_id, members=page,
        total=len(visible), cursor_next=next_cursor)


@router.get("/{cluster_id}/sources")
async def get_cluster_sources(
    cluster_id: UUID, actor: dict = Depends(get_current_user),
) -> ClusterSourcesResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cluster = await resolve_cluster_for_actor(conn, actor, cluster_id)
        agent_id = cluster["agent_id"]
        sources = []
        if cluster["source_ids"]:
            source_rows = await conn.fetch(
                "SELECT *, coalesce(array_length(member_ids,1),0) AS member_count, "
                "coalesce(array_length(source_ids,1),0) AS source_count "
                "FROM memory_clusters WHERE id = ANY($1::uuid[]) AND agent_id = $2",
                cluster["source_ids"], agent_id)
            sources = [_cluster_summary(r) for r in source_rows]
        parents = await conn.fetch("""
            SELECT *, coalesce(array_length(member_ids,1),0) AS member_count,
                   coalesce(array_length(source_ids,1),0) AS source_count
            FROM memory_clusters WHERE $1::uuid = ANY(source_ids) AND agent_id = $2
        """, cluster_id, agent_id)
    return {"cluster_id": str(cluster_id),
            "sources": sources,
            "parent_clusters": [_cluster_summary(r) for r in parents]}


@router.put("/{cluster_id}/narrate")
async def narrate_cluster(
    cluster_id: UUID, body: NarrateBody,
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cluster = await resolve_cluster_for_actor(conn, actor, cluster_id)
        await conn.execute(
            "UPDATE memory_clusters SET narrative=$1, narrated_at=NOW() WHERE id=$2",
            body.narrative, cluster_id)
        org_id = await conn.fetchval(
            "SELECT organization_id FROM workspaces WHERE id=$1",
            cluster["workspace_id"])
        await broadcast_event("cluster.narrated",
            {"cluster_id": str(cluster_id),
             "agent_identifier": cluster["agent_identifier"]},
            org_id=org_id)
    return {"ok": True}


@router.put("/{cluster_id}/status")
async def update_cluster_status(
    cluster_id: UUID, body: ClusterStatusBody,
    actor: dict = Depends(get_current_user),
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cluster = await resolve_cluster_for_actor(conn, actor, cluster_id)
        valid = {("candidate", "active"), ("candidate", "rejected"), ("active", "superseded")}
        if (cluster["status"], body.status) not in valid:
            raise HTTPException(422, f"invalid transition {cluster['status']} -> {body.status}")
        await conn.execute(
            "UPDATE memory_clusters SET status=$1 WHERE id=$2",
            body.status, cluster_id)
        event_map = {"active": "cluster.promoted", "rejected": "cluster.rejected",
                     "superseded": "cluster.superseded"}
        org_id = await conn.fetchval(
            "SELECT organization_id FROM workspaces WHERE id=$1",
            cluster["workspace_id"])
        event_data = {"cluster_id": str(cluster_id),
             "agent_identifier": cluster["agent_identifier"]}
        if body.reason:
            event_data["reason"] = body.reason
        await broadcast_event(event_map[body.status], event_data, org_id=org_id)
    return {"ok": True}


@router.delete("/{cluster_id}", status_code=204)
async def delete_cluster(cluster_id: UUID, actor: dict = Depends(get_current_user)):
    if not actor.get("is_super"):
        raise HTTPException(403, "cluster delete requires super access")
    pool = await get_pool()
    async with pool.acquire() as conn:
        if not await conn.fetchval("SELECT 1 FROM memory_clusters WHERE id=$1", cluster_id):
            raise HTTPException(404)
        await conn.execute(
            "UPDATE memory_clusters SET status='rejected' WHERE id=$1", cluster_id)
