#!/bin/bash
set -e

echo "[entrypoint] Initialising database schema…"
python -m scripts.init_db

if [ "${SEED_ON_EMPTY:-true}" = "true" ]; then
    echo "[entrypoint] Seeding sample data (skipped if DB already has data)…"
    python -m scripts.init_db --seed --if-empty
fi

echo "[entrypoint] Starting FastAPI server…"

if [ "${APP_ENV}" = "development" ]; then
    exec uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --reload \
        --reload-dir /app/app
else
    exec uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers 1 \
        --access-log
fi
