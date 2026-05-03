# Multi-Agent Logistics System

A production-style demo that routes shipment exceptions through a sequential 5-agent AI pipeline powered by Claude. Each exception — a weather delay, lost package, damaged item, etc. — is automatically detected, analyzed, decided on, communicated to the customer, and actioned, all while a live Angular dashboard shows every step in real time.

---

## Quick Start — Docker (recommended)

Requires Docker 24+ and an Anthropic API key.

```bash
git clone <repo-url>
cd "Multi-Agent Logistics System"

cp .env.example .env
# Set ANTHROPIC_API_KEY=sk-ant-... in .env

docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:4200 |
| API / Swagger | http://localhost:8000/docs |

The database is seeded automatically on first start. See [DOCKER.md](DOCKER.md) for production deployment, logs, database management, and more.

---

## Quick Start — Local (no Docker)

### Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11 or 3.12 |
| Node.js | 18+ |
| Anthropic API key | [console.anthropic.com](https://console.anthropic.com) |

### 1 — Clone and set up the backend

```bash
git clone <repo-url>
cd "Multi-Agent Logistics System"

python3 -m venv MULT_AGENT_LOG.venv
source MULT_AGENT_LOG.venv/bin/activate   # Windows: MULT_AGENT_LOG.venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Open .env and set:  ANTHROPIC_API_KEY=sk-ant-...
```

### 2 — Seed the database

```bash
python scripts/init_db.py --seed --reset
```

This creates `logistics.db` with 10 shipments across FedEx, UPS, USPS, and DHL, plus 5 fully resolved exceptions with complete agent histories so every dashboard panel has data immediately.

> **Flags:** `--seed` inserts the sample data. `--reset` clears existing rows first (safe to re-run). Running without `--seed` only creates the empty tables.

### 3 — Start the backend

```bash
uvicorn app.main:app --reload
# API running at  http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### 4 — Start the frontend

```bash
cd dashboard
npm install
npm run dev
# Dashboard at http://localhost:4200
```

### 5 — Trigger a live exception

Open the dashboard and click **⚡ Simulate Exception**, or pick a specific scenario from the dropdown. Watch the 5-agent pipeline execute step by step in real time.

---

## Architecture

```
                        ┌─────────────────────────────────────────────────┐
                        │                 Angular Dashboard                │
                        │  AgentPipeline  WorkflowVisualizer  LiveStream  │
                        │  ResolutionMetrics  CostTracker                 │
                        └──────────────┬──────────────────────────────────┘
                                       │ HTTP (REST)  /  WebSocket
                        ┌──────────────▼──────────────────────────────────┐
                        │              FastAPI  (port 8000)               │
                        │                                                 │
                        │  POST /webhook/tracking-update                  │
                        │  POST /simulate/exception    ← demo trigger     │
                        │  GET  /monitoring/exceptions                    │
                        │  GET  /monitoring/exceptions/{id}               │
                        │  GET  /monitoring/agents/performance            │
                        │  WS   /ws                    ← live events      │
                        └──────────────┬──────────────────────────────────┘
                                       │  BackgroundTask
                        ┌──────────────▼──────────────────────────────────┐
                        │           AgentCoordinator                      │
                        │                                                 │
                        │  DetectionAgent  → AnalysisAgent               │
                        │       → DecisionAgent → CommunicationAgent     │
                        │              → ActionAgent                      │
                        │                                                 │
                        │  ● 45 s per-agent timeout                       │
                        │  ● exponential-backoff retry (3 attempts)       │
                        │  ● circuit breaker (5 failures → open 60 s)     │
                        └──────────────┬──────────────────────────────────┘
                                       │  SQLAlchemy async
                        ┌──────────────▼──────────────────────────────────┐
                        │           SQLite  (logistics.db)                │
                        │  shipments · shipment_exceptions                │
                        │  agent_actions · resolutions · webhook_events   │
                        └─────────────────────────────────────────────────┘
```

### The 5-agent pipeline

| # | Agent | Input | Output |
|---|-------|-------|--------|
| 1 | **Detection** | raw carrier event JSON | `is_exception`, `exception_type`, initial severity |
| 2 | **Analysis** | exception + shipment history | `root_cause`, severity rating, impact assessment |
| 3 | **Decision** | analysis output | resolution path (`reship`, `refund`, `contact_carrier`, …), priority |
| 4 | **Communication** | decision + customer details | subject line + full customer email body |
| 5 | **Action** | decision + communication | executed action list, final resolution record |

### Real-time event flow

```
POST /simulate/exception
        │
        ├─► creates ShipmentException (DB)
        ├─► broadcasts  exception.created  (WS)
        └─► BackgroundTask: AgentCoordinator.run()
                │
                ├─► agent.started       (WS)  ←┐
                ├─► claude API call             │  × 5
                ├─► agent.completed     (WS)  ←┘
                │
                └─► pipeline.resolved / pipeline.failed  (WS)
```

Every WebSocket event is applied via `applyWsEvent()` in `ExceptionStreamService`, updating the `BehaviorSubject<Exception[]>` state which Angular's `async` pipe propagates to all subscribed components.

---

## Project Structure

```
.
├── app/
│   ├── agents/
│   │   ├── base.py            # BaseAgent: retry logic, timing, token tracking
│   │   ├── schemas.py         # WorkflowContext + per-agent output types
│   │   ├── detection.py
│   │   ├── analysis.py
│   │   ├── decision.py
│   │   ├── communication.py
│   │   └── action.py
│   ├── api/endpoints/
│   │   ├── webhook.py         # POST /webhook/tracking-update
│   │   ├── simulate.py        # POST /simulate/exception  GET /simulate/scenarios
│   │   ├── monitoring.py      # GET  /monitoring/exceptions  /agents/performance
│   │   ├── shipments.py       # CRUD for shipment records
│   │   ├── workflow.py        # POST /workflow/trigger (direct pipeline trigger)
│   │   └── ws.py              # WS  /ws
│   ├── core/
│   │   ├── config.py          # Pydantic settings (reads .env)
│   │   ├── circuit_breaker.py # 3-state circuit breaker for Anthropic API
│   │   ├── coordinator.py     # AgentCoordinator: pipeline orchestration + WS events
│   │   ├── websocket_manager.py  # ConnectionManager singleton
│   │   └── workflow.py        # run_exception_workflow() entry point
│   ├── database.py            # SQLAlchemy async engine + session factory
│   ├── models.py              # ORM models
│   ├── schemas.py             # Pydantic request/response schemas
│   └── main.py                # FastAPI app, lifespan, router registration
├── dashboard/                 # Angular 16 + RxJS + Tailwind CSS
│   └── src/app/
│       ├── app.component.ts           # Root: subscribes to ExceptionStreamService
│       ├── components/
│       │   ├── agent-pipeline/        # Per-agent status summary row
│       │   ├── workflow-visualizer/   # Selected exception step-by-step detail
│       │   ├── live-event-stream/     # Scrolling event log
│       │   ├── resolution-metrics/    # Resolution type breakdown
│       │   └── cost-tracker/          # Token cost summary
│       ├── services/
│       │   ├── exception-stream.service.ts  # WS + BehaviorSubject state
│       │   └── api.service.ts               # REST client + WS event reducer
│       └── models/
│           └── exception.model.ts     # TypeScript interfaces + AGENTS constant
├── scripts/
│   └── init_db.py             # Database seeder (--reset flag)
├── tests/
│   ├── test_workflow.py
│   └── sample_payloads.py
├── requirements.txt
└── .env.example
```

---

## API Reference

### Simulation & Demo

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/simulate/scenarios` | List the 6 built-in exception scenarios |
| `POST` | `/api/v1/simulate/exception` | Trigger a scenario against a real DB shipment |

**POST /simulate/exception**

```bash
# Random scenario
curl -X POST http://localhost:8000/api/v1/simulate/exception \
  -H "Content-Type: application/json" \
  -d '{}'

# Specific scenario
curl -X POST http://localhost:8000/api/v1/simulate/exception \
  -H "Content-Type: application/json" \
  -d '{"scenario": "damaged"}'
```

Scenarios: `delay` · `lost` · `damaged` · `address_issue` · `customs_hold` · `failed_delivery`

Returns `202 Accepted` immediately. Pipeline progress arrives over WebSocket.

---

### Webhook (carrier integration)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/webhook/tracking-update` | Receive a carrier tracking event |

```bash
curl -X POST http://localhost:8000/api/v1/webhook/tracking-update \
  -H "Content-Type: application/json" \
  -d '{
    "tracking_number": "FX100000001",
    "event_type": "delay",
    "event_timestamp": "2026-05-03T10:00:00Z",
    "location": "Memphis, TN",
    "description": "Package delayed — severe weather at Memphis hub",
    "carrier_code": "DELAY_WEATHER"
  }'
```

If the tracking number is found in the database, the full pipeline runs automatically in the background.

---

### Monitoring

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/monitoring/exceptions` | Paginated exception list |
| `GET` | `/api/v1/monitoring/exceptions/{id}` | Full detail including agent outputs |
| `GET` | `/api/v1/monitoring/agents/performance` | Aggregate per-agent metrics |

```bash
# List with pagination and status filter
curl "http://localhost:8000/api/v1/monitoring/exceptions?page=1&page_size=20&status=resolved"

# Full detail for one exception
curl http://localhost:8000/api/v1/monitoring/exceptions/1

# Agent performance report
curl http://localhost:8000/api/v1/monitoring/agents/performance
```

---

### Shipments

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/shipments/` | Register a new shipment |
| `GET` | `/api/v1/shipments/` | List shipments |
| `GET` | `/api/v1/shipments/{id}` | Get shipment by ID |

```bash
curl -X POST http://localhost:8000/api/v1/shipments/ \
  -H "Content-Type: application/json" \
  -d '{
    "tracking_number": "MY123456789",
    "carrier": "FedEx",
    "origin": "New York, NY",
    "destination": "Los Angeles, CA",
    "customer_name": "Jane Doe",
    "customer_email": "jane@example.com"
  }'
```

---

### WebSocket

Connect to `ws://localhost:8000/api/v1/ws` to receive live pipeline events.

**Event types:**

```jsonc
// New exception created
{ "event": "exception.created", "exception_id": 42, "tracking_number": "FX100000001",
  "carrier": "FedEx", "exception_type": "delay", "severity": "high", ... }

// Agent starting
{ "event": "agent.started", "exception_id": 42, "agent_name": "detection_agent",
  "workflow_status": "detecting" }

// Agent finished
{ "event": "agent.completed", "exception_id": 42, "agent_name": "analysis_agent",
  "output": { "root_cause": "...", "severity": "high", ... },
  "duration_ms": 1842, "input_tokens": 512, "output_tokens": 380 }

// Agent failed
{ "event": "agent.failed", "exception_id": 42, "agent_name": "decision_agent",
  "reason": "timeout" }

// Pipeline finished
{ "event": "pipeline.resolved", "exception_id": 42, "resolution_type": "reship" }
{ "event": "pipeline.failed",   "exception_id": 42 }
```

---

## Example Workflow

Below is a complete end-to-end trace for a damaged package scenario.

### 1. Trigger the exception

```bash
curl -X POST http://localhost:8000/api/v1/simulate/exception \
  -H "Content-Type: application/json" \
  -d '{"scenario": "damaged"}'
# → 202 {"exception_id": 7, "message": "Pipeline started"}
```

### 2. WebSocket event stream (abbreviated)

```
exception.created   id=7  type=damaged  severity=null
agent.started       id=7  agent=detection_agent   status=detecting
agent.completed     id=7  agent=detection_agent   severity=high    duration=1.2s
agent.started       id=7  agent=analysis_agent    status=analyzing
agent.completed     id=7  agent=analysis_agent    root_cause="Forklift impact at sorting facility"
agent.started       id=7  agent=decision_agent    status=deciding
agent.completed     id=7  agent=decision_agent    resolution=reship   priority=urgent
agent.started       id=7  agent=communication_agent  status=communicating
agent.completed     id=7  agent=communication_agent  subject="Important update about your shipment"
agent.started       id=7  agent=action_agent      status=acting
agent.completed     id=7  agent=action_agent      actions=["reship_initiated","customer_notified"]
pipeline.resolved   id=7  resolution_type=reship
```

### 3. Fetch the final record

```bash
curl http://localhost:8000/api/v1/monitoring/exceptions/7
```

```json
{
  "id": 7,
  "tracking_number": "UPS200000002",
  "exception_type": "damaged",
  "severity": "high",
  "workflow_status": "resolved",
  "resolution": {
    "resolution_type": "reship",
    "root_cause": "Package sustained forklift impact at Memphis sorting facility",
    "customer_message": "We sincerely apologize — a replacement shipment has been dispatched.",
    "actions_taken": ["reship_initiated", "carrier_claim_filed", "customer_notified"]
  },
  "agent_actions": [
    { "agent_name": "detection_agent",     "status": "completed", "duration_ms": 1204, ... },
    { "agent_name": "analysis_agent",      "status": "completed", "duration_ms": 1843, ... },
    { "agent_name": "decision_agent",      "status": "completed", "duration_ms": 1531, ... },
    { "agent_name": "communication_agent", "status": "completed", "duration_ms": 2107, ... },
    { "agent_name": "action_agent",        "status": "completed", "duration_ms":  988, ... }
  ]
}
```

---

## Configuration

All settings are read from `.env` via Pydantic Settings.

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `DATABASE_URL` | `sqlite+aiosqlite:///./logistics.db` | SQLAlchemy async DB URL |
| `APP_ENV` | `development` | `development` or `production` |
| `LOG_LEVEL` | `INFO` | Python log level |

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | FastAPI 0.115 |
| Database ORM | SQLAlchemy 2 (async) + aiosqlite |
| AI agents | Anthropic SDK — claude-sonnet-4-6 |
| Schema validation | Pydantic v2 |
| Real-time transport | FastAPI WebSockets |
| Frontend framework | Angular 16 + RxJS |
| UI styling | Tailwind CSS v3 |
| Python runtime | 3.11 / 3.12 |
