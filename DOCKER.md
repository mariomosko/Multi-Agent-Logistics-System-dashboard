# Docker Deployment Guide

---

## Prerequisites

- Docker 24+ and Docker Compose v2 (`docker compose` not `docker-compose`)
- An Anthropic API key

---

## Quick start (development)

```bash
git clone <repo-url>
cd "Multi-Agent Logistics System"

cp .env.example .env
# Set ANTHROPIC_API_KEY in .env

docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| API + Swagger | http://localhost:8000/docs |
| Health check | http://localhost:8000/health |

The database is seeded automatically on first start. Source code is mounted as a volume — Python and React changes reload without rebuilding.

To stop:

```bash
docker compose down
```

---

## Production deployment

```bash
cp .env.example .env
# Set ANTHROPIC_API_KEY=... and APP_ENV=production in .env

docker compose -f docker-compose.prod.yml up --build -d
```

| Service | URL |
|---------|-----|
| Dashboard + API | http://localhost (port 80) |

In production, nginx serves the pre-built React SPA and proxies all `/api/` traffic (including WebSocket upgrades) to the backend container. The backend is not exposed to the host.

---

## Architecture

```
Host                Docker network (logistics-prod_default)
─────               ────────────────────────────────────────
                    ┌─────────────────────────────────┐
:80  ◄────────────► │  frontend  (nginx:1.27-alpine)  │
                    │  /           → SPA              │
                    │  /api/       → proxy backend    │
                    │  /api/v1/ws  → WS upgrade       │
                    └──────────────┬──────────────────┘
                                   │  :8000 (internal)
                    ┌──────────────▼──────────────────┐
                    │  backend  (python:3.12-slim)     │
                    │  FastAPI + 5-agent pipeline      │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │  db_data volume                  │
                    │  /data/logistics.db (SQLite)     │
                    └─────────────────────────────────┘
```

---

## Environment variables

All variables are read from `.env`. The only one that is required is `ANTHROPIC_API_KEY`.

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Your Anthropic API key |
| `DATABASE_URL` | set by compose | SQLAlchemy async DB URL |
| `APP_ENV` | set by compose | `development` or `production` |
| `LOG_LEVEL` | set by compose | Python log level |
| `SEED_ON_EMPTY` | `true` | Seed sample data on first startup |

Variables set directly in the compose file (`DATABASE_URL`, `APP_ENV`, `LOG_LEVEL`, `SEED_ON_EMPTY`) override `.env` values — so `.env` only needs `ANTHROPIC_API_KEY` in practice.

---

## Common commands

### Build

```bash
# Development (fast iteration)
docker compose build

# Production (optimised images)
docker compose -f docker-compose.prod.yml build

# Rebuild a single service
docker compose build backend
```

### Run

```bash
# Start in foreground (see logs)
docker compose up

# Start in background
docker compose up -d

# Production
docker compose -f docker-compose.prod.yml up -d
```

### Logs

```bash
# All services
docker compose logs -f

# Single service
docker compose logs -f backend
docker compose logs -f frontend
```

### Stop

```bash
# Stop and remove containers (keep volumes)
docker compose down

# Stop, remove containers AND volumes (deletes database)
docker compose down -v
```

### Database

```bash
# Re-seed (inside running container)
docker compose exec backend python -m scripts.init_db --seed --if-empty

# Full reset (drops and recreates all tables)
docker compose exec backend python -m scripts.init_db --seed --reset

# Open a SQLite shell
docker compose exec backend sqlite3 /data/logistics.db
```

### Shell access

```bash
docker compose exec backend bash
docker compose exec frontend sh
```

---

## How the database persists

A named Docker volume (`logistics_db_dev` / `logistics_db_prod`) is mounted at `/data` inside the backend container. The SQLite file lives at `/data/logistics.db`.

The volume survives `docker compose down` and `docker compose up` cycles — data is only lost if you explicitly run `docker compose down -v` or delete the volume with `docker volume rm`.

---

## Startup sequence

```
backend healthcheck passes (GET /health → 200)
        │
        └─► frontend starts (depends_on: backend healthy)
```

The entrypoint (`scripts/docker-entrypoint.sh`) runs before the server starts:

1. `python -m scripts.init_db` — creates tables if they don't exist
2. If `SEED_ON_EMPTY=true` — seeds sample data only when the shipments table is empty
3. Starts uvicorn (`--reload` in dev, single worker in prod)

---

## Rebuilding after code changes

| Change | Action needed |
|--------|--------------|
| Python source (`app/`) | Auto-reloaded by uvicorn in dev; `docker compose restart backend` in prod |
| React source (`dashboard/src/`) | Auto-reloaded by Vite HMR in dev; `docker compose -f docker-compose.prod.yml build frontend` in prod |
| `requirements.txt` | `docker compose build backend` |
| `package.json` | `docker compose build frontend` |

---

## Production hardening checklist

The setup here is intentionally demo-focused. For a real production deployment, also consider:

- Replace `allow_origins=["*"]` in `app/main.py` with your actual domain
- Add a TLS termination layer in front of nginx (e.g. Certbot / Caddy / a load balancer)
- Switch `DATABASE_URL` to PostgreSQL (`postgresql+asyncpg://...`) for multi-writer concurrency — a one-line `.env` change; no application code changes required
- Set `uvicorn --workers` > 1 and move WebSocket broadcasting to Redis pub/sub (see ARCHITECTURE.md)
- Store `ANTHROPIC_API_KEY` in Docker secrets or a secrets manager instead of `.env`
