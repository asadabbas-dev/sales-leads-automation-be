"""
Lead Ops Automation — FastAPI Service

Production-grade lead enrichment with idempotency, retry safety, and full audit trail.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.db.session import init_db
from api.routes import enrich, leads, metrics, opportunities, runs, settings
from api.schemas.common import error_message, success_response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB tables on startup (idempotent via CREATE TABLE IF NOT EXISTS)."""
    await init_db()
    yield


app = FastAPI(
    title="Lead Ops Automation API",
    description="Automatic lead qualification, routing, and logging with retry safety.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(enrich.router, prefix="/enrich-lead")
app.include_router(runs.router)
app.include_router(metrics.router)
app.include_router(leads.router)
app.include_router(opportunities.router)
app.include_router(settings.router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    """Return all errors in common format: { success: false, message }."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": error_message(exc.detail)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    """Catch-all so every error returns { success: false, message }."""
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": str(exc) or "Internal server error."},
    )


@app.get("/health", tags=["health"])
async def health():
    """Health check for load balancers and container orchestration."""
    return success_response(data={"status": "ok"}, message=None)