# Architecture

This document explains the key design decisions behind the Multi-Agent Logistics System — why the pipeline is structured the way it is, how the pieces coordinate, and how the system handles failure.

---

## Why 5 agents instead of 1 monolithic prompt?

The obvious alternative is a single large Claude call:

```
"Given this tracking event and shipment history, classify the exception,
determine the root cause, choose a resolution, draft a customer email,
and output a full action plan."
```

This works at small scale but breaks in several ways as complexity grows.

### Context window pressure

A monolithic prompt must carry every instruction for every task simultaneously. For a production logistics system, each concern accumulates detail quickly: detection needs carrier code tables, analysis needs historical patterns, decision needs policy rules and cost thresholds, communication needs brand voice guidelines, action needs API call specs. A single prompt bloated with all of this competes against itself — the model's attention is divided and the signal-to-noise ratio drops.

With 5 agents, each prompt is focused. The detection agent's prompt is ~20 lines. It does one thing: classify whether a carrier event is a real exception.

### Independent auditability and testability

Each agent writes an `AgentAction` row with its `action_taken`, `reasoning`, `duration_ms`, and token counts. You can query exactly what the detection agent said about exception #42, independently of what the decision agent said. A monolithic output is a single blob — you can't tell which part of the reasoning led to which output field.

The audit trail maps directly to regulatory requirements: if a customer disputes a reship decision, you have a complete reasoning chain from raw event to customer email.

### Failure isolation

If the communication agent times out, the exception has already been detected, analyzed, and decided. The coordinator can retry just the communication step, or fail it gracefully and still record the resolution type. With a monolithic agent, a timeout anywhere means losing all outputs.

### Different prompting strategies per stage

Detection benefits from a short, strict prompt that returns a binary judgment fast. Analysis benefits from chain-of-thought reasoning over historical context. Decision benefits from explicit policy constraints. Communication benefits from brand-voice and tone guidelines. These are fundamentally different prompting problems, and forcing them into one call means compromising on all of them.

### Parallelization headroom

The current pipeline is sequential because each agent depends on the previous one's output. But Detection and a hypothetical "fraud check" agent could run in parallel — the coordinator architecture supports this without restructuring any agent code, just changing the loop.

---

## How agents coordinate

### The WorkflowContext

```python
@dataclass
class WorkflowContext:
    detection:     DetectionOutput     | None = None
    analysis:      AnalysisOutput      | None = None
    decision:      DecisionOutput      | None = None
    communication: CommunicationOutput | None = None
    action:        ActionOutput        | None = None
```

`WorkflowContext` is the message-passing bus between agents. It starts empty and is populated as each agent completes. Agents access previous outputs through typed fields — the analysis agent reads `context.detection.exception_type`, the decision agent reads `context.analysis.severity`, and so on.

The context is not persisted between requests. It lives only for the duration of one pipeline run. Long-term storage is in `AgentAction` rows, which the monitoring endpoints expose.

### The coordinator loop

```python
_PIPELINE = [
    ("detection",     WorkflowStatus.DETECTING,    DetectionAgent()),
    ("analysis",      WorkflowStatus.ANALYZING,     AnalysisAgent()),
    ("decision",      WorkflowStatus.DECIDING,      DecisionAgent()),
    ("communication", WorkflowStatus.COMMUNICATING, CommunicationAgent()),
    ("action",        WorkflowStatus.ACTING,        ActionAgent()),
]
```

The coordinator iterates this list. For each step it:

1. Updates `exception.workflow_status` in the DB and flushes (so the REST polling endpoint reflects current state immediately)
2. Broadcasts `agent.started` over WebSocket
3. Calls `agent.run()` wrapped in `asyncio.wait_for()` with a 45-second timeout
4. On success: stores the output in `context`, broadcasts `agent.completed` with full output + timing + tokens
5. On failure: broadcasts `agent.failed`, writes a system failure `AgentAction` row, breaks out of the loop

### Short-circuit for non-exceptions

The detection agent can return `is_exception: false`. The coordinator checks for this after detection and resolves the exception immediately with status `RESOLVED` — the remaining 4 agents are skipped. This avoids billing for analysis/decision/communication/action on events that turn out to be routine scan updates.

### Background task isolation

Pipelines run in `BackgroundTasks` (FastAPI's built-in background task runner). The webhook endpoint and simulate endpoint both return immediately (`202 Accepted`) and pass the work off. Each background run opens its own `AsyncSessionLocal()` session — the request session is closed as soon as the response is sent and cannot be reused.

---

## Error handling strategy

There are four nested layers of error handling, from outermost to innermost:

```
┌─ asyncio.wait_for (coordinator) ─────────────────────────────────────┐
│  ┌─ CircuitBreakerOpen (coordinator) ───────────────────────────────┐ │
│  │  ┌─ agent-level try/except ──────────────────────────────────┐  │ │
│  │  │  ┌─ BaseAgent._call_claude (exponential backoff) ───────┐ │  │ │
│  │  │  │   up to 3 attempts, respects Retry-After header      │ │  │ │
│  │  │  └───────────────────────────────────────────────────── ┘ │  │ │
│  │  └───────────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Layer 1: Per-agent timeout (45 seconds)

`asyncio.wait_for()` wraps every agent call. If the Anthropic API hangs (e.g. a malformed streaming response that never closes), the coordinator unblocks after 45 seconds, marks the exception FAILED, and moves on. Without this, a single stuck HTTP call would block the event loop slot indefinitely.

### Layer 2: Circuit breaker

The circuit breaker tracks consecutive Anthropic API failures across all agents. After 5 consecutive failures, it trips OPEN for 60 seconds — all agent calls fail immediately with `CircuitBreakerOpen` instead of spending 45 seconds timing out each one.

```
CLOSED ──(5 failures)──► OPEN ──(60s elapsed)──► HALF_OPEN
                                                       │
                         CLOSED ◄──(1 success)────────┤
                           OPEN ◄──(1 failure)─────────┘
```

This protects against: cascading timeouts when the API is down, rate-limit storms, and accidental API key expiry consuming all pipeline slots.

### Layer 3: Agent-level exception handler

Each agent wraps its `_call_claude()` call. If Claude returns unparseable JSON, `_parse_json()` makes one self-repair attempt (asks Claude to fix its own output). If the second attempt also fails, the exception propagates to the coordinator which marks the pipeline FAILED.

### Layer 4: HTTP retry with exponential backoff

`BaseAgent._call_claude()` retries up to 3 times with exponential backoff for:
- `RateLimitError` — respects the `Retry-After` response header if present
- `APIConnectionError` — network blips
- `InternalServerError` — transient 5xx from the API

`CircuitBreakerOpen` is re-raised immediately (no retry). Other `APIError` subclasses are re-raised immediately (e.g. authentication failures, which retrying won't fix).

---

## Database schema

```
shipments
    id, tracking_number, carrier, origin, destination
    customer_name, customer_email, status, created_at

shipment_exceptions
    id, shipment_id → shipments.id
    exception_type, description, raw_event (JSON)
    severity, workflow_status, detected_at

agent_actions
    id, exception_id → shipment_exceptions.id
    agent_name, status, action_taken, reasoning
    input_tokens, output_tokens, duration_ms, created_at

resolutions
    id, exception_id → shipment_exceptions.id (unique)
    resolution_type, root_cause, customer_message
    actions_taken (JSON), resolved_at

webhook_events
    id, tracking_number, raw_payload (JSON)
    status, processed_at, error_message
```

**`agent_actions` is append-only.** If an agent is retried after a failure (future feature), each attempt gets its own row. The coordinator queries the most recent `completed` row for a given `(exception_id, agent_name)` pair to get timing and tokens for the WebSocket broadcast.

**`resolutions` is one-to-one with exceptions.** The action agent writes it. Resolution queries use `LEFT OUTER JOIN` so pre-resolved exceptions surface even when no action agent ran.

---

## Real-time transport

### Why WebSocket instead of SSE

The dashboard is read-only, so SSE (server-sent events) would technically suffice for pushing events. WebSocket was chosen because:

1. The simulate button sends a `POST /simulate/exception` request — a second HTTP round-trip per scenario. In a more tightly coupled design, the trigger could be sent *over* the WebSocket, eliminating the extra HTTP call. The current architecture keeps them separate for clarity, but the WS channel is ready for it.
2. FastAPI's WebSocket support is first-class and requires no extra dependencies, while SSE via `StreamingResponse` requires more careful keepalive and reconnection handling.

### ConnectionManager

```python
class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def broadcast(self, payload: dict) -> None:
        text = json.dumps(payload, default=str)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
```

The manager is a module-level singleton, shared across all requests within a process. It silently prunes connections that raise on send (client navigated away, network dropped).

**Important:** this design works for a single-process deployment. In a multi-worker setup (e.g. `uvicorn --workers 4`), each worker has its own in-process singleton — a WebSocket connected to worker 1 won't receive events from a pipeline running on worker 3. The fix is to move `broadcast()` to a Redis pub/sub channel that all workers subscribe to. The interface (`manager.broadcast(payload)`) is unchanged; only the implementation swaps.

### Frontend state machine

The React hook `useExceptionStream` maintains the full exceptions array as a single piece of state. Each incoming WebSocket event is applied by `applyWsEvent()` — a pure function that returns a new array without mutating the old one. React's reconciler diffs the new array and re-renders only the affected components.

```
Initial REST load:   exceptions = normalizeSummary(items)
WS event arrives:    exceptions = applyWsEvent(exceptions, msg)
Exception selected:  if no outputs → fetch GET /monitoring/exceptions/{id}
                     merge normalizeDetail(response) into component state
```

This two-phase approach (REST for history, WebSocket for live) means the dashboard never shows an empty state — historical data from the seed script is available the moment the page loads.

---

## Scaling considerations

The current stack is intentionally simple: one Python process, one SQLite file, one Vite dev server. Here is what changes when usage grows:

### Vertical limit: SQLite → PostgreSQL

SQLite serializes all writes through a single file lock. Under concurrent load (multiple webhooks arriving simultaneously), pipelines queue behind each other at the DB layer. Switching to PostgreSQL is a one-line change in `.env`:

```
DATABASE_URL=postgresql+asyncpg://user:pass@host/dbname
```

SQLAlchemy's async engine abstracts the dialect. No application code changes.

### Horizontal limit: multi-worker WebSocket

As noted above, multi-worker WebSocket requires a pub/sub broker. Redis is the standard choice:

```python
# websocket_manager.py (multi-worker version)
async def broadcast(self, payload: dict) -> None:
    await redis.publish("ws:events", json.dumps(payload))

# each worker subscribes and fans out to its local connections
async def _redis_listener(self):
    async for message in redis.subscribe("ws:events"):
        for ws in self._connections:
            await ws.send_text(message)
```

### Throughput limit: background tasks

`BackgroundTasks` runs in the same event loop as the request handler. Under high load, many in-flight pipelines compete for the same event loop. The fix is to push pipeline work to a task queue (Celery + Redis, or SAQ + Redis). The coordinator code doesn't change — only the dispatch mechanism moves from `background_tasks.add_task(...)` to `queue.enqueue(...)`.

### Cost control

Each agent call records `input_tokens` and `output_tokens`. The `GET /monitoring/agents/performance` endpoint aggregates these. A soft budget limit can be enforced in `BaseAgent._call_claude()` by checking cumulative spend before each call and raising a custom exception if a threshold is exceeded — the coordinator handles it like any other failure.

### Observability

Each `AgentAction` row has `duration_ms`. Slow agents (consistently over 10 seconds) indicate either a prompt that generates very long outputs or an API latency issue. Adding a Prometheus counter and histogram around `_call_claude()` and wiring it to Grafana is straightforward — the timing infrastructure is already in place.
