"""Cell telemetry + manual triggers — metacognicion v2.0."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field

from auth import get_current_user
from db import get_pool
from pagination import paginate
from permissions import resolve_agent_for_actor

log = logging.getLogger("ecodb.cells")

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
        count_sql = f"""
            SELECT COUNT(*) FROM cell_runs cr
            LEFT JOIN agents a ON a.id = cr.agent_id WHERE {where}
        """
        total = await conn.fetchval(count_sql, *params)
        items, next_cursor = await paginate(conn, f"""
            SELECT cr.*, a.identifier AS agent_identifier
            FROM cell_runs cr LEFT JOIN agents a ON a.id = cr.agent_id
            WHERE {where}
        """, list(params), limit, cursor, cursor_column="cr.created_at")
    return {"items": [dict(r) for r in items], "total": total, "cursor_next": next_cursor}


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

        rows = await conn.fetch(f"""
            SELECT cr.cell_type, MAX(cr.finished_at) AS last FROM cell_runs cr
            WHERE cr.status='completed' {agent_filter}
            GROUP BY cr.cell_type
        """, *params)
        # Keep the 3 built-in keys always present; overlay any custom types found.
        last_by_type = {ct: None for ct in ('consolidation', 'foresight', 'skill_distillation')}
        for r in rows:
            last_by_type[r["cell_type"]] = r["last"].isoformat() if r["last"] else None

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


# ---------------------------------------------------------------------------
# Manual trigger
# ---------------------------------------------------------------------------

class TriggerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool = True
    cell_type: str
    agent_identifier: str
    level: Optional[str] = None
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    status: str


_TRIGGER_SEM: Optional[asyncio.Semaphore] = None


def _get_trigger_sem() -> asyncio.Semaphore:
    global _TRIGGER_SEM
    if _TRIGGER_SEM is None:
        _TRIGGER_SEM = asyncio.Semaphore(3)
    return _TRIGGER_SEM


def _default_period(level: str, today: date) -> tuple[date, date]:
    if level == "weekly":
        end = today
        start = end - timedelta(days=6)
    elif level == "monthly":
        first_of_month = today.replace(day=1)
        end = first_of_month - timedelta(days=1)
        start = end.replace(day=1)
    elif level == "quarterly":
        q_month = ((today.month - 1) // 3) * 3 + 1
        first_of_quarter = today.replace(month=q_month, day=1)
        end = first_of_quarter - timedelta(days=1)
        prev_q_month = ((end.month - 1) // 3) * 3 + 1
        start = end.replace(month=prev_q_month, day=1)
    elif level == "yearly":
        end = date(today.year - 1, 12, 31)
        start = date(today.year - 1, 1, 1)
    else:
        raise ValueError(f"unknown level: {level}")
    return start, end


_BUILTIN_CELL_TYPES = frozenset(
    {"consolidation", "foresight", "skill_distillation"})


@router.post("/trigger/{cell_type}")
async def trigger_cell(
    cell_type: str = Path(
        ..., min_length=1, max_length=64, pattern="^[a-z0-9_]+$"),
    agent_identifier: str = Query(..., min_length=1, max_length=128),
    level: Optional[str] = Query(
        None, pattern="^(weekly|monthly|quarterly|yearly)$"),
    period_start: Optional[date] = Query(None),
    period_end: Optional[date] = Query(None),
    actor: dict = Depends(get_current_user),
) -> TriggerResponse:
    if not actor.get("is_super"):
        raise HTTPException(403, "cell trigger requires super access")

    if cell_type in ("foresight", "skill_distillation"):
        if level is not None:
            raise HTTPException(
                422, f"level parameter not applicable for {cell_type}")
        if period_start is not None or period_end is not None:
            raise HTTPException(
                422, f"period parameters not applicable for {cell_type}")

    pool = await get_pool()
    async with pool.acquire() as conn:
        agent = await resolve_agent_for_actor(conn, actor, agent_identifier)
        agent_id = agent["id"]

    # Custom (non-built-in) cell types route to the generic handler, which
    # requires an enabled cell_task_configs row with a prompt template.
    if cell_type not in _BUILTIN_CELL_TYPES:
        from cell_worker import _load_cell_config, _run_generic_cell, _resolve_run_context, _active_cell
        async with pool.acquire() as conn:
            cfg = await _load_cell_config(conn, agent_id, cell_type, None)
        if not cfg.get("cell_type"):
            raise HTTPException(422, f"no config found for cell_type {cell_type!r}")
        if not cfg.get("prompt_content"):
            raise HTTPException(
                422, f"no prompt template configured for cell_type {cell_type!r}")

        async def _run_generic():
            async with _get_trigger_sem():
                run_ctx = await _resolve_run_context(pool, agent_id, cell_type, None)
                tok = _active_cell.set(run_ctx) if run_ctx else None
                try:
                    await _run_generic_cell(pool, cfg, agent_id)
                except Exception:
                    log.exception("trigger generic %s agent=%s failed",
                                  cell_type, agent_identifier)
                finally:
                    if tok is not None:
                        _active_cell.reset(tok)

        asyncio.create_task(_run_generic())
        return TriggerResponse(
            cell_type=cell_type, agent_identifier=agent_identifier,
            level=None, status="started")

    today = date.today()
    effective_level = None
    p_start = None
    p_end = None

    if cell_type == "consolidation":
        effective_level = level or "weekly"
        has_start = period_start is not None
        has_end = period_end is not None
        if has_start != has_end:
            raise HTTPException(
                422, "period_start and period_end must both be provided or both omitted")
        if has_start:
            p_start, p_end = period_start, period_end
        else:
            p_start, p_end = _default_period(effective_level, today)
        if p_start > p_end:
            raise HTTPException(422, "period_start must be <= period_end")

    from cell_worker import (
        run_consolidation,
        run_foresight_extraction,
        run_monthly_consolidation,
        run_quarterly_consolidation,
        run_skill_distillation,
        run_yearly_consolidation,
    )

    _dispatch = {
        ("consolidation", "weekly"): lambda: run_consolidation(
            pool, agent_id, p_start, p_end),
        ("consolidation", "monthly"): lambda: run_monthly_consolidation(
            pool, agent_id, p_start, p_end),
        ("consolidation", "quarterly"): lambda: run_quarterly_consolidation(
            pool, agent_id, p_start, p_end),
        ("consolidation", "yearly"): lambda: run_yearly_consolidation(
            pool, agent_id, p_start, p_end),
        ("foresight", None): lambda: run_foresight_extraction(
            pool, agent_id),
        ("skill_distillation", None): lambda: run_skill_distillation(
            pool, agent_id),
    }

    key = (cell_type, effective_level)
    fn = _dispatch.get(key)
    if fn is None:
        raise HTTPException(422, f"invalid cell_type/level: {cell_type}/{level}")

    from cell_worker import _resolve_run_context, _active_cell

    async def _run():
        async with _get_trigger_sem():
            # Honor the agent's DB config (model/provider/template) for manual triggers too.
            run_ctx = await _resolve_run_context(pool, agent_id, cell_type, effective_level)
            tok = _active_cell.set(run_ctx) if run_ctx else None
            try:
                await fn()
            except Exception:
                log.exception("trigger %s/%s agent=%s failed",
                              cell_type, effective_level, agent_identifier)
            finally:
                if tok is not None:
                    _active_cell.reset(tok)

    asyncio.create_task(_run())

    return TriggerResponse(
        cell_type=cell_type,
        agent_identifier=agent_identifier,
        level=effective_level,
        period_start=p_start,
        period_end=p_end,
        status="started",
    )
