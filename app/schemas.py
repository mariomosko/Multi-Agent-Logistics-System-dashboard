from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models import ExceptionSeverity, ShipmentStatus, WebhookStatus, WorkflowStatus


# Shipment schemas
class ShipmentCreate(BaseModel):
    tracking_number: str
    origin: str
    destination: str
    carrier: str
    customer_name: str
    customer_email: str


class ShipmentRead(ShipmentCreate):
    id: int
    status: ShipmentStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Tracking event schema (payload sent by carrier webhooks or manual trigger)
class TrackingEvent(BaseModel):
    tracking_number: str
    event_type: str
    event_timestamp: datetime
    location: str
    description: str
    carrier_code: str | None = None
    metadata: dict[str, Any] = {}


# Exception schemas
class ExceptionRead(BaseModel):
    id: int
    shipment_id: int
    exception_type: str
    description: str | None
    severity: ExceptionSeverity | None
    workflow_status: WorkflowStatus
    detected_at: datetime

    model_config = {"from_attributes": True}


# Agent action schema
class AgentActionRead(BaseModel):
    id: int
    exception_id: int
    agent_name: str
    action_taken: str
    reasoning: str
    status: str
    error_message: str | None
    timestamp: datetime

    model_config = {"from_attributes": True}


# Resolution schema
class ResolutionRead(BaseModel):
    id: int
    exception_id: int
    resolution_type: str
    root_cause: str
    customer_notified: bool
    customer_message: str | None
    actions_taken: list[Any]
    completed_at: datetime

    model_config = {"from_attributes": True}


# ── Webhook schemas ───────────────────────────────────────────────────────────

class TrackingUpdatePayload(BaseModel):
    """Carrier webhook payload — simulates what FedEx/UPS/USPS would POST."""
    carrier: str = Field(min_length=1, max_length=100)
    tracking_number: str = Field(min_length=1, max_length=100)
    event_type: str = Field(
        min_length=1,
        max_length=100,
        description="e.g. delay, damaged, failed_delivery, customs_hold, lost",
    )
    event_timestamp: datetime
    location: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=1000)
    status_code: str | None = Field(
        default=None,
        description="Carrier-specific status code, e.g. 'DE', 'DL', 'AG'",
    )
    metadata: dict[str, Any] = {}


class WebhookAck(BaseModel):
    """Immediate 202 response returned before async processing begins."""
    status: Literal["accepted"] = "accepted"
    webhook_event_id: int
    tracking_number: str
    message: str


class WebhookEventRead(BaseModel):
    id: int
    carrier: str
    tracking_number: str
    event_type: str
    status: WebhookStatus
    exception_id: int | None
    received_at: datetime
    processed_at: datetime | None
    error_message: str | None

    model_config = {"from_attributes": True}


# ── Workflow response ─────────────────────────────────────────────────────────

class WorkflowResult(BaseModel):
    exception_id: int
    workflow_status: WorkflowStatus
    severity: ExceptionSeverity | None
    resolution: ResolutionRead | None
    agent_actions: list[AgentActionRead]


# ── Monitoring schemas ────────────────────────────────────────────────────────

class AgentActionReadFull(AgentActionRead):
    """AgentActionRead extended with cost-tracking fields."""
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None

    model_config = {"from_attributes": True}


class ExceptionSummary(BaseModel):
    """Row returned by GET /exceptions."""
    id: int
    shipment_id: int
    tracking_number: str
    carrier: str
    exception_type: str
    severity: ExceptionSeverity | None
    workflow_status: WorkflowStatus
    detected_at: datetime
    customer_name: str

    model_config = {"from_attributes": True}


class PaginatedExceptions(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ExceptionSummary]


class ExceptionDetail(BaseModel):
    """Full record returned by GET /exceptions/{id}."""
    id: int
    shipment_id: int
    tracking_number: str
    carrier: str
    customer_name: str
    customer_email: str
    exception_type: str
    description: str | None
    severity: ExceptionSeverity | None
    workflow_status: WorkflowStatus
    detected_at: datetime
    raw_event: dict[str, Any]
    agent_actions: list[AgentActionReadFull]
    resolution: ResolutionRead | None

    model_config = {"from_attributes": True}


class AgentMetrics(BaseModel):
    """Per-agent stats for GET /agents/performance."""
    agent_name: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float                  # 0.0–1.0
    avg_duration_ms: float | None
    p95_duration_ms: float | None
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float


class PerformanceReport(BaseModel):
    """Response model for GET /agents/performance."""
    generated_at: datetime
    total_exceptions_processed: int
    exceptions_by_status: dict[str, int]
    agents: list[AgentMetrics]
    total_estimated_cost_usd: float
