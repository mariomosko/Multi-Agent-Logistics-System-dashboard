import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import BaseAgent
from app.agents.schemas import AnalysisOutput, WorkflowContext
from app.models import ExceptionSeverity, ShipmentException, WorkflowStatus

SYSTEM_PROMPT = """You are a logistics exception analysis agent. Given a confirmed
shipment exception, determine the root cause and severity so the decision agent can
choose the best resolution path.

Respond ONLY with a valid JSON object — no markdown, no explanation:
{
  "root_cause": "detailed explanation of why this exception occurred",
  "severity": "low" | "medium" | "high" | "critical",
  "impact_factors": ["list", "of", "contributing", "factors"],
  "estimated_delay_days": null | integer,
  "recommended_urgency": "routine" | "expedited" | "immediate"
}

Severity guide:
- low:      minor delay < 2 days, customer not yet expecting delivery
- medium:   delay 2-5 days or failed delivery attempt
- high:     delay > 5 days, damaged goods, or address issues
- critical: lost package, significant damage, or time-sensitive shipment"""

_SEVERITY_MAP = {
    "low": ExceptionSeverity.LOW,
    "medium": ExceptionSeverity.MEDIUM,
    "high": ExceptionSeverity.HIGH,
    "critical": ExceptionSeverity.CRITICAL,
}


class AnalysisAgent(BaseAgent):
    name = "analysis_agent"

    async def run(
        self,
        exception: ShipmentException,
        db: AsyncSession,
        context: WorkflowContext,
    ) -> AnalysisOutput:
        self._start_timing()
        detection = context.detection
        user_message = (
            f"Exception type: {exception.exception_type}\n"
            f"Description: {exception.description or 'N/A'}\n"
            f"Detection summary: {detection.summary if detection else 'N/A'}\n"
            f"Raw event data:\n{json.dumps(exception.raw_event, indent=2)}"
        )

        try:
            raw = await self._call_claude(SYSTEM_PROMPT, user_message, max_tokens=1500)
            output = AnalysisOutput.model_validate(await self._parse_json(raw))

            exception.severity = _SEVERITY_MAP.get(output.severity)
            exception.workflow_status = WorkflowStatus.DECIDING

            delay_str = (
                f"{output.estimated_delay_days} day(s)"
                if output.estimated_delay_days is not None
                else "unknown"
            )
            await self._record_action(
                db, exception.id,
                action_taken=(
                    f"Severity assessed as '{output.severity}'; "
                    f"estimated delay: {delay_str}"
                ),
                reasoning=output.root_cause,
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
                    "description": exception.description,
                    "detection_summary": (
                        context.detection.summary if context.detection else None
                    ),
                },
            )
            await self._record_action(
                db, exception.id,
                action_taken="Analysis failed",
                reasoning=str(exc),
                status="failed",
                error_message=str(exc),
            )
            exception.workflow_status = WorkflowStatus.FAILED
            await db.flush()
            raise
