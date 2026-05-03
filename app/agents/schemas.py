"""
Typed input/output contracts for each agent and the shared WorkflowContext
that carries accumulated outputs through the pipeline.
"""
from typing import Literal

from pydantic import BaseModel, Field


# ── Detection ────────────────────────────────────────────────────────────────

class DetectionOutput(BaseModel):
    is_exception: bool
    exception_type: Literal[
        "delay", "lost", "damaged", "address_issue",
        "customs_hold", "failed_delivery", "other"
    ] = "other"
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str


# ── Analysis ─────────────────────────────────────────────────────────────────

class AnalysisOutput(BaseModel):
    root_cause: str
    severity: Literal["low", "medium", "high", "critical"]
    impact_factors: list[str] = []
    estimated_delay_days: int | None = None
    recommended_urgency: Literal["routine", "expedited", "immediate"] = "routine"


# ── Decision ─────────────────────────────────────────────────────────────────

class PlannedAction(BaseModel):
    action_type: str
    priority: Literal["high", "medium", "low"]
    description: str
    requires_customer_contact: bool = False


class DecisionOutput(BaseModel):
    resolution_type: Literal[
        "reroute", "reship", "refund", "contact_carrier",
        "schedule_redelivery", "escalate", "monitor"
    ]
    actions: list[PlannedAction] = []
    notify_customer: bool
    notification_urgency: Literal["immediate", "same_day", "next_day"] = "same_day"
    rationale: str


# ── Communication ─────────────────────────────────────────────────────────────

class CommunicationOutput(BaseModel):
    subject: str | None = None
    message: str | None = None
    tone: Literal["apologetic", "informational", "urgent"] = "informational"
    include_tracking_link: bool = False
    skipped: bool = False
    reason: str | None = None


# ── Action ────────────────────────────────────────────────────────────────────

class ExecutedAction(BaseModel):
    action_type: str
    status: Literal["completed", "failed", "pending_external"]
    result: str
    external_reference: str | None = None


class ActionOutput(BaseModel):
    executed_actions: list[ExecutedAction] = []
    overall_status: Literal["resolved", "partially_resolved", "escalated"]
    next_review_date: str | None = None
    notes: str = ""


# ── Shared pipeline context ───────────────────────────────────────────────────

class WorkflowContext(BaseModel):
    """Accumulates typed agent outputs as the pipeline progresses."""
    detection: DetectionOutput | None = None
    analysis: AnalysisOutput | None = None
    decision: DecisionOutput | None = None
    communication: CommunicationOutput | None = None
    action: ActionOutput | None = None
