from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.database import get_db
from app.models import (
    AgentAction,
    ShipmentException,
    WorkflowStatus,
)
from app.schemas import (
    AgentMetrics,
    ExceptionDetail,
    ExceptionSummary,
    PaginatedExceptions,
    PerformanceReport,
    ResolutionRead,
    AgentActionReadFull,
)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


# ── GET /exceptions ───────────────────────────────────────────────────────────

@router.get("/exceptions", response_model=PaginatedExceptions)
async def list_exceptions(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: WorkflowStatus | None = None,
):
    """Paginated list of all shipment exceptions with their resolution status."""
    base_q = (
        select(ShipmentException)
        .join(ShipmentException.shipment)
        .options(selectinload(ShipmentException.shipment))
    )
    if status:
        base_q = base_q.where(ShipmentException.workflow_status == status)

    count_result = await db.execute(
        select(func.count()).select_from(base_q.subquery())
    )
    total = count_result.scalar_one()

    rows_result = await db.execute(
        base_q
        .order_by(ShipmentException.detected_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    exceptions = rows_result.scalars().all()

    items = [
        ExceptionSummary(
            id=exc.id,
            shipment_id=exc.shipment_id,
            tracking_number=exc.shipment.tracking_number,
            carrier=exc.shipment.carrier,
            exception_type=exc.exception_type,
            severity=exc.severity,
            workflow_status=exc.workflow_status,
            detected_at=exc.detected_at,
            customer_name=exc.shipment.customer_name,
        )
        for exc in exceptions
    ]

    return PaginatedExceptions(total=total, page=page, page_size=page_size, items=items)


# ── GET /exceptions/{id} ──────────────────────────────────────────────────────

@router.get("/exceptions/{exception_id}", response_model=ExceptionDetail)
async def get_exception(
    exception_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Full agent workflow details for a single exception."""
    result = await db.execute(
        select(ShipmentException)
        .where(ShipmentException.id == exception_id)
        .options(
            selectinload(ShipmentException.shipment),
            selectinload(ShipmentException.agent_actions),
            selectinload(ShipmentException.resolution),
        )
    )
    exc = result.scalar_one_or_none()
    if exc is None:
        raise HTTPException(status_code=404, detail="Exception not found")

    return ExceptionDetail(
        id=exc.id,
        shipment_id=exc.shipment_id,
        tracking_number=exc.shipment.tracking_number,
        carrier=exc.shipment.carrier,
        customer_name=exc.shipment.customer_name,
        customer_email=exc.shipment.customer_email,
        exception_type=exc.exception_type,
        description=exc.description,
        severity=exc.severity,
        workflow_status=exc.workflow_status,
        detected_at=exc.detected_at,
        raw_event=exc.raw_event,
        agent_actions=[
            AgentActionReadFull.model_validate(a) for a in exc.agent_actions
        ],
        resolution=(
            ResolutionRead.model_validate(exc.resolution)
            if exc.resolution else None
        ),
    )


# ── GET /agents/performance ───────────────────────────────────────────────────

@router.get("/agents/performance", response_model=PerformanceReport)
async def agent_performance(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Aggregate metrics per agent: timing, success rate, token usage, cost."""
    # --- exceptions by status ---
    status_rows = await db.execute(
        select(ShipmentException.workflow_status, func.count())
        .group_by(ShipmentException.workflow_status)
    )
    exceptions_by_status = {row[0].value: row[1] for row in status_rows}
    total_exceptions = sum(exceptions_by_status.values())

    # --- per-agent aggregates ---
    agg_rows = await db.execute(
        select(
            AgentAction.agent_name,
            func.count().label("total_runs"),
            func.count(AgentAction.id)
            .filter(AgentAction.status == "completed")
            .label("successful_runs"),
            func.avg(AgentAction.duration_ms).label("avg_duration_ms"),
            func.sum(AgentAction.input_tokens).label("total_input_tokens"),
            func.sum(AgentAction.output_tokens).label("total_output_tokens"),
        )
        .group_by(AgentAction.agent_name)
    )

    # p95 requires a separate per-agent query (SQLite lacks PERCENTILE_CONT)
    p95_map: dict[str, float | None] = {}
    agent_names_result = await db.execute(
        select(AgentAction.agent_name).distinct()
    )
    for (agent_name,) in agent_names_result:
        dur_result = await db.execute(
            select(AgentAction.duration_ms)
            .where(
                AgentAction.agent_name == agent_name,
                AgentAction.duration_ms.is_not(None),
            )
            .order_by(AgentAction.duration_ms)
        )
        durations = [r[0] for r in dur_result]
        if durations:
            idx = int(len(durations) * 0.95)
            p95_map[agent_name] = durations[min(idx, len(durations) - 1)]
        else:
            p95_map[agent_name] = None

    cin = settings.cost_per_input_token
    cout = settings.cost_per_output_token

    agents: list[AgentMetrics] = []
    total_cost = 0.0

    for row in agg_rows:
        name = row.agent_name
        total = row.total_runs
        success = int(row.successful_runs or 0)
        failed = total - success
        inp = int(row.total_input_tokens or 0)
        out = int(row.total_output_tokens or 0)
        cost = inp * cin + out * cout
        total_cost += cost

        agents.append(AgentMetrics(
            agent_name=name,
            total_runs=total,
            successful_runs=success,
            failed_runs=failed,
            success_rate=round(success / total, 4) if total else 0.0,
            avg_duration_ms=(
                round(row.avg_duration_ms, 1) if row.avg_duration_ms else None
            ),
            p95_duration_ms=p95_map.get(name),
            total_input_tokens=inp,
            total_output_tokens=out,
            estimated_cost_usd=round(cost, 6),
        ))

    # Sort by pipeline order
    _ORDER = [
        "detection_agent", "analysis_agent", "decision_agent",
        "communication_agent", "action_agent",
    ]
    agents.sort(key=lambda a: _ORDER.index(a.agent_name)
                if a.agent_name in _ORDER else len(_ORDER))

    return PerformanceReport(
        generated_at=datetime.now(timezone.utc),
        total_exceptions_processed=total_exceptions,
        exceptions_by_status=exceptions_by_status,
        agents=agents,
        total_estimated_cost_usd=round(total_cost, 6),
    )
