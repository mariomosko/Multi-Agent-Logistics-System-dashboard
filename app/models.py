import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WebhookStatus(str, enum.Enum):
    RECEIVED = "received"       # logged, not yet processed
    PROCESSING = "processing"   # background task is running
    PROCESSED = "processed"     # pipeline completed (may still be FAILED in pipeline)
    IGNORED = "ignored"         # tracking number not in our system
    FAILED = "failed"           # background task itself crashed


class ShipmentStatus(str, enum.Enum):
    PENDING = "pending"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    EXCEPTION = "exception"


class ExceptionSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkflowStatus(str, enum.Enum):
    PENDING = "pending"
    DETECTING = "detecting"
    ANALYZING = "analyzing"
    DECIDING = "deciding"
    COMMUNICATING = "communicating"
    ACTING = "acting"
    RESOLVED = "resolved"
    FAILED = "failed"


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tracking_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[ShipmentStatus] = mapped_column(
        Enum(ShipmentStatus), default=ShipmentStatus.PENDING
    )
    carrier: Mapped[str] = mapped_column(String(100))
    origin: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(200))
    customer_name: Mapped[str] = mapped_column(String(200))
    customer_email: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    exceptions: Mapped[list["ShipmentException"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )


class ShipmentException(Base):
    __tablename__ = "shipment_exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id"), index=True)
    exception_type: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_event: Mapped[dict] = mapped_column(JSON)
    severity: Mapped[ExceptionSeverity | None] = mapped_column(
        Enum(ExceptionSeverity), nullable=True
    )
    workflow_status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus), default=WorkflowStatus.PENDING
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    shipment: Mapped["Shipment"] = relationship(back_populates="exceptions")
    agent_actions: Mapped[list["AgentAction"]] = relationship(
        back_populates="exception", cascade="all, delete-orphan"
    )
    resolution: Mapped["Resolution | None"] = relationship(
        back_populates="exception", uselist=False, cascade="all, delete-orphan"
    )


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exception_id: Mapped[int] = mapped_column(
        ForeignKey("shipment_exceptions.id"), index=True
    )
    agent_name: Mapped[str] = mapped_column(String(100), index=True)
    action_taken: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="completed")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Performance / cost tracking
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    exception: Mapped["ShipmentException"] = relationship(back_populates="agent_actions")


class Resolution(Base):
    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exception_id: Mapped[int] = mapped_column(
        ForeignKey("shipment_exceptions.id"), unique=True, index=True
    )
    resolution_type: Mapped[str] = mapped_column(String(100))
    root_cause: Mapped[str] = mapped_column(Text)
    customer_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    customer_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    actions_taken: Mapped[list] = mapped_column(JSON, default=list)
    completed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    exception: Mapped["ShipmentException"] = relationship(back_populates="resolution")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    carrier: Mapped[str] = mapped_column(String(100))
    tracking_number: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(100))
    raw_payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[WebhookStatus] = mapped_column(
        Enum(WebhookStatus), default=WebhookStatus.RECEIVED, index=True
    )
    # Set once the background task creates a ShipmentException
    exception_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipment_exceptions.id"), nullable=True, index=True
    )
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
