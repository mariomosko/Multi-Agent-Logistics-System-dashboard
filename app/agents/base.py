import asyncio
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from typing import Any

import anthropic
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import WorkflowContext
from app.core.circuit_breaker import CircuitBreakerOpen, anthropic_breaker
from app.core.config import settings
from app.models import AgentAction, ShipmentException

_RETRYABLE = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)


class BaseAgent(ABC):
    name: str

    def __init__(self) -> None:
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=httpx.Timeout(30.0, connect=5.0),
        )
        self.model = settings.claude_model
        self._log = logging.getLogger(f"agents.{self.__class__.__name__}")
        # Set by _start_timing(); read by _record_action()
        self._run_start_time: float | None = None
        # Set by _call_claude() on success; read by _record_action()
        self._last_input_tokens: int | None = None
        self._last_output_tokens: int | None = None

    @abstractmethod
    async def run(
        self,
        exception: ShipmentException,
        db: AsyncSession,
        context: WorkflowContext,
    ) -> Any: ...

    # ── Timing ────────────────────────────────────────────────────────────────

    def _start_timing(self) -> None:
        """Call at the top of each agent's run() to capture wall-clock start."""
        self._run_start_time = time.monotonic()
        self._last_input_tokens = None
        self._last_output_tokens = None

    def _elapsed_ms(self) -> int | None:
        if self._run_start_time is None:
            return None
        return int((time.monotonic() - self._run_start_time) * 1000)

    # ── Claude API helpers ────────────────────────────────────────────────────

    async def _call_claude(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 1024,
    ) -> str:
        """
        Call Claude through the circuit breaker with exponential-backoff retry.
        Stores token counts in self._last_input_tokens / _last_output_tokens on success.
        """
        last_exc: Exception | None = None

        for attempt in range(1, 4):
            try:
                response = await anthropic_breaker.call(
                    self.client.messages.create(
                        model=self.model,
                        max_tokens=max_tokens,
                        system=system_prompt,
                        messages=[{"role": "user", "content": user_message}],
                    )
                )
                # Capture usage for cost tracking
                self._last_input_tokens = response.usage.input_tokens
                self._last_output_tokens = response.usage.output_tokens
                return response.content[0].text

            except CircuitBreakerOpen:
                raise

            except anthropic.RateLimitError as exc:
                last_exc = exc
                if attempt == 3:
                    break
                retry_after: float | None = None
                if getattr(exc, "response", None) is not None:
                    raw = exc.response.headers.get("retry-after")
                    retry_after = float(raw) if raw else None
                wait = retry_after if retry_after else (2 ** attempt) + random.uniform(0, 1)
                self._log.warning(
                    "RateLimitError attempt %d/3 — waiting %.1fs (Retry-After=%s)",
                    attempt, wait, retry_after,
                )
                await asyncio.sleep(wait)

            except (anthropic.APIConnectionError, anthropic.InternalServerError) as exc:
                last_exc = exc
                if attempt == 3:
                    break
                wait = (2 ** attempt) + random.uniform(0, 1)
                self._log.warning(
                    "%s attempt %d/3 — waiting %.1fs",
                    type(exc).__name__, attempt, wait,
                )
                await asyncio.sleep(wait)

            except anthropic.APIError:
                raise

        raise last_exc  # type: ignore[misc]

    async def _parse_json(self, raw: str) -> dict[str, Any]:
        """
        Strip code fences, parse JSON. One self-repair attempt on failure
        (routed through _call_claude so repair benefits from retry + circuit breaker).
        """
        cleaned = _strip_fences(raw)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            self._log.warning("JSON parse failed — requesting self-repair")

        repaired = await self._call_claude(
            system_prompt="You are a JSON repair tool. Return ONLY valid JSON — no markdown.",
            user_message=(
                "The text below is malformed JSON. Return the corrected JSON:\n\n" + raw
            ),
            max_tokens=2048,
        )

        try:
            return json.loads(_strip_fences(repaired))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Claude returned malformed JSON even after self-repair.\n"
                f"Original: {raw[:200]!r}\nRepaired: {repaired[:200]!r}"
            ) from exc

    # ── Structured error logging ──────────────────────────────────────────────

    def _log_failure(
        self,
        *,
        exception_id: int,
        step: str,
        exc: Exception,
        input_summary: dict[str, Any] | None = None,
    ) -> None:
        self._log.error(
            "Agent failure\n"
            "  agent      : %s\n"
            "  exception  : %d\n"
            "  step       : %s\n"
            "  error_type : %s\n"
            "  detail     : %s\n"
            "  input      : %s",
            self.name, exception_id, step,
            type(exc).__name__, exc, input_summary or {},
            exc_info=True,
        )

    # ── Database helpers ──────────────────────────────────────────────────────

    async def _record_action(
        self,
        db: AsyncSession,
        exception_id: int,
        action_taken: str,
        reasoning: str,
        status: str = "completed",
        error_message: str | None = None,
    ) -> AgentAction:
        """
        Persist an AgentAction row. Automatically captures timing and token
        counts from _start_timing() and _call_claude() instance state.
        """
        action = AgentAction(
            exception_id=exception_id,
            agent_name=self.name,
            action_taken=action_taken,
            reasoning=reasoning,
            status=status,
            error_message=error_message,
            duration_ms=self._elapsed_ms(),
            input_tokens=self._last_input_tokens,
            output_tokens=self._last_output_tokens,
        )
        db.add(action)
        await db.flush()
        return action


def _strip_fences(text: str) -> str:
    lines = text.strip().splitlines()
    return "\n".join(line for line in lines if not line.strip().startswith("```"))
