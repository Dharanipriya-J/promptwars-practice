"""
PitchPulse 2026 - Security Middleware, Authentication & Rate Limiting
Enforces zero-trust HTTP security headers, timing-attack-safe authentication, and per-IP rate limiting.
"""

import hmac
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from src.config import settings

# Rate Limiting Windows & Thresholds
RATE_LIMIT_STANDARD = 30
RATE_LIMIT_ASSISTANT = 10
RATE_LIMIT_WINDOW = 60

# In-Memory request timestamp storage per client IP
_CLIENT_REQUESTS: dict[str, list[float]] = defaultdict(list)


def apply_security_headers(response: Response) -> Response:
    """Applies defense-in-depth security headers to any outgoing HTTP response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), microphone=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; "
        "img-src 'self' data: https://images.unsplash.com; "
        "connect-src 'self' http://localhost:8000 https://generativelanguage.googleapis.com;"
    )
    return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces strict HTTP headers against clickjacking, MIME-sniffing, and protocol downgrade."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        return apply_security_headers(response)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Token-bucket style rate limiting per client IP.
    Protects Google Gemini API quota and prevents denial of service.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in ["/api/health", "/docs", "/openapi.json", "/"]:
            return await call_next(request)

        # Extract client IP from proxy header if available
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        elif request.client and request.client.host:
            client_ip = request.client.host
        else:
            client_ip = "127.0.0.1"

        now = time.monotonic()
        timestamps = _CLIENT_REQUESTS[client_ip]
        # Discard records older than rate window
        _CLIENT_REQUESTS[client_ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]

        # Apply stricter quota for Gemini-powered assistant queries
        is_assistant = request.url.path.startswith("/api/assistant")
        max_allowed = RATE_LIMIT_ASSISTANT if is_assistant else RATE_LIMIT_STANDARD

        if len(_CLIENT_REQUESTS[client_ip]) >= max_allowed:
            resp = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": (
                        f"Limit of {max_allowed} requests per minute reached for this endpoint. "
                        "Please pause before submitting further requests."
                    ),
                    "retry_after_seconds": RATE_LIMIT_WINDOW,
                },
            )
            return apply_security_headers(resp)

        _CLIENT_REQUESTS[client_ip].append(now)
        return await call_next(request)


def verify_staff_token(request: Request) -> bool:
    """
    Validates X-Staff-Token header against configured STAFF_SECRET_TOKEN.
    Uses constant-time comparison to prevent side-channel timing attacks.
    """
    token = request.headers.get("X-Staff-Token")
    configured_token = settings.staff_secret_token or ""

    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Staff authentication configuration is missing on server.",
        )

    if not token or not hmac.compare_digest(token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid X-Staff-Token header is required for operations dispatch.",
        )
    return True
