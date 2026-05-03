from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.schemas import DecisionOutput, WorkflowContext
from app.models import ShipmentException, WorkflowStatus

SYSTEM_PROMPT = """You are a logistics exception decision agent. Based on the exception
analysis, choose the optimal resolution path and define the concrete actions to take.

Respond ONLY with a valid JSON object — no markdown, no explanation:
{
  "resolution_type": "reroute" | "reship" | "refund" | "contact_carrier" | "schedule_redelivery" | "escalate" | "monitor",
  "actions": [
    {
      "action_type": "string describing the action",
      "priority": "high" | "medium" | "low",
      "description": "detailed description",
      "requires_customer_contact": true | false
    }
  ],
  "notify_customer": true | false,
  "notification_urgency": "immediate" | "same_day" | "next_day",
  "rationale": "explanation for this decision"
}"""


class DecisionAgent(BaseAgent):
    name = "decision_agent"

    async def run(
        self,
        exception: ShipmentException,
        db: AsyncSession,
        context: WorkflowContext,
    ) -> DecisionOutput:
        self._start_timing()
        analysis = context.analysis
        user_message = (
            f"Exception type: {exception.exception_type}\n"
            f"Severity: {exception.severity.value if exception.severity else 'unknown'}\n"
            f"Root cause: {analysis.root_cause if analysis else 'N/A'}\n"
            f"Impact factors: {analysis.impact_factors if analysis else []}\n"
            f"Estimated delay (days): "
            f"{analysis.estimated_delay_days if analysis else 'unknown'}\n"
            f"Recommended urgency: "
            f"{analysis.recommended_urgency if analysis else 'routine'}"
        )

        try:
            raw = await self._call_claude(SYSTEM_PROMPT, user_message, max_tokens=1500)
            output = DecisionOutput.model_validate(await self._parse_json(raw))

            exception.workflow_status = WorkflowStatus.COMMUNICATING

            await self._record_action(
                db, exception.id,
                action_taken=(
                    f"Resolution selected: '{output.resolution_type}' "
                    f"with {len(output.actions)} action(s) planned"
                ),
                reasoning=output.rationale,
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
                    "severity": (
                        exception.severity.value if exception.severity else None
                    ),
                    "root_cause": (
                        context.analysis.root_cause[:120] if context.analysis else None
                    ),
                },
            )
            await self._record_action(
                db, exception.id,
                action_taken="Decision failed",
                reasoning=str(exc),
                status="failed",
                error_message=str(exc),
            )
            exception.workflow_status = WorkflowStatus.FAILED
            await db.flush()
            raise
