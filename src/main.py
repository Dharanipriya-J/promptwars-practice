"""
PitchPulse 2026 - Production FastAPI Application Entry Point
Orchestrates AI services, stadium telemetry, accessible wayfinding, and security middleware.
"""

import logging
import logging.config
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.config import settings
from src.routes.assistant import router as assistant_router
from src.routes.stadium import router as stadium_router
from src.utils.cache import cache_stats
from src.utils.security import (
    RateLimitMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)

# Structured logging configuration
logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "[%(asctime)s] %(levelname)s %(name)s — %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": settings.log_level,
            }
        },
        "root": {"handlers": ["console"], "level": settings.log_level},
    }
)

logger = logging.getLogger("pitchpulse.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup checks and graceful shutdown lifecycle."""
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY is not set. Multilingual assistant running in offline resilience mode.")
    settings.validate_on_startup()
    yield


app = FastAPI(
    title="PitchPulse 2026 // FIFA Stadium Intelligence API",
    description=(
        "GenAI-powered accessible stadium operations, wayfinding, multilingual assistance, "
        "and crowd management for the FIFA World Cup 2026 at MetLife Stadium."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Compression & Security Middleware Stack
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

# Cross-Origin Resource Sharing with strict origin configuration
allowed_origin = settings.allowed_origin or "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Staff-Token", "X-Forwarded-For"],
)

# API Routers
app.include_router(stadium_router)
app.include_router(assistant_router)

# Mount static directory for JS, CSS, and SVG diagrams
STATIC_DIR = pathlib.Path(__file__).parent.parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

DOCS_DIR = pathlib.Path(__file__).parent.parent / "docs"
if DOCS_DIR.exists():
    app.mount("/docs/screenshots", StaticFiles(directory=str(DOCS_DIR / "screenshots")), name="screenshots")


@app.get("/", include_in_schema=False)
async def serve_index():
    """Serves the accessible PitchPulse 2026 frontend single-page application."""
    index_file = pathlib.Path(__file__).parent.parent / "index.html"
    return FileResponse(index_file)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler preventing stack traces and internal details from leaking."""
    logger.error("Unhandled exception on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Stadium Service Error",
            "message": "A temporary issue occurred. Venue operations backup systems are active.",
        },
    )


@app.get("/api/health", tags=["System"])
def health_check():
    """Liveness probe returning operational state, version, and cache diagnostics."""
    return {
        "status": "healthy",
        "service": "PitchPulse 2026",
        "version": "2.0.0",
        "deployment_target": "Google Cloud Run Ready",
        "gemini_configured": bool(settings.gemini_api_key),
        "cache": cache_stats(),
    }
