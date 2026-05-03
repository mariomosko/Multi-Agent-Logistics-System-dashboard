"""
POST /webhook/tracking-update

Simulates carrier webhook delivery. Validates the payload, persists a
WebhookEvent record, returns 202 immediately, then processes the event
asynchronously via FastAPI BackgroundTasks.

Background processing flow:
    WebhookEvent(RECEIVED)
    → find Shipment by tracking_number
    → if not found: IGNORED
    → create ShipmentException
    → run AgentCoordinator pipeline
    → WebhookEvent(PROCESSED)  (or FAILED if the task itself crashes)
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.websocket_manager import manager as ws_manager
from app.core.workflow import run_exception_workflow
from app.database import AsyncSessionLocal, get_db
from app.models import Shipment, ShipmentException, WebhookEvent, WebhookStatus, WorkflowStatus
from app.schemas import TrackingUpdatePayload, WebhookAck, WebhookEventRead

router = APIRouter(prefix="/webhook", tags=["webhook"])
_log = logging.getLogger(__name__)


# ── Auth dependency ───────────────────────────────────────────────────────────

async def _verify_secret(x_webhook_secret: str | None = Header(None)) -> None:
    """If WEBHOOK_SECRET is configured, require it in the X-Webhook-Secret header."""
    if settings.webhook_secret and x_webhook_secret != settings.webhook_secret:
        _log.warning("Rejected webhook request — invalid or missing X-Webhook-Secret")
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/tracking-update",
    response_model=WebhookAck,
    status_code=202,
    dependencies=[Depends(_verify_secret)],
)
async def tracking_update(
    payload: TrackingUpdatePayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> WebhookAck:
    """
    Accept a carrier tracking update event.

    Persists the raw payload immediately and returns 202. The agent
    pipeline runs in the background so the carrier webhook call is not
    blocked by Claude API latency.
    """
    webhook_event = WebhookEvent(
        carrier=payload.carrier,
        tracking_number=payload.tracking_number,
        event_type=payload.event_type,
        raw_payload=payload.model_dump(mode="json"),
        status=WebhookStatus.RECEIVED,
    )
    db.add(webhook_event)
    await db.commit()
    await db.refresh(webhook_event)

    _log.info(
        "Webhook received  id=%d  carrier=%s  tracking=%s  event_type=%s",
        webhook_event.id, payload.carrier, payload.tracking_number, payload.event_type,
    )

    background_tasks.add_task(_process_webhook, webhook_event.id)

    return WebhookAck(
        webhook_event_id=webhook_event.id,
        tracking_number=payload.tracking_number,
        message=(
            f"Tracking update for {payload.tracking_number!r} accepted "
            f"and queued for processing (event id={webhook_event.id})"
        ),
    )


# ── Monitoring endpoints ──────────────────────────────────────────────────────

@router.get("/events", response_model=list[WebhookEventRead])
async def list_webhook_events(
    skip: int = 0,
    limit: int = 50,
    status: WebhookStatus | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[WebhookEvent]:
    """List webhook events, optionally filtered by processing status."""
    q = select(WebhookEvent).offset(skip).limit(limit).order_by(WebhookEvent.received_at.desc())
    if status:
        q = q.where(WebhookEvent.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


@router.get("/events/{event_id}", response_model=WebhookEventRead)
async def get_webhook_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
) -> WebhookEvent:
    event = await db.get(WebhookEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Webhook event not found")
    return event


# ── Background task ───────────────────────────────────────────────────────────

async def _process_webhook(webhook_event_id: int) -> None:
    """
    Background coroutine — runs after the 202 response is sent.

    Opens its own DB session (the request session is already closed).
    On any unhandled exception, marks the WebhookEvent as FAILED so the
    error is visible without requiring log access.
    """
    _log.info("Background processing started  webhook_event_id=%d", webhook_event_id)
    try:
        async with AsyncSessionLocal() as db:
            await _run_pipeline(db, webhook_event_id)
    except Exception as exc:
        _log.error(
            "Background task crashed for webhook_event_id=%d: %s",
            webhook_event_id, exc, exc_info=True,
        )
        await _mark_failed(webhook_event_id, str(exc))


async def _run_pipeline(db: AsyncSession, webhook_event_id: int) -> None:
    """Core processing logic — runs inside an open session."""
    # ── Load event ────────────────────────────────────────────────────────────
    webhook = await db.get(WebhookEvent, webhook_event_id)
    if not webhook:
        _log.error("WebhookEvent %d not found — skipping", webhook_event_id)
        return

    webhook.status = WebhookStatus.PROCESSING
    await db.flush()
    _log.info(
        "Processing  webhook=%d  tracking=%s  event_type=%s",
        webhook_event_id, webhook.tracking_number, webhook.event_type,
    )

    # ── Look up shipment ──────────────────────────────────────────────────────
    shipment = await db.scalar(
        select(Shipment).where(Shipment.tracking_number == webhook.tracking_number)
    )
    if not shipment:
        msg = f"No shipment registered for tracking number {webhook.tracking_number!r}"
        _log.warning("webhook=%d  %s", webhook_event_id, msg)
        webhook.status = WebhookStatus.IGNORED
        webhook.error_message = msg
        webhook.processed_at = datetime.now(timezone.utc)
        await db.commit()
        return

    # ── Create exception record ───────────────────────────────────────────────
    exception = ShipmentException(
        shipment_id=shipment.id,
        exception_type=webhook.event_type,
        raw_event=webhook.raw_payload,
        workflow_status=WorkflowStatus.PENDING,
    )
    db.add(exception)
    await db.flush()

    # Link the webhook to the exception before the pipeline commits
    webhook.exception_id = exception.id
    await db.flush()

    _log.info(
        "webhook=%d  exception_id=%d  shipment_id=%d  starting pipeline",
        webhook_event_id, exception.id, shipment.id,
    )

    # Broadcast immediately so the dashboard shows the new exception before
    # the pipeline starts (which may take 30-60 s for the Claude calls).
    from datetime import timezone
    await ws_manager.broadcast({
        "event": "exception.created",
        "exception_id": exception.id,
        "tracking_number": shipment.tracking_number,
        "carrier": shipment.carrier,
        "customer_name": shipment.customer_name,
        "exception_type": webhook.event_type,
        "workflow_status": "pending",
        "detected_at": exception.detected_at.isoformat()
            if exception.detected_at else None,
        "shipment_id": shipment.id,
        "location": webhook.raw_payload.get("location"),
        "severity": None,
    })

    # ── Run agent pipeline ────────────────────────────────────────────────────
    # run_exception_workflow commits internally; after it returns the session
    # is in a clean state with a new implicit transaction.
    result = await run_exception_workflow(exception, db)

    _log.info(
        "webhook=%d  exception_id=%d  pipeline_status=%s",
        webhook_event_id, exception.id, result.workflow_status.value,
    )

    # ── Mark webhook as processed ─────────────────────────────────────────────
    # Re-fetch because the internal commit expired the ORM instance.
    webhook = await db.get(WebhookEvent, webhook_event_id)
    if webhook:
        webhook.status = WebhookStatus.PROCESSED
        webhook.processed_at = datetime.now(timezone.utc)
        await db.commit()


async def _mark_failed(webhook_event_id: int, error: str) -> None:
    """Open a fresh session to record a task-level failure."""
    try:
        async with AsyncSessionLocal() as db:
            webhook = await db.get(WebhookEvent, webhook_event_id)
            if webhook:
                webhook.status = WebhookStatus.FAILED
                webhook.error_message = error[:500]  # truncate for DB column
                webhook.processed_at = datetime.now(timezone.utc)
                await db.commit()
    except Exception:
        _log.exception(
            "Could not write FAILED status for webhook_event_id=%d", webhook_event_id
        )
