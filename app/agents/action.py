import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.schemas import ActionOutput, WorkflowContext
from app.models import Resolution, ShipmentException, WorkflowStatus

SYSTEM_PROMPT = """You are a logistics action execution agent. Given a resolution plan,
simulate and confirm the execution of each action. In production this agent would call
carrier APIs, update warehouse systems, and trigger reshipments.

For each action provided, produce an execution result.
Respond ONLY with a valid JSON object — no markdown, no explanation:
{
  "executed_actions": [
    {
      "action_type": "string",
      "status": "completed" | "failed" | "pending_external",
      "result": "description of what happened",
      "external_reference": null | "reference id or ticket number"
    }
  ],
  "overall_status": "resolved" | "partially_resolved" | "escalated",
  "next_review_date": null | "ISO date string",
  "notes": "any additional execution notes"
}"""


class ActionAgent(BaseAgent):
    name = "action_agent"

    async def run(
        self,
        exception: ShipmentException,
        db: AsyncSession,
        context: WorkflowContext,
    ) -> ActionOutput:
        self._start_timing()
        decision = context.decision
        analysis = context.analysis
        communication = context.communication
        customer_notified = bool(communication and not communication.skipped)

        actions_payload = (
            [a.model_dump() for a in decision.actions] if decision else []
        )
        user_message = (
            f"Resolution type: {decision.resolution_type if decision else 'N/A'}\n"
            f"Actions to execute:\n{json.dumps(actions_payload, indent=2)}\n"
            f"Customer notified: {customer_notified}\n"
            f"Analysis rationale: {analysis.root_cause if analysis else 'N/A'}"
        )

        try:
            raw = await self._call_claude(SYSTEM_PROMPT, user_message, max_tokens=1500)
            output = ActionOutput.model_validate(await self._parse_json(raw))

            resolution = Resolution(
                exception_id=exception.id,
                resolution_type=decision.resolution_type if decision else "unknown",
                root_cause=analysis.root_cause if analysis else "Unknown",
                customer_notified=customer_notified,
                customer_message=communication.message if communication else None,
                actions_taken=[a.model_dump() for a in output.executed_actions],
            )
            db.add(resolution)
            exception.workflow_status = WorkflowStatus.RESOLVED

            await self._record_action(
                db, exception.id,
                action_taken=(
                    f"Executed {len(output.executed_actions)} action(s) — "
                    f"overall status: {output.overall_status}"
                ),
                reasoning=output.notes,
            )
            await db.flush()
            return output

        except Exception as exc:
            self._log_failure(
                exception_id=exception.id,
                step="claude_api_or_execute",
                exc=exc,
                input_summary={
                    "resolution_type": (
                        decision.resolution_type if decision else None
                    ),
                    "n_actions": len(decision.actions) if decision else 0,
                    "customer_notified": customer_notified,
                },
            )
            await self._record_action(
                db, exception.id,
                action_taken="Action execution failed",
                reasoning=str(exc),
                status="failed",
                error_message=str(exc),
            )
            exception.workflow_status = WorkflowStatus.FAILED
            await db.flush()
            raise
