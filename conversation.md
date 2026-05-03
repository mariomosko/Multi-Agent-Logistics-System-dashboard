# Conversation Log — Multi-Agent Logistics System

---

## Turn 1

**Date:** 2026-05-01

**User:**
> Create a new FastAPI project for a multi-agent logistics workflow system.
>
> The system should handle shipment exceptions using 5 specialized AI agents:
> 1. Detection Agent - monitors tracking updates
> 2. Analysis Agent - determines root cause and severity
> 3. Decision Agent - chooses resolution path
> 4. Communication Agent - drafts customer notifications
> 5. Action Agent - executes solutions
>
> Set up the project structure with:
> - FastAPI backend
> - SQLite database for state tracking
> - Proper Python project structure (requirements.txt, .env, etc)
> - Basic README
>
> Use Python 3.11+ and include type hints everywhere.
> please also create a conversation file and keep track of my prompts and your responses

**Assistant:**

Created the full project from scratch. Here is a summary of every file produced:

### Project structure

```
Multi-Agent Logistics System/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app, lifespan, CORS, router registration
│   ├── database.py                # SQLAlchemy async engine, session factory, init_db
│   ├── models.py                  # ORM: Shipment, ShipmentException, AgentStep, Resolution
│   ├── schemas.py                 # Pydantic v2 request/response schemas
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                # BaseAgent: Claude client, _call_claude, _record_step
│   │   ├── detection.py           # DetectionAgent — classifies tracking events
│   │   ├── analysis.py            # AnalysisAgent — root cause + severity
│   │   ├── decision.py            # DecisionAgent — resolution path selection
│   │   ├── communication.py       # CommunicationAgent — customer email drafting
│   │   └── action.py              # ActionAgent — simulates resolution execution
│   ├── api/
│   │   ├── __init__.py
│   │   └── endpoints/
│   │       ├── __init__.py
│   │       ├── shipments.py       # CRUD for Shipment records
│   │       └── workflow.py        # POST /trigger, GET /exceptions
│   └── core/
│       ├── __init__.py
│       ├── config.py              # Pydantic settings (reads .env)
│       └── workflow.py            # run_exception_workflow — orchestrates all 5 agents
├── tests/
│   ├── __init__.py
│   └── test_workflow.py           # Health check + shipment CRUD tests
├── requirements.txt
├── .env / .env.example
├── README.md
└── conversation.md                # This file
```

### Key design decisions

- **Sequential pipeline** — each agent receives a shared `context` dict accumulating prior agents' outputs, allowing later agents (e.g. Communication) to reference Analysis results without re-querying Claude.
- **SQLite + aiosqlite** — zero-dependency async persistence; easy to swap for Postgres by changing `DATABASE_URL`.
- **All agents call `claude-sonnet-4-6`** via structured JSON prompts; each agent's system prompt is strict JSON-only to keep parsing reliable.
- **Early exit** — if Detection determines the event is not an exception, the workflow short-circuits to `RESOLVED` without running the remaining four agents.
- **AgentStep records** — every agent call writes an `agent_steps` row with input/output/status, giving a full audit trail per exception.

---

## Turn 2

**Date:** 2026-05-01

**User:**
> How would this project structure handle:
> 1. Multiple environment configurations (dev, staging, prod)?
> 2. Different database backends if we wanted to switch from SQLite to Postgres later?
> 3. Running multiple instances of this service for load balancing?

**Assistant:**

### 1. Multiple environment configs

`app/core/config.py` already handles this well — Pydantic Settings loads from `.env` but environment variables always win. The simplest pattern is to set `APP_ENV` at the process level and never commit environment-specific `.env` files:

```
.env.example   ← committed, documents all keys
.env           ← local dev only, gitignored
```

In staging/prod you inject vars directly (Docker env, Kubernetes secrets, AWS Secrets Manager). The one gap is that `Settings` has no validation enforcing prod-required fields (like `ANTHROPIC_API_KEY` being non-empty). A `model_validator` on `Settings` can catch that at startup rather than at first agent call.

### 2. Switching to Postgres

It's a one-line change in `.env`: `DATABASE_URL=postgresql+asyncpg://user:pass@host/db`. SQLAlchemy's async layer abstracts the dialect completely — models, queries, and session handling are all identical. The only friction:

- Swap `aiosqlite` for `asyncpg` in `requirements.txt`
- `func.now()` in `app/models.py` is standard SQL and portable, so no model changes needed
- The `JSON` column type works in both, but Postgres gives you `JSONB` (indexable) — worth upgrading those columns when migrating

### 3. Multiple instances / load balancing

SQLite becomes the hard blocker here — it uses file-level locking and will break under concurrent writes from multiple processes. With Postgres that concern disappears.

The bigger issue is that `run_exception_workflow` in `app/core/workflow.py` runs synchronously inside a request (5 Claude API calls, potentially 5–15 seconds). Under load balancing that ties up a worker per in-flight request. The right fix is a task queue: store the exception, enqueue a job (Celery + Redis, or ARQ for async), and have workers pull from the queue independently. The `/trigger` endpoint returns a `202 Accepted` with the `exception_id`, and clients poll `/exceptions/{id}` for status.

**Recommendation:** Don't change anything yet unless moving toward staging — but keep the Postgres + task queue path in mind as the natural next step for real concurrency. The current architecture makes that migration straightforward since the workflow logic is already isolated in `workflow.py` and the DB layer is pure SQLAlchemy.

---

## Turn 3

**Date:** 2026-05-01

**User:**
> Why did you choose this directory structure over alternatives like:
> - Putting all agents in a single file vs separate modules?
> - Using a services/ folder vs keeping business logic in routers?
>
> What are the tradeoffs of each approach?

**Assistant:**

### Agents: one file vs separate modules

Separate modules was the right call here because each agent has its own system prompt, unique input/output shape, and will likely diverge further as you tune them (e.g. adding tool use to ActionAgent, streaming to CommunicationAgent). One file works fine up to ~3 small agents; beyond that, a single file becomes hard to diff, test in isolation, or hand to a teammate to own. The cost is a few extra imports — negligible.

The case *for* a single file: if the agents were nearly identical in structure (same prompt pattern, same I/O), a single file with a factory function would reduce duplication. That's not true here since each agent has distinct logic and prompts.

### Services layer vs logic in routers

The current structure already has an implicit services layer — `app/core/workflow.py` is the service, and the router in `app/api/endpoints/workflow.py` just wires HTTP to it. This is the right separation: routers own request/response translation (HTTP status codes, dependency injection), services own business logic. The router has no idea how agents work; the workflow orchestrator has no idea it's being called over HTTP.

The alternative — putting `run_exception_workflow` directly in the router — would work fine at this scale but makes the logic harder to call from tests, a CLI, or a background worker without going through FastAPI's request cycle.

A fully explicit `services/` folder (separate from `core/`) would make sense if there were multiple distinct business domains — e.g. `services/billing.py`, `services/notifications.py`. For a single-domain system, `core/` is specific enough.

### Summary

| Decision | Chosen | Alternative | When to flip |
|---|---|---|---|
| Agent files | One per agent | Single `agents.py` | If agents become nearly identical (factory pattern) |
| Business logic | `core/workflow.py` | Inside router | If the system stays < 2 endpoints and never needs a worker |

---

## Turn 4

**Date:** 2026-05-02

**User:**
> Design and implement the SQLite database schema for this system. We need to track:
> - Shipments (id, tracking_number, status, carrier, destination, created_at)
> - Exceptions (id, shipment_id, exception_type, description, severity, detected_at)
> - Agent_Actions (id, exception_id, agent_name, action_taken, reasoning, timestamp)
> - Resolutions (id, exception_id, resolution_type, customer_notified, completed_at)
>
> Create the models using SQLAlchemy and include a database initialization script.

**Assistant:**

Rewrote the schema across 8 existing files and created 2 new ones to align with the specified design. Here is a full accounting of every change:

### Schema changes (`app/models.py`)

| Table | Change |
|---|---|
| `shipments` | Added `status` column (`ShipmentStatus` enum: pending / in_transit / delivered / exception) |
| `shipment_exceptions` | Added `description` (Text); renamed `created_at` → `detected_at`; kept `raw_event` (JSON) and `workflow_status` which the agent pipeline requires |
| `agent_steps` → `agent_actions` | Renamed table and ORM class; replaced `input_data` / `output_data` / `started_at` / `completed_at` with `action_taken` (Text), `reasoning` (Text), `timestamp` |
| `resolutions` | Added `customer_notified` (Boolean); renamed `resolved_at` → `completed_at`; kept `root_cause`, `customer_message`, `actions_taken` |

### Cascading updates

- **`app/schemas.py`** — `AgentStepRead` → `AgentActionRead` with new fields; `ShipmentRead` gains `status`; `ExceptionRead` gains `description`, uses `detected_at`; `ResolutionRead` gains `customer_notified`, uses `completed_at`; `WorkflowResult.agent_steps` → `agent_actions`
- **`app/agents/base.py`** — `_record_step()` → `_record_action(action_taken, reasoning)` with explicit text fields replacing the JSON blob
- **All 5 agent files** — each agent now derives a human-readable `action_taken` string and a `reasoning` string from its Claude response before calling `_record_action`; `DetectionAgent` also populates `ShipmentException.description`
- **`app/core/workflow.py`** and **`app/api/endpoints/workflow.py`** — updated `selectinload` and `WorkflowResult` construction to use `agent_actions`

### New files

- **`scripts/init_db.py`** — standalone async init script; run with `python -m scripts.init_db` to create tables, add `--seed` to insert 3 sample shipments
- **`scripts/__init__.py`** — makes `scripts/` a package so `-m` imports work

### Design rationale for the schema choices

- `description` on exceptions makes the table queryable in plain SQL without having to parse `raw_event` JSON — useful for dashboards or manual investigation.
- `action_taken` + `reasoning` as separate text columns are more readable in audit queries (`SELECT agent_name, action_taken FROM agent_actions WHERE exception_id = ?`) than a JSON blob.
- `customer_notified` as a boolean is a first-class field because it's a compliance concern — it should be trivially queryable without parsing nested JSON.
- `detected_at` / `completed_at` naming is more domain-accurate than generic `created_at` / `resolved_at`.

---

## Turn 5

**Date:** 2026-05-02

**User:**
> How would this schema handle:
> 1. An exception that gets reopened after being marked resolved?
> 2. Multiple agents trying to update the same exception simultaneously?
> 3. A shipment with 50+ exceptions (is there a performance issue)?
> 4. Deleting old data - do we have cascade deletes set up correctly?

**Assistant:**

### 1. Reopened exceptions

The current `WorkflowStatus` enum has no backward path from `RESOLVED`. The right fix is not to mutate the existing row — that loses the original resolution. Instead, add a nullable `parent_exception_id` FK on `ShipmentException`: a reopened case creates a fresh exception row that points back to the original. The original resolution stays intact as an audit record. The tradeoff vs. a status transition log is simplicity — you get history for free via the FK chain without a separate `ExceptionEvent` table.

### 2. Concurrent updates

Within a single async process, SQLAlchemy's per-request sessions prevent conflicts. The gap opens if you add multiple workers (Uvicorn `--workers`, Celery). Nothing currently prevents two workers from both fetching the same exception in `PENDING` and both starting the pipeline. Fix: add `version: Mapped[int]` and `__mapper_args__ = {"version_id_col": version}` on `ShipmentException` — SQLAlchemy raises `StaleDataError` if two sessions try to update the same row version.

### 3. 50+ exceptions per shipment

Indexes are in place (`shipment_id` on `shipment_exceptions`, `exception_id` on `agent_actions`) so individual queries stay fast. The current code never eager-loads `Shipment.exceptions` implicitly, so no N+1 problem today. The latent issue: a "get shipment with all exceptions and their actions" endpoint without pagination would pull 50 exceptions × 5 agent_actions = 250 rows. The `list_exceptions` endpoint has `LIMIT 50`, but there is no per-shipment pagination yet — worth adding before going to prod.

### 4. Cascade deletes

ORM-level cascades are correctly configured for all three chains:
```
Shipment → ShipmentException (delete-orphan)
         → AgentAction       (delete-orphan)
         → Resolution        (delete-orphan)
```
The gap: SQLite does not enforce foreign keys at the database level by default (`PRAGMA foreign_keys` is OFF). A raw `DELETE` from a migration script or DB tool would orphan child rows silently. Fix: add a `@event.listens_for(engine.sync_engine, "connect")` listener in `database.py` that runs `PRAGMA foreign_keys = ON` on every new connection.

### Most actionable item now

The SQLite FK pragma is a silent footgun — it costs one line in `database.py` and has no downside. The others (optimistic locking, per-shipment pagination) matter when you add workers or data volume.

---

## Turn 6

**Date:** 2026-05-02

**User:**
> Create the agent coordinator system. Each agent should:
> 1. Have a specific system prompt that defines its role
> 2. Accept structured input (exception data)
> 3. Call Claude API (Sonnet 4) with proper error handling
> 4. Return structured JSON output
> 5. Log its reasoning and actions to the database
>
> Start with the AgentCoordinator class that orchestrates all 5 agents in sequence.
> Include the Anthropic SDK and proper async handling.

**Assistant:**

### New files

**`app/agents/schemas.py`** — Pydantic contracts for each agent's output and the shared pipeline context:
- `DetectionOutput`, `AnalysisOutput`, `DecisionOutput`, `CommunicationOutput`, `ActionOutput` — typed, validated outputs replacing raw dicts
- `PlannedAction`, `ExecutedAction` — nested models for decision/action lists
- `WorkflowContext` — accumulates all 5 outputs as optional fields; agents read prior outputs via `context.detection`, `context.analysis`, etc.

**`app/core/coordinator.py`** — `AgentCoordinator` class:
- Module-level `_PIPELINE` list maps `(context_key, next_status, agent_instance)` — adding or reordering agents is a one-line change
- `run()` loops the pipeline, setting `workflow_status` before each agent, catching failures, and always committing terminal state
- Two early-exit conditions: `FAILED` (any agent error) and `RESOLVED` (DetectionAgent found no exception)
- Module-level singleton instantiated in `workflow.py` — safe to share across requests since the coordinator holds no mutable state
- Structured log lines at every step: `exception=42  detection_agent  status → detecting`

### Updated files

**`app/agents/base.py`** — three new capabilities:
- `_call_claude()` now retries up to 3 times with exponential backoff (2 s, 4 s) on `RateLimitError`, `APIConnectionError`, and `InternalServerError`; all other `APIError` subtypes raise immediately
- `_parse_json()` strips markdown code fences Claude sometimes wraps responses in, then attempts a self-repair call if the result still fails `json.loads`
- Added `self._log = logging.getLogger(f"agents.{ClassName}")` for per-agent structured logging
- Abstract `run()` signature now uses `WorkflowContext` instead of `dict[str, Any]`

**All 5 agent files** — each agent now:
- Takes `context: WorkflowContext` and returns its specific typed output model
- Reads prior agent outputs as typed attributes (`context.analysis.root_cause`) instead of `context.get("analysis", {}).get("root_cause", "")`
- Calls `self._parse_json(raw)` instead of `json.loads(raw)` directly
- Validates the parsed dict into its output model with `OutputModel.model_validate(...)`

**`app/core/workflow.py`** — reduced to a 3-line shim; all logic now lives in `AgentCoordinator`

### Key design decisions

- **Typed pipeline context** over a plain dict: attribute access gives IDE autocompletion and a `ValidationError` if an upstream agent returns an unexpected shape, catching contract breaks at runtime rather than silently propagating `None`.
- **Coordinator catches agent exceptions, commits, then returns** a `WorkflowResult` with `FAILED` status rather than propagating a 500 — the caller always gets the exception id and the audit trail of completed agent actions.
- **Module-level `_PIPELINE`** means agent order and status transitions are visible in one place, not scattered across `if/else` in agent code.
- **Self-repair JSON** is a practical hedge: Claude occasionally wraps responses in ` ```json ``` ` despite instructions, and a single repair call is cheaper than a failed request and manual retry.

---

## Turn 7

**Date:** 2026-05-02

**User:**
> How does the AgentCoordinator handle:
> 1. One agent failing in the middle of the workflow?
> 2. The Anthropic API being down or rate-limited?
> 3. An agent returning malformed JSON?
> 4. Timeout scenarios (agent takes >60 seconds)?

**Assistant:**

Answers based on reading the current code directly.

### 1. Mid-pipeline agent failure

Handled correctly. The agent sets `workflow_status = FAILED`, writes a FAILED `AgentAction` row, flushes, and re-raises. The coordinator catches at `coordinator.py:97-105`, logs it, and `break`s out of the loop. `await db.commit()` at line 107 always runs regardless, making the FAILED state durable. The final reload picks up whatever `agent_actions` were recorded, and the caller gets a `WorkflowResult` with FAILED status and the partial audit trail.

What's missing: no resume point. To retry, you'd create a new `ShipmentException` — there's no "restart from agent N" path.

### 2. API down or rate-limited

Partially handled. `_call_claude` (base.py:49-71) retries 3 times on `RateLimitError`, `APIConnectionError`, `InternalServerError` with fixed waits of 2 s and 4 s. Three specific gaps in the current code:

- **No jitter** — concurrent requests both wait exactly 2 s and retry simultaneously
- **`Retry-After` header ignored** — Anthropic 429s sometimes include the exact wait time; we discard it
- **The repair call in `_parse_json` line 98 is a raw `self.client.messages.create`** — zero retry logic; a rate limit during repair immediately propagates as FAILED

### 3. Malformed JSON

Two-stage handling in `_parse_json` (base.py:73-103): strip code fences → `json.loads` → if fails, one self-repair Claude call → `json.loads` again. If the second parse also fails, `JSONDecodeError` propagates and the agent's `except` block records FAILED.

After parsing, each agent calls `OutputModel.model_validate(parsed_dict)` — so valid JSON with wrong types (e.g. `confidence: "high"` instead of a float) raises `ValidationError`, also caught and recorded as FAILED.

Gap: the repair call has no retry and no timeout. Error messages on double-failure are bare `JSONDecodeError`, not field-level Pydantic validation messages.

### 4. Timeout — not handled

The one real gap. No `asyncio.wait_for` exists anywhere in the coordinator or agents. `AsyncAnthropic` defaults to a 600 s total timeout. A single hung Claude call ties up a FastAPI worker for up to 10 minutes. With 5 agents, a worst-case stuck pipeline could block a worker for 50 minutes.

Fix is two lines:
```python
# BaseAgent.__init__
self.client = anthropic.AsyncAnthropic(
    api_key=settings.anthropic_api_key,
    timeout=httpx.Timeout(30.0, connect=5.0),
)

# coordinator.py loop body
output = await asyncio.wait_for(agent.run(exception, db, context), timeout=45.0)
```

### Summary

| Scenario | Current state |
|---|---|
| Mid-pipeline failure | ✓ Handled — always commits, always returns a result |
| API rate limit | ⚠ Partial — retried but no jitter, `Retry-After` ignored, repair call unprotected |
| Malformed JSON | ✓ Handled — one repair attempt then FAILED with audit record |
| Timeout | ✗ Not handled — worker can hang up to 600 s |

---

## Turn 8

**Date:** 2026-05-02

**User:**
> Can you add more robust error handling:
> - Retry logic with exponential backoff for API failures
> - Circuit breaker pattern if the API is consistently failing
> - Detailed error logging with context (which agent, what input, what failed)

**Assistant:**

### New file: `app/core/circuit_breaker.py`

`CircuitBreaker` class with three states (CLOSED / OPEN / HALF_OPEN) and a module-level singleton `anthropic_breaker` shared by all agents:

- **CLOSED → OPEN** after 5 consecutive API call failures
- **OPEN → HALF_OPEN** after 60 s recovery timeout has elapsed
- **HALF_OPEN → CLOSED** after 2 consecutive successes (probe calls passed)
- **HALF_OPEN → OPEN** on any failure during probe

`CircuitBreakerOpen` exception is raised immediately when the circuit is OPEN — no HTTP call is made, no retry loop is entered. The coordinator catches it as a distinct case and writes a `failed` `AgentAction` record explaining why the step was skipped.

### Updated: `app/agents/base.py`

Three additions:

**SDK-level timeout** — `AsyncAnthropic` is now constructed with `httpx.Timeout(30.0, connect=5.0)`. This makes the HTTP layer raise `APITimeoutError` (a subclass of `APIConnectionError`, already retryable) rather than hanging indefinitely.

**Improved `_call_claude` retry loop:**
- Each attempt is now wrapped in `anthropic_breaker.call(coro)` so failures feed the circuit breaker automatically
- `RateLimitError` now reads the `Retry-After` response header and waits exactly that long if present; otherwise uses `2^attempt + random(0,1)` jitter
- `APIConnectionError` and `InternalServerError` use the same jitter formula
- `CircuitBreakerOpen` short-circuits the retry loop immediately
- All other `APIError` subtypes (auth, bad request) still raise immediately

**Repair call in `_parse_json` is now routed through `_call_claude`** instead of raw `self.client.messages.create`, so it benefits from retry + circuit breaker protection. The repair also has its own system prompt ("You are a JSON repair tool.") to get a cleaner response.

**`_log_failure` method** — structured multiline ERROR log with: `agent`, `exception_id`, `step`, `error_type`, `detail`, `input_summary` dict, plus `exc_info=True` for the full traceback.

### Updated: all 5 agent `except` blocks

Each agent's `except Exception` block now calls `self._log_failure(...)` before `_record_action`, with an `input_summary` dict specific to that agent's context:

| Agent | input_summary keys |
|---|---|
| Detection | `exception_type`, `event_type`, `location` |
| Analysis | `exception_type`, `description`, `detection_summary` (truncated) |
| Decision | `exception_type`, `severity`, `root_cause` (truncated to 120 chars) |
| Communication | `exception_type`, `resolution_type`, `notify_customer`, `tracking_number` |
| Action | `resolution_type`, `n_actions`, `customer_notified` |

### Updated: `app/core/coordinator.py`

Three new error paths in the pipeline loop:

1. **`asyncio.TimeoutError`** — caught when `asyncio.wait_for(agent.run(...), timeout=45.0)` fires. Coordinator calls `_record_system_failure` which sets FAILED status and writes an `AgentAction` row. The agent's own `except` block never ran, so the coordinator must handle DB state.

2. **`CircuitBreakerOpen`** — caught separately from generic exceptions. Writes a clear `AgentAction` message ("Skipped — Anthropic API circuit breaker is OPEN") so the audit trail explains why downstream agents never ran.

3. **Generic `Exception`** — unchanged; agent already set FAILED and wrote its own record. Coordinator logs at ERROR level and includes `circuit_state` for cross-agent visibility.

`_record_system_failure` is wrapped in its own try/except to prevent a logging-path DB error from hiding the original failure.

All coordinator log lines now include `circuit_state` in the final summary: `Pipeline complete  exception=42  status=failed  circuit=open`.

### Error handling layers summary (innermost → outermost)

```
httpx.Timeout(30s)           ← SDK-level: kills hung HTTP connections
_call_claude retry loop      ← 3 attempts + jitter + Retry-After
CircuitBreaker.call()        ← counts failures; opens after 5 in a row
agent.run() try/except       ← _log_failure + _record_action + FAILED status
asyncio.wait_for(45s)        ← coordinator: kills hung agent coroutines
CircuitBreakerOpen handler   ← coordinator: fast-fail + audit record
db.commit() always runs      ← ensures FAILED state is durable
```

---

## Turn 9

**Date:** 2026-05-02

**User:**
> Create a FastAPI POST endpoint /webhook/tracking-update that:
> 1. Receives tracking updates (simulate carrier webhooks)
> 2. Validates the payload
> 3. Triggers the agent coordinator
> 4. Returns immediate 200 response (async processing)
> 5. Logs everything to database
>
> Include request/response models using Pydantic.
> Add proper error handling and logging.
> Also create sample webhook payloads for testing (5 different exception scenarios).

**Assistant:**

### New files

**`app/api/endpoints/webhook.py`** — three endpoints:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/webhook/tracking-update` | Accept carrier event, return 202, queue background task |
| `GET` | `/api/v1/webhook/events` | List webhook events (filterable by `status` query param) |
| `GET` | `/api/v1/webhook/events/{id}` | Fetch a single webhook event by id |

**`tests/sample_payloads.py`** — five ready-to-send payloads:

| Key | Carrier | Scenario |
|---|---|---|
| `weather_delay` | FedEx | Severe thunderstorm/tornado grounds Memphis hub for 18 h |
| `damaged_package` | UPS | Crush damage detected at Worldport during unloading |
| `failed_delivery` | USPS | Address missing apartment number; notice left, package held |
| `customs_hold` | DHL | CBP documentation review at JFK; 3-7 day hold |
| `lost_package` | FedEx | No scan for 6 days; investigation ticket auto-generated |

Run all five with: `python tests/sample_payloads.py` (server must be running).

### Updated files

**`app/models.py`** — new `WebhookStatus` enum (`received / processing / processed / ignored / failed`) and `WebhookEvent` table:
- `raw_payload` (JSON) stores the full carrier payload verbatim
- `exception_id` (nullable FK) links to `shipment_exceptions` once the background task creates one
- `status` is indexed for fast `WHERE status = 'processing'` monitoring queries
- `IGNORED` status is distinct from `FAILED` — means the tracking number simply isn't in our system

**`app/schemas.py`** — three new Pydantic types:
- `TrackingUpdatePayload` — validated request body with `Field(min_length=...)` guards on carrier, tracking_number, event_type, location, description
- `WebhookAck` — `Literal["accepted"]` status ensures the response shape is unambiguous
- `WebhookEventRead` — ORM-mapped read schema for monitoring endpoints

**`app/core/config.py`** — `webhook_secret: str = ""` setting; if non-empty, the `_verify_secret` dependency validates the `X-Webhook-Secret` header and rejects 401 on mismatch

**`app/main.py`** — registered `webhook.router`

### Async processing design

The endpoint returns **202** before any Claude API call is made. The background task:

1. Opens a **fresh DB session** (not the request session, which closes when the response is sent)
2. Sets `WebhookEvent.status = PROCESSING`
3. Looks up the `Shipment` — sets `IGNORED` + exits if not found
4. Creates a `ShipmentException`, links `webhook.exception_id`
5. Calls `run_exception_workflow(exception, db)` — the coordinator commits internally
6. **Re-fetches** the webhook row (`await db.get(WebhookEvent, id)`) — necessary because the internal commit expires the ORM instance
7. Sets `PROCESSED`, final commit

Error path: `_mark_failed` opens a second fresh session to record task-level crashes separately from pipeline FAILED states. A pipeline `FAILED` (agent error) still sets `WebhookEvent.status = PROCESSED` — the distinction is intentional: the pipeline ran and reached a conclusion; `FAILED` on the webhook row means the background task itself crashed.

---

## Turn 10

**Date:** 2026-05-02

**User:**
> What happens when:
> 1. We receive duplicate webhooks for the same event?
> 2. Webhooks arrive out of order?
> 3. A webhook payload is missing required fields?
> 4. We get 1000 webhooks at once (spike)?

**Assistant:**

Answers based on reading `app/api/endpoints/webhook.py` directly.

### 1. Duplicate webhooks — not handled

Lines 63–72 insert a `WebhookEvent` unconditionally. No unique constraint exists on `(carrier, tracking_number, event_type, event_timestamp)` and no idempotency key is checked. Two identical POST requests produce two `WebhookEvent` rows, two `ShipmentException` rows, two full 5-agent pipelines, and potentially two customer email notifications.

Fix: compute `sha256(carrier + tracking_number + event_type + event_timestamp)`, store as a unique-indexed `idempotency_key` column, check for it before inserting. If found, return 202 with the existing `webhook_event_id` and skip the insert.

### 2. Out-of-order webhooks — not handled

Events are processed in arrival order regardless of `event_timestamp`. `_run_pipeline` creates a new `ShipmentException` without checking whether a more recent event for the same `(shipment_id, event_type)` already exists. Concrete failure: a carrier resends "delay_resolved" before the original "delay" — `DetectionAgent` marks it RESOLVED, then the actual "delay" triggers a full pipeline and the customer gets a resolution email before the problem was acknowledged.

Fix: before creating the `ShipmentException`, query for an existing exception with the same type and a `detected_at` newer than `payload.event_timestamp`; if found, mark the incoming webhook IGNORED.

### 3. Missing required fields — handled correctly

FastAPI's Pydantic layer fires before the handler runs. Missing or empty `carrier`, `tracking_number`, `event_type`, `location`, or `description` returns 422 with field-level error details. No DB write, no background task scheduled.

The gap: rejected payloads leave no trace in `webhook_events`. A custom `RequestValidationError` handler that writes a `WebhookEvent(status=FAILED)` row would make malformed-payload rates queryable.

### 4. 1000 webhooks at once — serious gap

FastAPI dispatches all 1000 requests concurrently via asyncio. Each returns 202 and registers a `BackgroundTasks` coroutine. Since all 1000 responses complete concurrently, up to **1000 `_process_webhook` coroutines can run simultaneously**, each making 5 Claude API calls — up to **5,000 simultaneous API requests**. The circuit breaker opens after 5 consecutive failures, limiting cascade damage, but the initial burst still hits the API. Concurrently, 1000 SQLite writers cause "database is locked" contention — `aiosqlite` retries internally but SQLite is not designed for this concurrency level.

Minimum fix — module-level semaphore in `webhook.py`:
```python
_pipeline_semaphore = asyncio.Semaphore(10)

async def _process_webhook(webhook_event_id: int) -> None:
    async with _pipeline_semaphore:
        ...  # existing body
```
Excess tasks wait in the asyncio queue rather than all running at once. Production fix: move to a task queue (ARQ, Celery) so pipelines run in worker processes that can be scaled and throttled independently.

### Summary

| Scenario | Current behaviour | Severity |
|---|---|---|
| Duplicate webhooks | Double-processed, double customer email | High |
| Out-of-order events | Processed in arrival order; stale events can win | Medium |
| Missing fields | 422 returned correctly; no DB trace of bad requests | Low |
| 1000-webhook spike | Up to 1000 concurrent pipelines; SQLite lock contention | High |

---

## Turn 11

**Date:** 2026-05-03

**User:**
> Create these GET endpoints for monitoring:
> - /exceptions — List all detected exceptions with their resolution status
> - /exceptions/{id} — Get full agent workflow details for a specific exception
> - /agents/performance — Show metrics: avg processing time per agent, success rate, cost tracking
>
> Include proper response models and database queries. Add pagination for the list endpoint.

**Assistant:**

Implemented three monitoring endpoints plus all supporting infrastructure.

### Changes

**`app/agents/analysis.py`, `decision.py`, `communication.py`, `action.py`**
Added `self._start_timing()` as the first line of each agent's `run()` method. This was already in `detection.py`. All five agents now record wall-clock start time so `_record_action()` can store `duration_ms` on every `AgentAction` row.

**`app/core/config.py`**
Added two cost-per-token settings (overridable via `.env`):
```python
cost_per_input_token: float = 0.000003   # $3 / 1M input tokens
cost_per_output_token: float = 0.000015  # $15 / 1M output tokens
```

**`app/schemas.py`**
Added six new Pydantic response models:
- `AgentActionReadFull` — extends `AgentActionRead` with `duration_ms`, `input_tokens`, `output_tokens`
- `ExceptionSummary` — flat row for the paginated list (includes `tracking_number`, `carrier`, `customer_name` from the joined `Shipment`)
- `PaginatedExceptions` — wraps `ExceptionSummary` list with `total`, `page`, `page_size`
- `ExceptionDetail` — full record with `raw_event`, all agent actions, and resolution
- `AgentMetrics` — per-agent stats: `total_runs`, `successful_runs`, `failed_runs`, `success_rate`, `avg_duration_ms`, `p95_duration_ms`, `total_input_tokens`, `total_output_tokens`, `estimated_cost_usd`
- `PerformanceReport` — top-level response with `generated_at`, `total_exceptions_processed`, `exceptions_by_status` dict, `agents` list, `total_estimated_cost_usd`

**`app/api/endpoints/monitoring.py`** *(new file)*

Three endpoints, all read-only:

**`GET /api/v1/monitoring/exceptions`**
- Query params: `page` (default 1), `page_size` (default 20, max 100), optional `status` filter
- Joins `ShipmentException` → `Shipment` via `selectinload`
- Count query runs first so `total` is always accurate
- Returns `PaginatedExceptions`

**`GET /api/v1/monitoring/exceptions/{id}`**
- Eager-loads `shipment`, `agent_actions`, and `resolution` in a single query
- Returns 404 if not found
- Returns `ExceptionDetail` with every `AgentAction` including token counts

**`GET /api/v1/monitoring/agents/performance`**
- Aggregates `AgentAction` rows via `GROUP BY agent_name`:
  - `COUNT(*)` → `total_runs`
  - `COUNT(*) FILTER (WHERE status = 'completed')` → `successful_runs`
  - `AVG(duration_ms)`, `SUM(input_tokens)`, `SUM(output_tokens)`
- p95 latency: fetches sorted `duration_ms` per agent and picks index `floor(n × 0.95)` (SQLite lacks `PERCENTILE_CONT`)
- Cost = `input_tokens × cost_per_input_token + output_tokens × cost_per_output_token`
- Results sorted in pipeline order: detection → analysis → decision → communication → action
- Returns `PerformanceReport`

**`app/main.py`**
Registered monitoring router: `app.include_router(monitoring.router, prefix="/api/v1")`

### Endpoints summary

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/monitoring/exceptions` | Paginated exception list |
| GET | `/api/v1/monitoring/exceptions/{id}` | Full exception detail |
| GET | `/api/v1/monitoring/agents/performance` | Per-agent metrics & cost |

---

## Turn 12

**Date:** 2026-05-03

**User:**
> Create a simple React dashboard (you can use Vite + React) that shows:
> 1. Live event stream - real-time exceptions being processed
> 2. Agent workflow visualization - show the 5 agents and their current status
> 3. Resolution outcomes - success/failure metrics
> 4. Cost tracking - API calls, estimated resolution costs
>
> Use Tailwind CSS for styling. Keep it clean and functional, not fancy.
> Include a mock data generator for demo purposes.

**Assistant:**

Created a standalone Vite + React dashboard in `dashboard/` with Tailwind CSS v4 and a self-contained mock data engine.

### Project structure

```
dashboard/
  src/
    App.jsx                     — layout, state, simulation timers
    index.css                   — @import "tailwindcss" (v4)
    lib/
      mockGenerator.js          — mock data engine
    components/
      LiveEventStream.jsx       — scrollable live feed
      AgentPipeline.jsx         — 5-agent status row
      ResolutionMetrics.jsx     — outcome bars + severity breakdown
      CostTracker.jsx           — token usage + cost bars
  vite.config.js                — @tailwindcss/vite plugin registered
```

### Mock data engine (`lib/mockGenerator.js`)

- `generateException()` — creates a random exception with a tracking number, carrier, type, severity, and per-agent status map (`{ detection: 'idle', ... }`)
- `advancePipeline(exc)` — advances one step: marks the running agent completed (with random token counts), starts the next agent. 8% chance of failure at any step. Returns `null` when the pipeline is finished.
- `totalStats(exceptions)` — aggregates resolved/failed/active counts, bySeverity, byType, per-agent success rate and cost
- Timers in `App.jsx`: new exception every **2.8 s**, pipeline advance every **1.2 s**

### Components

**`AgentPipeline`** — horizontal row of 5 agent cards connected by arrows. Active agents pulse and highlight in their accent color. Shows runs, success%, and per-agent cost.

**`LiveEventStream`** — reverse-chronological scrollable list, capped at 40 visible rows. Each row shows tracking number, carrier, exception type, severity badge, and animated status dot.

**`ResolutionMetrics`** — stacked progress bar (resolved/failed/active), success rate, mini bar charts for severity and exception type, and a resolutions breakdown once data arrives.

**`CostTracker`** — 2×2 stat grid (total cost, avg cost/exception, input/output tokens), per-agent cost bars, and an input/output token ratio bar.

### Running

```bash
cd dashboard
npm run dev   # http://localhost:5173
```

Pause/Resume and Clear controls are in the header.

---

## Turn 13

**Date:** 2026-05-03

**User:**
> Build a component that visualizes the agent workflow:
> - Show all 5 agents as cards/boxes
> - Highlight the currently active agent
> - Display each agent's output/reasoning
> - Show the flow: Detection → Analysis → Decision → Communication → Action
> - Color code by severity (red/yellow/green)
>
> Make it update in real-time as agents process exceptions.
> Use React hooks for state management.

**Assistant:**

Built `WorkflowVisualizer.jsx` — a self-contained component that tracks a selected exception through all 5 pipeline stages in real time, with per-agent output, severity color-coding, and smart auto-follow behavior.

### Changes

**`src/lib/mockGenerator.js`**
Extended the exception object with three new fields:
- `agent_outputs: {}` — per-agent structured output, populated as each agent completes
- `agent_durations: {}` — simulated Claude API call duration (ms), randomized per agent's realistic range (detection 800–1800ms, analysis 1400–3200ms, etc.)
- `agent_costs: {}` — already existed, now also used in the visualizer

Added rich output pools per agent × exception type:
- Detection: `{ confidence, summary }` — 2 variants per exception type
- Analysis: `{ root_cause, estimated_delay_days, recommended_urgency }` — 2 variants per type
- Decision: `{ resolution_type, notify_customer, rationale, action_count }` — 1–2 variants
- Communication: `{ subject, tone, message_preview }` — 1 per type
- Action: `{ executed_count, overall_status, notes }` — 1 per type

`advancePipeline()` now calls `makeAgentOutput(agentKey, exceptionType)` on each completion and stores the result in `agent_outputs[agentKey]`.

**`src/components/WorkflowVisualizer.jsx`** *(new)*

State managed with two hooks:
- `useState(selectedId)` — which exception is being shown
- `useState(isPinned)` — whether the user has manually selected one

`useEffect` auto-follow logic: when `isPinned=false`, only switches exceptions when the currently tracked one reaches `resolved` or `failed` (avoids jarring jumps while an exception is mid-pipeline). When the user clicks a pill, it pins to that exception.

**Exception selector strip** — scrollable row of pills for the 12 most recent exceptions. Each pill shows the last 7 chars of tracking number, a severity initial badge, and an animated dot for active exceptions. Selected + pinned pill turns dark.

**Exception header** — severity-colored left stripe, severity badge (red/orange/yellow/green), tracking number, carrier, exception type, location, status, and a "X ago" timestamp.

**AgentStep cards** (× 5) — vertical stack connected by dashed/solid lines:
- `idle`: gray card, "Waiting for upstream agent…"
- `running`: severity-colored border + ring-glow, bouncing dots, "Calling Claude API…"
- `completed`: agent accent color, output rendered by type-specific renderer, timing/token/cost metadata in header
- `failed`: red card, "Agent failed — pipeline halted at this step."

**Per-agent output renderers:**
- Detection: confidence %, quoted summary
- Analysis: delay days, urgency color-coded (red=immediate, orange=expedited), root cause paragraph
- Decision: resolution type, notify-customer flag, action count, rationale
- Communication: subject line, tone badge, italic message preview (2-line clamp)
- Action: executed count, overall status color-coded, notes

**Severity color system** (applied to running-agent border, header stripe, step-number ring):
- `critical` → red-500
- `high` → orange-400
- `medium` → yellow-400
- `low` → green-400

**`src/App.jsx`**
Reorganized layout:
1. Header (sticky)
2. AgentPipeline summary row (full width)
3. Two-column row: WorkflowVisualizer (2/3) + LiveEventStream (1/3), max-height 620px
4. Two-column row: ResolutionMetrics + CostTracker

---

## Turn 14

**Date:** 2026-05-03

**User:**
> How are you implementing "real-time" updates?
> - WebSockets?
> - Server-Sent Events?
> - Polling?
>
> What are the tradeoffs of each approach?

**Assistant:**

None of the three. The current dashboard is a pure client-side simulation — `setInterval` in `App.jsx` drives all state updates locally with no server connection. The FastAPI backend has only REST endpoints and no push mechanism.

### Current implementation

Two `setInterval` timers in `App.jsx`:
- `advancePipeline` called every 1400ms — steps each active exception through the pipeline
- `spawnException` called every 2800ms — generates new mock exceptions

No `EventSource`, no `WebSocket`, no `fetch` loop. All state lives in React's `useState`.

### Tradeoffs

**Polling** — client calls REST endpoint every N seconds. Zero backend changes needed (works with existing `GET /monitoring/exceptions`). Simple and stateless. Downside: wastes requests when nothing changed; latency is bounded by the interval. Best for low-frequency aggregate metrics (performance report, resolution counts).

**Server-Sent Events (SSE)** — server pushes newline-delimited JSON over a long-lived HTTP response. Browser's `EventSource` API reconnects automatically. One-directional (server → client), which is all a read-only dashboard needs. Proxies cleanly through nginx. FastAPI supports it via `StreamingResponse`. This is the right fit for the exception stream and workflow status transitions.

**WebSockets** — full-duplex, both sides can send at any time. Necessary only when the client needs to push data back mid-stream (chat, collaborative editing, action triggers). Adds connection lifecycle complexity and doesn't proxy as cleanly. Overkill for a monitoring dashboard.

### Recommended split for this system

| Panel | Approach | Rationale |
|---|---|---|
| Live event stream | SSE | Push new exceptions as they arrive |
| Workflow detail | SSE | Push status transitions per exception ID |
| Agent performance | Polling (30s) | Aggregate stats, no sub-second freshness needed |
| Resolution metrics | Polling (10s) | Same — totals, not event-by-event |

A production SSE endpoint would use `StreamingResponse` in FastAPI, polling the DB for new rows since `last_id` every second. The React side would replace `setInterval` with `new EventSource('/api/v1/stream/exceptions')` and push each parsed event into state.

---

## Turn 15 — Full backend–frontend integration

**User:** "Currently the frontend is a pure client-side simulation with mock data, and the backend REST API exists but isn't connected. I need to integrate them for a real production-like demo. Please: 1. Add WebSocket support to FastAPI backend. 2. Connect React frontend to the real backend. 3. Add a trigger endpoint to simulate real scenarios. 4. Seed the database with realistic test data. 5. Add a demo mode button in the frontend."

### What was built

#### Backend

**`app/core/websocket_manager.py`** — `ConnectionManager` singleton that tracks active WebSocket connections and broadcasts JSON payloads to all of them, silently pruning dead connections.

**`app/api/endpoints/ws.py`** — `GET /api/v1/ws` WebSocket endpoint. Accepts the connection via `manager.connect()`, reads incoming frames in a loop (ignored — dashboard is read-only), and cleans up on `WebSocketDisconnect`.

**`app/api/endpoints/simulate.py`** — Two endpoints:
- `GET /api/v1/simulate/scenarios` — returns metadata (label, description, icon) for all 6 exception scenarios.
- `POST /api/v1/simulate/exception` — picks a random shipment, builds a raw tracking event for the requested scenario (or picks randomly), creates a `ShipmentException`, broadcasts `exception.created`, then kicks off `run_exception_workflow()` as a `BackgroundTask` using a fresh `AsyncSessionLocal` session.

**`app/core/coordinator.py`** — Added WebSocket broadcasts at every pipeline milestone:
- `agent.started` — after `workflow_status` is updated and flushed
- `agent.completed` — after a successful agent run, with the full structured output, timing (queried from the just-written `AgentAction` row), and token counts
- `agent.failed` — in timeout, circuit-breaker, and general exception handlers
- `pipeline.resolved` / `pipeline.failed` — after the final commit, with `resolution_type`

**`app/api/endpoints/webhook.py`** — Added `exception.created` broadcast after a new `ShipmentException` row is flushed, so webhook-triggered exceptions also appear live in the dashboard.

**`scripts/init_db.py`** — Rewritten with `--reset` flag. Seeds 10 shipments across FedEx, UPS, USPS, DHL and 5 pre-resolved exceptions with realistic `AgentAction` rows (action_taken, reasoning, duration_ms, input_tokens, output_tokens) and `Resolution` rows, giving the monitoring panels immediate data on first load.

#### Frontend

**`dashboard/vite.config.js`** — Added `ws: true` to the `/api` proxy so WebSocket upgrade requests through port 5173 are forwarded to port 8000.

**`dashboard/src/lib/api.js`** — REST client with:
- `normalizeSummary()` — converts the list endpoint shape to component shape (derives `agent_statuses` from `workflow_status`)
- `normalizeDetail()` — converts the detail endpoint (with `agent_actions[]`) to component shape with real outputs, timing, and costs
- `applyWsEvent()` — pure function that applies a single WS event to the exceptions array (handles all 6 event types)
- `fetchExceptions`, `fetchExceptionDetail`, `fetchScenarios`, `triggerSimulation`

**`dashboard/src/hooks/useExceptionStream.js`** — Manages real-time state:
- Initial load via `GET /monitoring/exceptions?page_size=50`
- WebSocket connection to `ws://{hostname}:8000/api/v1/ws` with 3-second auto-reconnect
- `wsStatus`: `'connecting' | 'connected' | 'disconnected' | 'error'`

**`dashboard/src/App.jsx`** — Replaced mock `setInterval` simulation with `useExceptionStream()`. Added:
- WS status indicator dot in the header (green/yellow/red)
- "⚡ Simulate Exception" button → `POST /simulate/exception` (random scenario)
- Scenario picker `<select>` with all 6 typed scenarios
- `simulating` state disables controls during in-flight request
- `lastScenario` badge and `simError` display

**`dashboard/src/components/WorkflowVisualizer.jsx`** — Extended to handle both mock and real data shapes:
- `isRaw(output)` helper detects flat `{action_taken, reasoning}` records from the DB
- `GenericOutput` component renders raw records as action + reasoning text
- Each per-agent renderer (`DetectionOutput`, `AnalysisOutput`, etc.) checks `isRaw` first and falls back to `GenericOutput`
- `detailCache` state: when a real exception with no agent outputs is selected, `GET /monitoring/exceptions/{id}` is fetched once and the result merged into the display
- Skeleton loading animation shown while the detail fetch is in progress (`isLoadingDetail`)

### Key design decisions

**WebSocket over SSE** — Turn 14 concluded SSE was the right fit for a read-only dashboard, but since the simulate button also needs to *send* a trigger (bidirectional), FastAPI WebSockets were used for the live stream so the same connection can in principle carry both directions. In practice the client only sends keepalive frames; the trigger still goes over REST (`POST /simulate/exception`).

**Background task sessions** — The simulate endpoint returns `202 Accepted` immediately and runs the pipeline in a `BackgroundTask`. Each background run opens its own `AsyncSessionLocal()` session since the request session is closed after the response.

**Two-phase data loading** — The initial REST fetch gives historical exceptions; WebSocket events provide live updates. For historical exceptions selected in the workflow detail panel that have no cached outputs, an on-demand `GET /monitoring/exceptions/{id}` fetch fills in the agent action history without blocking the initial page load.

**Dual-format output rendering** — WS events carry structured output dicts (with fields like `confidence`, `root_cause`, `actions`). The DB stores flat text in `action_taken` / `reasoning`. Both paths are supported transparently via `isRaw()` detection, keeping the rich mock-era renderers intact for live simulation while still displaying historical data from the seed script.

---

## Turn 16 — Docker containerisation

**User:** "I need to containerize the entire application with Docker for easy deployment and to show production-readiness in my job application. Multi-container Docker Compose, dev and prod configs, documentation."

### New files

**`Dockerfile`** (backend) — `python:3.12-slim` base, non-root `app` user, curl for healthcheck, copies `app/` and `scripts/`, mounts `/data` for SQLite persistence. `HEALTHCHECK` calls `GET /health`. Entrypoint is `scripts/docker-entrypoint.sh`.

**`scripts/docker-entrypoint.sh`** — Runs `python -m scripts.init_db` (creates tables if missing), then conditionally seeds via `--if-empty` when `SEED_ON_EMPTY=true`. Starts uvicorn with `--reload --reload-dir /app/app` in development, plain single-worker in production.

**`dashboard/Dockerfile`** (frontend prod) — Two-stage build: Node 20 Alpine builds the React app (`npm ci` + `npm run build`), nginx 1.27 Alpine serves `dist/`. Build context is the repo root so `nginx.conf` is in scope.

**`dashboard/Dockerfile.dev`** (frontend dev) — Node 20 Alpine, `npm install`, starts Vite with `--host 0.0.0.0`. Only `src/` and `public/` are volume-mounted so `node_modules` stays intact inside the container.

**`nginx.conf`** — Two separate `location` blocks: `/api/v1/ws` with WebSocket upgrade headers (`Upgrade`, `Connection`, 86400s timeouts) before the generic `/api/` proxy block; `location /` serves the SPA with `try_files` fallback to `index.html`.

**`docker-compose.yml`** (dev) — Backend mounts `./app` and `./scripts` for live reload; frontend mounts `./dashboard/src` and `./dashboard/public` for Vite HMR. Backend port 8000 exposed to host; frontend port 5173 exposed. Frontend `depends_on` backend `service_healthy`.

**`docker-compose.prod.yml`** (prod) — Backend port not exposed to host (internal only). Frontend build context is repo root. Single `db_data` volume. Both services `restart: unless-stopped`.

**`.dockerignore`** — Excludes `__pycache__`, virtualenvs, `*.db` files, `.env`, `dashboard/`, `tests/`.

**`dashboard/.dockerignore`** — Excludes `node_modules/`, `dist/`, `.env`.

**`DOCKER.md`** — Complete deployment guide: quick start, architecture diagram, env var table, every common command (build/run/logs/stop/exec/db), startup sequence, rebuild matrix, production hardening checklist.

### Modified files

**`app/database.py`** — Added `if "sqlite" not in settings.database_url: return` guard at the top of the pragma listener so the SQLite-specific PRAGMAs are skipped if `DATABASE_URL` is ever switched to PostgreSQL.

**`scripts/init_db.py`** — Added `--if-empty` flag backed by `is_db_empty()` (counts rows in `shipments`). The Docker entrypoint uses `--seed --if-empty` so the container can restart without re-inserting duplicate data. Also added `func, select` imports.

**`dashboard/src/hooks/useExceptionStream.js`** — Changed WS URL from `ws://${hostname}:8000/...` (hardcoded port) to `${scheme}://${window.location.host}/api/v1/ws` so it routes through Vite's proxy in dev (port 5173) and nginx in prod (port 80) without any code change between environments.

**`dashboard/vite.config.js`** — Changed proxy target from hardcoded `http://localhost:8000` to `process.env.BACKEND_URL || 'http://localhost:8000'`. Docker Compose sets `BACKEND_URL=http://backend:8000` (Docker internal hostname); local dev falls back to localhost.

**`README.md`** — Added "Quick Start — Docker (recommended)" section at the top (3-command clone-copy-run), kept the existing local setup section below it.

**`.env.example`** — Added `SEED_ON_EMPTY=true` with explanatory comment.

### Key design decisions

**Dev vs prod compose split** — `docker-compose.yml` mounts source as volumes (fast iteration, no rebuild needed), exposes both ports. `docker-compose.prod.yml` builds optimised images, hides backend behind nginx, exposes only port 80.

**WebSocket through nginx** — The dedicated `location /api/v1/ws` block with `proxy_http_version 1.1` and the `Upgrade`/`Connection` headers must appear *before* the generic `/api/` block, otherwise nginx matches the shorter prefix first and strips the upgrade headers.

**Non-root container user** — The backend runs as a non-root `app` user for defence-in-depth. `/data` is `chown`-ed to `app:app` in the Dockerfile before the `USER` switch.

**`--if-empty` seeding** — Using `--seed` alone on a container restart would re-run inserts and hit unique-constraint errors on tracking numbers. `--if-empty` skips the seed entirely if the table already has rows, making the entrypoint idempotent.

**WS URL uses `window.location.host`** — `window.location.host` includes the port (e.g. `localhost:5173` in Vite dev, `localhost` in nginx prod on port 80). This means the same compiled JS works in all three environments: local dev, Docker dev, Docker prod — with zero environment-specific configuration injected into the bundle.

---

## Turn 17 — Angular migration

**User:** "yes please migrate to angular version 14+ please and add a turn in md about migrating to angular" (context: user knows Angular, not React; wants to own and explain every line of the frontend code in interviews)

### What was built

The entire `dashboard/` frontend was migrated from **React 18 + Vite** to **Angular 16** with standalone components, Tailwind CSS 3, and RxJS. The backend (FastAPI, SQLite, all agents) is unchanged.

#### New Angular project structure

```
dashboard/
├── angular.json              — CLI config: browser builder, port 4200, proxy
├── tsconfig.json             — strict TS, ES2022 module, strictTemplates: false
├── tsconfig.app.json         — app-only tsconfig extending the root
├── tailwind.config.js        — content: ['./src/**/*.{html,ts}']
├── postcss.config.js         — tailwindcss + autoprefixer
├── proxy.conf.js             — dev proxy to backend (JS file: reads BACKEND_URL env var)
├── package.json              — Angular 16.2, RxJS 7.8, TypeScript 5.1
└── src/
    ├── index.html            — <app-root> entry point
    ├── main.ts               — bootstrapApplication() + provideHttpClient()
    ├── styles.css            — @tailwind base/components/utilities + bounce keyframe
    └── app/
        ├── app.component.ts  — root: subscribes to stream service, handles simulate
        ├── app.component.html
        ├── models/
        │   └── exception.model.ts   — Exception, AgentDef, AgentStat, TotalStats interfaces
        ├── services/
        │   ├── api.service.ts            — HttpClient REST + normalizeSummary/applyWsEvent
        │   └── exception-stream.service.ts — WebSocket + BehaviorSubject state + computeStats
        └── components/
            ├── agent-pipeline/
            ├── workflow-visualizer/      — ngOnChanges auto-follow + detail fetch cache
            ├── live-event-stream/
            ├── resolution-metrics/
            └── cost-tracker/
```

#### Key Angular patterns used

**Standalone components (Angular 14+):** each component declares `standalone: true` and lists its own `imports`. No `AppModule` exists. `bootstrapApplication()` in `main.ts` is the only bootstrap call, with `provideHttpClient()` as the single root provider.

**Service-as-store:** `ExceptionStreamService` owns the WebSocket connection and a `BehaviorSubject<Exception[]>`. `AppComponent` subscribes in `ngOnInit()` via `takeUntil(destroy$)` and passes plain arrays to child components via `@Input()`. Child components are stateless and have no knowledge of the WebSocket.

**`takeUntil` cleanup:** `AppComponent` holds a `Subject<void>` (`destroy$`). All subscriptions are piped through `takeUntil(this.destroy$)` and the subject is completed in `ngOnDestroy()`, preventing memory leaks.

**`ngOnChanges` for reactive logic:** `WorkflowVisualizerComponent` implements `OnChanges`. Every time the `exceptions` `@Input()` changes, `ngOnChanges` triggers `autoFollow()` (picks the latest active exception) and `checkDetailFetch()` (lazily loads full agent outputs via `GET /monitoring/exceptions/{id}`). A `Map<id, data | 'loading'>` guards against duplicate fetches.

**`proxy.conf.js` (not JSON):** A JavaScript proxy config is used so `process.env.BACKEND_URL` can be read at `ng serve` startup, matching the same Docker Compose env var injection that Vite used previously.

#### Infrastructure changes

| File | Change |
|---|---|
| `dashboard/Dockerfile.dev` | `ng serve --host 0.0.0.0 --port 4200` instead of Vite |
| `dashboard/Dockerfile` | `COPY --from=builder /app/dist/dashboard` (Angular output path) |
| `docker-compose.yml` | Port `5173→4200`; removed `./dashboard/public:/app/public` volume |
| `.dockerignore` | Replaced blanket `dashboard/` exclusion with `dashboard/node_modules/`, `dashboard/dist/`, `dashboard/.angular/` so prod build context can access source files |
| `ARCHITECTURE.md` | New "Frontend: Angular Migration" section with React→Angular mapping table |

#### Build result

```
✔ Browser application bundle generation complete.
Initial Total: 246.84 kB — 0 errors, 0 warnings
```

---

## Turn 18 — Angular `browserTarget` fix

**User:** "Error: Schema validation failed with the following errors: Data path "" must have required property 'browserTarget'."

Angular 16's `dev-server` builder uses `browserTarget` (not `buildTarget`, which is Angular 17+). Fixed `angular.json` serve configuration:

```json
"configurations": {
  "production":  { "browserTarget": "dashboard:build:production" },
  "development": { "browserTarget": "dashboard:build:development" }
}
```
