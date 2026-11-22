from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api import (
    connectors,
    cron,
    energy,
    investigations,
    opportunities,
    providers,
    quality,
    system,
    workflow,
)
from app.config import get_settings
from app.logging_config import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.auto_setup:
        from app.setup import ensure_ready

        ensure_ready()
    if settings.scheduler_enabled:
        from app.scheduler import start_scheduler, stop_scheduler

        start_scheduler()
        yield
        stop_scheduler()
    else:
        yield


app = FastAPI(
    title="GridLink API",
    version="0.1.0",
    description="Connect, standardise, validate and monitor energy data from multiple European markets.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_origin_regex=get_settings().cors_origin_regex,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(IntegrityError)
async def integrity_error(_: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "Constraint violation", "error": str(exc.orig)[:300]})


for r in (system, workflow, providers, connectors, energy, quality, opportunities, investigations, cron):
    app.include_router(r.router)
