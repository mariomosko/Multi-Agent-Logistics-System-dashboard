"""
POST /api/v1/simulate/exception

Triggers the full 5-agent pipeline against a real DB shipment using a
pre-built scenario payload. Returns 202 immediately; the pipeline runs in
the background and pushes progress via WebSocket.

Also exposes GET /api/v1/simulate/scenarios so the frontend can list options.
"""
import logging
import random
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.websocket_manager import manager as ws_manager
from app.core.workflow import run_exception_workflow
from app.database import AsyncSessionLocal, get_db
from app.models import Shipment, ShipmentException, WorkflowStatus

router = APIRouter(prefix="/simulate", tags=["simulate"])
_log = logging.getLogger(__name__)

# ── Scenario templates ────────────────────────────────────────────────────────

SCENARIO_META = {
    "delay": {
        "label":       "Weather Delay",
        "description": "Severe weather grounds hub — 2–3 day delay expected",
        "icon":        "🌩️",
    },
    "lost": {
        "label":       "Lost Package",
        "description": "No scans for 6+ days, investigation triggered",
        "icon":        "🔍",
    },
    "damaged": {
        "label":       "Damaged in Transit",
        "description": "Forklift impact at sorting facility, contents compromised",
        "icon":        "📦",
    },
    "address_issue": {
        "label":       "Address Issue",
        "description": "Apartment number missing, delivery failed",
        "icon":        "📍",
    },
    "customs_hold": {
        "label":       "Customs Hold",
        "description": "CBP documentation review, 3–7 day estimated hold",
        "icon":        "🛃",
    },
    "failed_delivery": {
        "label":       "Failed Delivery",
        "description": "Driver unable to access delivery location",
        "icon":        "🚚",
    },
}

_SCENARIO_EVENTS: dict[str, dict] = {
    "delay": {
        "event_type": "delay",
        "event_timestamp": "2026-05-03T14:30:00Z",
        "location": "Memphis, TN — FedEx World Hub",
        "description": (
            "Package delayed due to severe thunderstorms and tornado warnings "
            "across the Memphis hub. All outbound flights grounded. "
            "Estimated delay: 2-3 days."
        ),
        "status_code": "DE",
        "metadata": {
            "weather_event": "tornado_warning",
            "hub_closure_duration_hours": 18,
            "affected_flights": 47,
        },
    },
    "lost": {
        "event_type": "lost",
        "event_timestamp": "2026-05-03T16:00:00Z",
        "location": "Last scan: Dallas, TX — FedEx Ground facility",
        "description": (
            "Package has not received any scan activity for 6 days following "
            "departure from Dallas Ground facility. Expected delivery date was "
            "2026-04-29. System-generated alert triggered after 144 hours without "
            "a location update. Investigation initiated."
        ),
        "status_code": "LS",
        "metadata": {
            "last_scan_timestamp": "2026-04-27T10:22:00Z",
            "days_without_scan": 6,
            "days_overdue": 4,
            "investigation_ticket": f"INV-2026-{random.randint(10000, 99999)}",
        },
    },
    "damaged": {
        "event_type": "damaged",
        "event_timestamp": "2026-05-03T09:15:00Z",
        "location": "Louisville, KY — UPS Worldport",
        "description": (
            "Package sustained visible damage during unloading at Worldport. "
            "Outer carton crushed; contents may be compromised. Package held "
            "pending damage assessment. Customer notification required."
        ),
        "status_code": "DM",
        "metadata": {
            "damage_type": "crush",
            "assessment_required": True,
            "insurance_claim_eligible": True,
        },
    },
    "address_issue": {
        "event_type": "address_issue",
        "event_timestamp": "2026-05-03T11:45:00Z",
        "location": "Austin, TX 78701",
        "description": (
            "Delivery attempted but address could not be located. Apartment "
            "number missing from label. Carrier left notice; package returned "
            "to post office. Redelivery requires address correction."
        ),
        "status_code": "AG",
        "metadata": {
            "attempt_number": 1,
            "notice_left": True,
            "missing_field": "apartment_number",
        },
    },
    "customs_hold": {
        "event_type": "customs_hold",
        "event_timestamp": "2026-05-03T07:00:00Z",
        "location": "JFK International Airport, NY — CBP Customs",
        "description": (
            "Shipment held by U.S. Customs and Border Protection for additional "
            "documentation review. Commercial invoice and HS tariff codes require "
            "verification. Estimated hold: 3-7 business days."
        ),
        "status_code": "CH",
        "metadata": {
            "customs_authority": "CBP",
            "hold_reason": "documentation_review",
            "documents_required": ["commercial_invoice", "hs_tariff_declaration"],
            "estimated_hold_days": 5,
        },
    },
    "failed_delivery": {
        "event_type": "failed_delivery",
        "event_timestamp": "2026-05-03T15:30:00Z",
        "location": "Chicago, IL 60601",
        "description": (
            "Third delivery attempt failed. Recipient not home, no safe-drop "
            "location available. Package returned to facility. Customer must "
            "schedule redelivery or pick up at local station."
        ),
        "status_code": "FD",
        "metadata": {
            "attempt_number": 3,
            "safe_drop_available": False,
            "hold_until": "2026-05-10",
        },
    },
}

ScenarioType = Literal[
    "delay", "lost", "damaged", "address_issue", "customs_hold", "failed_delivery"
]


# ── Request / response schemas ────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    scenario: ScenarioType | None = None  # random if omitted


class SimulateResponse(BaseModel):
    exception_id: int
    tracking_number: str
    carrier: str
    scenario: str
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/scenarios")
async def list_scenarios() -> dict:
    """Return available scenarios and their descriptions."""
    return {
        k: {**v, "key": k}
        for k, v in SCENARIO_META.items()
    }


@router.post("/exception", response_model=SimulateResponse, status_code=202)
async def trigger_simulation(
    body: SimulateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> SimulateResponse:
    """
    Pick a random registered shipment, build a scenario raw_event, create a
    ShipmentException, broadcast exception.created, and run the full agent
    pipeline asynchronously.
    """
    scenario = body.scenario or random.choice(list(_SCENARIO_EVENTS))

    # Pick a random registered shipment
    shipment = await db.scalar(
        select(Shipment).order_by(func.random()).limit(1)
    )
    if shipment is None:
        raise HTTPException(
            status_code=404,
            detail="No shipments in the database. Run: python -m scripts.init_db --seed",
        )

    # Build the raw event (inject real tracking number + carrier)
    raw_event = {
        **_SCENARIO_EVENTS[scenario],
        "carrier": shipment.carrier,
        "tracking_number": shipment.tracking_number,
    }

    # Create the exception record
    exception = ShipmentException(
        shipment_id=shipment.id,
        exception_type=scenario,
        raw_event=raw_event,
        workflow_status=WorkflowStatus.PENDING,
    )
    db.add(exception)
    await db.commit()
    await db.refresh(exception)

    _log.info(
        "Simulation triggered  scenario=%s  exception_id=%d  shipment=%s",
        scenario, exception.id, shipment.tracking_number,
    )

    # Broadcast new exception immediately so the dashboard updates before
    # the pipeline even starts
    await ws_manager.broadcast({
        "event": "exception.created",
        "exception_id": exception.id,
        "tracking_number": shipment.tracking_number,
        "carrier": shipment.carrier,
        "customer_name": shipment.customer_name,
        "exception_type": scenario,
        "workflow_status": "pending",
        "detected_at": exception.detected_at.isoformat(),
        "shipment_id": shipment.id,
        "location": raw_event.get("location"),
        "severity": None,
    })

    background_tasks.add_task(_run_pipeline, exception.id)

    return SimulateResponse(
        exception_id=exception.id,
        tracking_number=shipment.tracking_number,
        carrier=shipment.carrier,
        scenario=scenario,
        message=(
            f"Scenario '{scenario}' triggered for {shipment.tracking_number}. "
            f"Watch exception #{exception.id} via WebSocket for live progress."
        ),
    )


# ── Background task ───────────────────────────────────────────────────────────

async def _run_pipeline(exception_id: int) -> None:
    """Run the full agent pipeline in a fresh session."""
    _log.info("Simulation pipeline starting  exception_id=%d", exception_id)
    try:
        async with AsyncSessionLocal() as db:
            exception = await db.get(ShipmentException, exception_id)
            if exception is None:
                _log.error("Exception %d not found — aborting simulation", exception_id)
                return
            await run_exception_workflow(exception, db)
    except Exception as exc:
        _log.error(
            "Simulation pipeline crashed  exception_id=%d: %s",
            exception_id, exc, exc_info=True,
        )
