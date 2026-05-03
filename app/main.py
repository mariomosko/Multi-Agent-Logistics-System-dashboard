import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import monitoring, shipments, simulate, webhook, workflow, ws
from app.core.config import settings
from app.database import init_db

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Initializing database…")
    await init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Multi-Agent Logistics System",
    description="Handles shipment exceptions using a 5-agent AI pipeline.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(shipments.router,  prefix="/api/v1")
app.include_router(workflow.router,   prefix="/api/v1")
app.include_router(webhook.router,    prefix="/api/v1")
app.include_router(monitoring.router, prefix="/api/v1")
app.include_router(simulate.router,   prefix="/api/v1")
app.include_router(ws.router,         prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
