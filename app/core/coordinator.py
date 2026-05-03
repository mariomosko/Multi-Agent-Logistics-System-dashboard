"""
AgentCoordinator — orchestrates the 5-agent exception-handling pipeline.

Pipeline order:
    DetectionAgent → AnalysisAgent → DecisionAgent
    → CommunicationAgent → ActionAgent

Error handling layers (outermost to innermost):
  1. asyncio.wait_for      — per-agent hard timeout (45 s)
  2. CircuitBreakerOpen    — API considered down; fast-fail the pipeline
  3. Agent-level try/except — retries + structured logging inside each agent
  4. BaseAgent._call_claude — exponential backoff retry at the HTTP call level

WebSocket events emitted (via app.core.websocket_manager):
  pipeline.started   — once at the top, before the first agent
  agent.started      — each time an agent is about to run
  agent.completed    — each time an agent finishes successfully
  agent.failed       — on timeout, circuit-breaker, or agent error
  pipeline.resolved  — final status = RESOLVED
  pipeline.failed    — final status = FAILED
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.action import ActionAgent
from app.agents.analysis import AnalysisAgent
from app.agents.communication import CommunicationAgent
from app.agents.decision import DecisionAgent
from app.agents.detection import DetectionAgent
from app.agents.schemas import WorkflowContext
from app.core.circuit_breaker import CircuitBreakerOpen, anthropic_breaker
from app.core.websocket_manager import manager as ws_manager
from app.models import AgentAction, ShipmentException, WorkflowStatus
from app.schemas import WorkflowResult

_AGENT_TIMEOUT: float = 45.0

_PIPELINE: list[tuple[str, WorkflowStatus, Any]] = [
    ("detection",     WorkflowStatus.DETECTING,    DetectionAgent()),
    ("analysis",      WorkflowStatus.ANALYZING,     AnalysisAgent()),
    ("decision",      WorkflowStatus.DECIDING,      DecisionAgent()),
    ("communication", WorkflowStatus.COMMUNICATING, CommunicationAgent()),
    ("action",        WorkflowStatus.ACTING,        ActionAgent()),
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentCoordinator:
    """
    Stateless orchestrator — safe to instantiate once at module level and
    reuse across requests. All mutable state lives in the DB and the
    per-call WorkflowContext.
    """

    def __init__(self) -> None:
        self._log = logging.getLogger(__name__)

    async def run(
        self,
        exception: ShipmentException,
        db: AsyncSession,
    ) -> WorkflowResult:
        # Reload with shipment so CommunicationAgent can read customer details.
        result = await db.execute(
            select(ShipmentException)
            .where(ShipmentException.id == exception.id)
            .options(selectinload(ShipmentException.shipment))
        )
        exception = result.scalar_one()

        context = WorkflowContext()
        self._log.info("Pipeline started  exception=%d", exception.id)

        await ws_manager.broadcast({
            "event": "pipeline.started",
            "exception_id": exception.id,
            "tracking_number": exception.shipment.tracking_number if exception.shipment else None,
            "exception_type": exception.exception_type,
            "timestamp": _now_iso(),
        })

        for ctx_key, next_status, agent in _PIPELINE:
            # ── Early-exit guards ─────────────────────────────────────────
            if exception.workflow_status == WorkflowStatus.FAILED:
                self._log.warning(
                    "Pipeline aborted at '%s' — exception %d already FAILED",
                    ctx_key, exception.id,
                )
                break

            if ctx_key != "detection" and exception.workflow_status == WorkflowStatus.RESOLVED:
                self._log.info(
                    "Pipeline short-circuited after detection — not an exception (id=%d)",
                    exception.id,
                )
                break

            # ── Advance status ────────────────────────────────────────────
            exception.workflow_status = next_status
            await db.flush()
            self._log.info(
                "exception=%d  %-20s  status → %s",
                exception.id, agent.name, next_status.value,
            )

            await ws_manager.broadcast({
                "event": "agent.started",
                "exception_id": exception.id,
                "agent_name": agent.name,
                "workflow_status": next_status.value,
                "timestamp": _now_iso(),
            })

            # ── Run with timeout + error isolation ────────────────────────
            try:
                output = await asyncio.wait_for(
                    agent.run(exception, db, context),
                    timeout=_AGENT_TIMEOUT,
                )
                setattr(context, ctx_key, output)
                self._log.info("exception=%d  %s  ✓", exception.id, agent.name)

                # Fetch the AgentAction just flushed by the agent for timing/tokens
                last_action_row = await db.scalar(
                    select(AgentAction)
                    .where(
                        AgentAction.exception_id == exception.id,
                        AgentAction.agent_name == agent.name,
                        AgentAction.status == "completed",
                    )
                    .order_by(AgentAction.id.desc())
                )

                await ws_manager.broadcast({
                    "event": "agent.completed",
                    "exception_id": exception.id,
                    "agent_name": agent.name,
                    "workflow_status": exception.workflow_status.value,
                    "severity": exception.severity.value if exception.severity else None,
                    "duration_ms": last_action_row.duration_ms if last_action_row else None,
                    "input_tokens": last_action_row.input_tokens if last_action_row else None,
                    "output_tokens": last_action_row.output_tokens if last_action_row else None,
                    "output": output.model_dump(mode="json"),
                    "timestamp": _now_iso(),
                })

            except asyncio.TimeoutError:
                self._log.error(
                    "exception=%d  %s  timed out after %.0fs",
                    exception.id, agent.name, _AGENT_TIMEOUT,
                )
                await self._record_system_failure(
                    db, exception,
                    agent_name=agent.name,
                    action_taken=f"Agent timed out after {_AGENT_TIMEOUT:.0f}s",
                    reasoning="asyncio.TimeoutError — agent exceeded per-step deadline",
                )
                await ws_manager.broadcast({
                    "event": "agent.failed",
                    "exception_id": exception.id,
                    "agent_name": agent.name,
                    "workflow_status": "failed",
                    "reason": "timeout",
                    "timestamp": _now_iso(),
                })
                break

            except CircuitBreakerOpen as exc:
                self._log.error(
                    "exception=%d  %s  circuit breaker open: %s",
                    exception.id, agent.name, exc,
                )
                await self._record_system_failure(
                    db, exception,
                    agent_name=agent.name,
                    action_taken="Skipped — Anthropic API circuit breaker is OPEN",
                    reasoning=str(exc),
                )
                await ws_manager.broadcast({
                    "event": "agent.failed",
                    "exception_id": exception.id,
                    "agent_name": agent.name,
                    "workflow_status": "failed",
                    "reason": "circuit_breaker_open",
                    "timestamp": _now_iso(),
                })
                break

            except Exception as exc:
                # Agent already set FAILED + wrote AgentAction + flushed.
                self._log.error(
                    "exception=%d  %s  failed: %s  (circuit_state=%s)",
                    exception.id, agent.name, exc,
                    anthropic_breaker.state,
                )
                await ws_manager.broadcast({
                    "event": "agent.failed",
                    "exception_id": exception.id,
                    "agent_name": agent.name,
                    "workflow_status": "failed",
                    "reason": type(exc).__name__,
                    "timestamp": _now_iso(),
                })
                break

        await db.commit()
        self._log.info(
            "Pipeline complete  exception=%d  status=%s  circuit=%s",
            exception.id,
            exception.workflow_status.value,
            anthropic_breaker.state,
        )

        # Reload with child relations for response payload + final WS event
        result = await db.execute(
            select(ShipmentException)
            .where(ShipmentException.id == exception.id)
            .options(
                selectinload(ShipmentException.agent_actions),
                selectinload(ShipmentException.resolution),
            )
        )
        exception = result.scalar_one()

        final_status = exception.workflow_status.value
        resolution_type = (
            exception.resolution.resolution_type if exception.resolution else None
        )

        await ws_manager.broadcast({
            "event": "pipeline.resolved" if final_status == "resolved" else "pipeline.failed",
            "exception_id": exception.id,
            "workflow_status": final_status,
            "resolution_type": resolution_type,
            "timestamp": _now_iso(),
        })

        return WorkflowResult(
            exception_id=exception.id,
            workflow_status=exception.workflow_status,
            severity=exception.severity,
            resolution=exception.resolution,
            agent_actions=exception.agent_actions,
        )

    async def _record_system_failure(
        self,
        db: AsyncSession,
        exception: ShipmentException,
        agent_name: str,
        action_taken: str,
        reasoning: str,
    ) -> None:
        try:
            exception.workflow_status = WorkflowStatus.FAILED
            db.add(
                AgentAction(
                    exception_id=exception.id,
                    agent_name=agent_name,
                    action_taken=action_taken,
                    reasoning=reasoning,
                    status="failed",
                    error_message=action_taken,
                )
            )
            await db.flush()
        except Exception:
            self._log.exception(
                "Could not write system-failure record for exception %d", exception.id
            )
