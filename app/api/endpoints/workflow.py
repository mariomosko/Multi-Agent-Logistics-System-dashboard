from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.workflow import run_exception_workflow
from app.database import get_db
from app.models import Shipment, ShipmentException, WorkflowStatus
from app.schemas import ExceptionRead, TrackingEvent, WorkflowResult

router = APIRouter(prefix="/workflow", tags=["workflow"])


@router.post("/trigger", response_model=WorkflowResult)
async def trigger_workflow(
    event: TrackingEvent,
    db: AsyncSession = Depends(get_db),
) -> WorkflowResult:
    """
    Accepts a tracking event, creates a ShipmentException, and runs the full
    5-agent pipeline synchronously, returning the final result.
    """
    shipment = await db.scalar(
        select(Shipment).where(Shipment.tracking_number == event.tracking_number)
    )
    if not shipment:
        raise HTTPException(
            status_code=404,
            detail=f"Shipment with tracking number {event.tracking_number!r} not found",
        )

    exception = ShipmentException(
        shipment_id=shipment.id,
        exception_type=event.event_type,
        raw_event=event.model_dump(mode="json"),
        workflow_status=WorkflowStatus.PENDING,
    )
    db.add(exception)
    await db.flush()

    return await run_exception_workflow(exception, db)


@router.get("/exceptions", response_model=list[ExceptionRead])
async def list_exceptions(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[ShipmentException]:
    result = await db.execute(
        select(ShipmentException).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


@router.get("/exceptions/{exception_id}", response_model=WorkflowResult)
async def get_exception_result(
    exception_id: int,
    db: AsyncSession = Depends(get_db),
) -> WorkflowResult:
    result = await db.execute(
        select(ShipmentException)
        .where(ShipmentException.id == exception_id)
        .options(
            selectinload(ShipmentException.agent_actions),
            selectinload(ShipmentException.resolution),
        )
    )
    exception = result.scalar_one_or_none()
    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found")

    return WorkflowResult(
        exception_id=exception.id,
        workflow_status=exception.workflow_status,
        severity=exception.severity,
        resolution=exception.resolution,
        agent_actions=exception.agent_actions,
    )
