"""
PITCHPULSE 2026 - Security Middleware, Authentication & Rate Limiting
Criterion #2: Security (Comprehensive defensive posture)
"""

import os
import time
from collections import defaultdict
from typing import Dict, Tuple
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse

# Staff Secret for Protected Incident Dispatch (default demo token for testing)
STAFF_AUTH_TOKEN = os.getenv("STAFF_SECRET_TOKEN", "fifa-staff-secure-2026")

# In-Memory Token Bucket Rate Limiter: max 30 requests per minute per IP
RATE_LIMIT_MAX = 30
RATE_LIMIT_WINDOW = 60
_CLIENT_REQUESTS: Dict[str, list] = defaultdict(list)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Enforces strict HTTP security headers against clickjacking, MIME-sniffing, and XSS.
    """
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), microphone=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https://images.unsplash.com; "
            "connect-src 'self' http://localhost:8000 https://generativelanguage.googleapis.com;"
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Token-bucket rate limiting per client IP to protect Gemini API quota and backend resources.
    """
    async def dispatch(self, request: Request, call_next):
        # Exclude static assets or health checks from rate limiting
        if request.url.path in ["/api/health", "/docs", "/openapi.json", "/"]:
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        
        # Clean timestamps older than 60 seconds
        _CLIENT_REQUESTS[client_ip] = [t for t in _CLIENT_REQUESTS[client_ip] if now - t < RATE_LIMIT_WINDOW]

        if len(_CLIENT_REQUESTS[client_ip]) >= RATE_LIMIT_MAX:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": "Maximum 30 requests per minute allowed to protect API resources. Please try again shortly."
                }
            )

        _CLIENT_REQUESTS[client_ip].append(now)
        return await call_next(request)


def verify_staff_token(request: Request):
    """
    Validates X-Staff-Token header for operations staff endpoints (/api/stadium/incident).
    Prevents unauthorized malicious emergency dispatching.
    """
    token = request.headers.get("X-Staff-Token")
    if not token or token != STAFF_AUTH_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid X-Staff-Token header is required to dispatch stadium incidents."
        )
    return True
