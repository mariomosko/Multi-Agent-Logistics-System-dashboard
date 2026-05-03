import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.schemas import DetectionOutput, WorkflowContext
from app.models import ShipmentException, WorkflowStatus

SYSTEM_PROMPT = """You are a logistics exception detection agent. Analyze raw tracking
events and determine whether they represent an exception requiring intervention.
Exceptions include: delays, lost packages, damaged goods, address issues, customs holds,
or failed delivery attempts.

Respond ONLY with a valid JSON object — no markdown, no explanation:
{
  "is_exception": true | false,
  "exception_type": "delay" | "lost" | "damaged" | "address_issue" | "customs_hold" | "failed_delivery" | "other",
  "confidence": 0.0-1.0,
  "summary": "one-sentence description of what was detected"
}"""


class DetectionAgent(BaseAgent):
    name = "detection_agent"

    async def run(
        self,
        exception: ShipmentException,
        db: AsyncSession,
        context: WorkflowContext,
    ) -> DetectionOutput:
        self._start_timing()
        user_message = (
            f"Analyze this tracking event:\n"
            f"{json.dumps(exception.raw_event, indent=2)}"
        )

        try:
            raw = await self._call_claude(SYSTEM_PROMPT, user_message)
            output = DetectionOutput.model_validate(await self._parse_json(raw))

            if output.is_exception:
                exception.exception_type = output.exception_type
                exception.description = output.summary
                exception.workflow_status = WorkflowStatus.ANALYZING
                action_taken = (
                    f"Classified as '{output.exception_type}' exception "
                    f"({output.confidence:.0%} confidence)"
                )
            else:
                exception.workflow_status = WorkflowStatus.RESOLVED
                action_taken = "No exception detected — event is routine"

            await self._record_action(
                db, exception.id,
                action_taken=action_taken,
                reasoning=output.summary,
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
                    "event_type": exception.raw_event.get("event_type"),
                    "location": exception.raw_event.get("location"),
                },
            )
            await self._record_action(
                db, exception.id,
                action_taken="Detection failed",
                reasoning=str(exc),
                status="failed",
                error_message=str(exc),
            )
            exception.workflow_status = WorkflowStatus.FAILED
            await db.flush()
            raise
