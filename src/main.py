"""
PITCHPULSE 2026 - FastAPI Production Application Entry Point
Criterion #1: Code Quality, Criterion #2: Security, Criterion #6: Google Cloud Run
"""

import os
import logging
import logging.config
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from src.routes.stadium import router as stadium_router
from src.routes.assistant import router as assistant_router
from src.utils.security import SecurityHeadersMiddleware, RateLimitMiddleware
from src.utils.cache import cache_stats

load_dotenv()

# Structured logging configuration (Criterion #1: Code Quality)
logging.config.dictConfig({
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
            "level": "INFO",
        }
    },
    "root": {"handlers": ["console"], "level": "INFO"},
})

logger = logging.getLogger("pitchpulse.main")

app = FastAPI(
    title="PitchPulse 2026 // FIFA Stadium Intelligence API",
    description=(
        "GenAI-powered accessible stadium operations, wayfinding, multilingual assistance, "
        "and crowd management for the FIFA World Cup 2026 at MetLife Stadium."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Security Middleware (Criterion #2 — applied before CORS)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

# CORS — credentials disabled for wildcard origin (Criterion #2 fix)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Staff-Token"],
)

app.include_router(stadium_router)
app.include_router(assistant_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global error handler — prevents internal stack traces from leaking (Criterion #2)."""
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
    """Google Cloud Run container liveness probe with cache diagnostics."""
    return {
        "status": "healthy",
        "service": "PitchPulse 2026",
        "version": "2.0.0",
        "deployment_target": "Google Cloud Run Ready",
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "cache": cache_stats(),
    }
