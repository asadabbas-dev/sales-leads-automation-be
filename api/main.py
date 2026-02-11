"""
Lead Ops Automation - FastAPI Service

Production-grade lead enrichment with idempotency, retry safety, and full audit trail.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.db.session import init_db
from api.routes import enrich, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    await init_db()
    yield
    # Cleanup if needed


app = FastAPI(
    title="Lead Ops Automation API",
    description="Automatic lead qualification, routing, and logging with retry safety",
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


@app.get("/health")
async def health():
    """Health check for load balancers and orchestration."""
    return {"status": "ok"}
