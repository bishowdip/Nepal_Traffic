"""
Nepal Traffic AI — FastAPI entry point.
"""
import logging
import logging.handlers
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import init_db


# ── Logging setup ─────────────────────────────────────────────────────────────

os.makedirs("./logs", exist_ok=True)

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))

def _add_rotating_handler(logger_name: str, filename: str):
    handler = logging.handlers.RotatingFileHandler(
        filename, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s — %(message)s"
    ))
    logging.getLogger(logger_name).addHandler(handler)

_add_rotating_handler("backend.api.vehicles", "./logs/detections.log")
_add_rotating_handler("backend.services.alert",  "./logs/alerts.log")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Load watchlist into alert engine cache
    from backend.database import AsyncSessionLocal
    from backend.models.vehicle import Watchlist
    from sqlalchemy import select
    from backend.services.alert import refresh_watchlist
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Watchlist).where(Watchlist.active == True))
        watchlist = {w.plate_text.lower(): True for w in result.scalars().all()}
        refresh_watchlist(watchlist)

    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Nepal Traffic AI",
    description="AI-powered vehicle recognition & traffic data collection system for Nepal checkpoints.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

from backend.api import vehicles, stream, reports, alerts

app.include_router(vehicles.router, prefix="/api", tags=["vehicles"])
app.include_router(alerts.router,   prefix="/api", tags=["alerts"])
app.include_router(reports.router,  prefix="/api", tags=["reports"])
app.include_router(stream.router,   tags=["websocket"])


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "mock_mode": settings.MOCK_MODE,
        "checkpoint": settings.CHECKPOINT_NAME,
    }


# ── Static frontend (must come AFTER all API routes) ─────────────────────────

_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
