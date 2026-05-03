"""
Circuit breaker for the Anthropic API.

States:
  CLOSED    — normal operation; failures are counted
  OPEN      — API is considered down; calls fail immediately without hitting the network
  HALF_OPEN — recovery test; a limited number of calls are allowed through

Transition rules:
  CLOSED  → OPEN      when consecutive_failures >= failure_threshold
  OPEN    → HALF_OPEN when recovery_timeout seconds have elapsed since last failure
  HALF_OPEN → CLOSED  when consecutive_successes >= success_threshold
  HALF_OPEN → OPEN    on any failure
"""
import logging
from datetime import datetime, timezone
from enum import Enum


class CircuitBreakerOpen(Exception):
    """Raised when a call is attempted while the circuit breaker is OPEN."""


class _State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
        name: str = "default",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.name = name

        self._state = _State.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_at: datetime | None = None
        self._log = logging.getLogger(f"circuit_breaker.{name}")

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state.value

    @property
    def is_open(self) -> bool:
        return self._state == _State.OPEN

    async def call(self, coro):
        """
        Await *coro* if the circuit allows it; raise CircuitBreakerOpen otherwise.
        Updates internal state based on outcome.
        """
        if self._state == _State.OPEN:
            if self._elapsed_since_failure() >= self.recovery_timeout:
                self._transition(_State.HALF_OPEN)
            else:
                remaining = self.recovery_timeout - self._elapsed_since_failure()
                raise CircuitBreakerOpen(
                    f"Circuit '{self.name}' is OPEN — retry in {remaining:.0f}s"
                )

        try:
            result = await coro
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    # ── State machine ─────────────────────────────────────────────────────────

    def _on_success(self) -> None:
        if self._state == _State.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._transition(_State.CLOSED)
        elif self._state == _State.CLOSED:
            # Reset streak on any success so we don't carry stale counts
            self._failure_count = 0

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_at = datetime.now(timezone.utc)

        if self._state == _State.HALF_OPEN:
            # Any failure during probe → back to OPEN
            self._transition(_State.OPEN)
        elif self._failure_count >= self.failure_threshold:
            self._transition(_State.OPEN)

    def _transition(self, new_state: _State) -> None:
        old = self._state
        self._state = new_state
        if new_state == _State.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == _State.HALF_OPEN:
            self._success_count = 0
        self._log.warning(
            "Transition %s → %s  (failures=%d)",
            old.value, new_state.value, self._failure_count,
        )

    def _elapsed_since_failure(self) -> float:
        if self._last_failure_at is None:
            return float("inf")
        return (datetime.now(timezone.utc) - self._last_failure_at).total_seconds()


# Shared singleton — imported by BaseAgent so all agents track the same API health
anthropic_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0,
    success_threshold=2,
    name="anthropic_api",
)
