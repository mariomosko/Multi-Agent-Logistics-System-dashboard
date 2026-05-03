from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.schemas import CommunicationOutput, WorkflowContext
from app.models import ShipmentException, WorkflowStatus

SYSTEM_PROMPT = """You are a customer communication agent for a logistics company.
Draft empathetic, professional, and actionable customer notifications for shipment
exceptions.

The message should:
- Be concise (3-5 sentences)
- Acknowledge the issue without excessive apology
- State what is being done to resolve it
- Set clear expectations for next steps or timeline

Respond ONLY with a valid JSON object — no markdown, no explanation:
{
  "subject": "email subject line",
  "message": "the full customer-facing message",
  "tone": "apologetic" | "informational" | "urgent",
  "include_tracking_link": true | false
}"""


class CommunicationAgent(BaseAgent):
    name = "communication_agent"

    async def run(
        self,
        exception: ShipmentException,
        db: AsyncSession,
        context: WorkflowContext,
    ) -> CommunicationOutput:
        self._start_timing()
        decision = context.decision
        analysis = context.analysis
        shipment = exception.shipment

        if decision and not decision.notify_customer:
            skip_reason = "Decision agent determined customer notification not required"
            output = CommunicationOutput(
                skipped=True,
                reason=skip_reason,
                tone="informational",
            )
            await self._record_action(
                db, exception.id,
                action_taken="Customer notification skipped",
                reasoning=skip_reason,
            )
            exception.workflow_status = WorkflowStatus.ACTING
            await db.flush()
            return output

        user_message = (
            f"Customer name: {shipment.customer_name if shipment else 'Customer'}\n"
            f"Tracking number: {shipment.tracking_number if shipment else 'N/A'}\n"
            f"Issue: {exception.exception_type} "
            f"(severity: {exception.severity.value if exception.severity else 'unknown'})\n"
            f"Root cause: {analysis.root_cause if analysis else 'under investigation'}\n"
            f"Resolution being taken: "
            f"{decision.resolution_type if decision else 'under review'}\n"
            f"Estimated delay: "
            f"{analysis.estimated_delay_days if analysis else 'unknown'} days"
        )

        try:
            raw = await self._call_claude(SYSTEM_PROMPT, user_message, max_tokens=800)
            output = CommunicationOutput.model_validate(await self._parse_json(raw))

            exception.workflow_status = WorkflowStatus.ACTING

            await self._record_action(
                db, exception.id,
                action_taken=f"Customer notification drafted: \"{output.subject or ''}\"",
                reasoning=f"Tone: {output.tone}",
            )
            await db.flush()
            return output

        except Exception as exc:
            self._log_failure(
                exception_id=exception.id,
                step="claude_api_or_parse",
                exc=exc,
                input_summary={
                    "exception_type": exception.exception_type,
                    "resolution_type": (
                        context.decision.resolution_type if context.decision else None
                    ),
                    "notify_customer": (
                        context.decision.notify_customer if context.decision else None
                    ),
                    "tracking_number": (
                        exception.shipment.tracking_number
                        if exception.shipment else None
                    ),
                },
            )
            await self._record_action(
                db, exception.id,
                action_taken="Communication drafting failed",
                reasoning=str(exc),
                status="failed",
                error_message=str(exc),
            )
            exception.workflow_status = WorkflowStatus.FAILED
            await db.flush()
            raise
