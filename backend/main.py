"""
MatSetu (मतसेतु) — India's AI-powered Digital Election Management Platform
FastAPI application factory.
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi

from backend.config import settings
from backend.database import init_db
from backend.services.qdrant import ensure_collections
from backend.routers import (
    auth_router, voter_router, vote_router, worker_router,
    admin_router, uncontested_router, sse_router
)

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("matsetu")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("MatSetu starting up...")
    await init_db()
    try:
        ensure_collections()
        logger.info("Qdrant collections ensured")
    except Exception as e:
        logger.warning(f"Qdrant init skipped: {e}")
    logger.info("MatSetu ready ✓")
    yield
    logger.info("MatSetu shutting down")


app = FastAPI(
    title="MatSetu — Digital Election Management Platform",
    description=(
        "India's AI-powered EVM replacement. "
        "950M voters | 1M+ booths | Biometric + ZK + Blockchain-hash secured."
    ),
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# ── Middleware ──────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://matsetu.eci.gov.in"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not settings.DEBUG:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["matsetu.eci.gov.in", "*.matsetu.eci.gov.in"]
    )


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{elapsed:.1f}"
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';"
    )
    return response


# ── Exception Handlers ──────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


# ── Routers ─────────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(voter_router)
app.include_router(vote_router)
app.include_router(worker_router)
app.include_router(admin_router)
app.include_router(uncontested_router)
app.include_router(sse_router)


# ── Health / Info ────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health():
    return {
        "status": "ok",
        "service": "MatSetu",
        "version": settings.APP_VERSION
    }


@app.get("/", tags=["system"])
async def root():
    return {
        "message": "MatSetu — Digital Election Management Platform",
        "version": settings.APP_VERSION,
        "docs": "/api/docs"
    }
