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
MAX_CONTENT_LENGTH = 64 * 1024  # 64 KB limit for JSON payloads

# In-Memory request timestamp storage per client IP
_CLIENT_REQUESTS: dict[str, list[float]] = defaultdict(list)


def _prune_expired_client_ips(now: float) -> None:
    """Evicts idle client IP buckets to guarantee bounded memory footprint."""
    if len(_CLIENT_REQUESTS) > 500:
        expired_ips = [
            ip for ip, timestamps in _CLIENT_REQUESTS.items()
            if not timestamps or (now - timestamps[-1] >= RATE_LIMIT_WINDOW)
        ]
        for ip in expired_ips:
            _CLIENT_REQUESTS.pop(ip, None)


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforces strict upper limit on incoming HTTP request body sizes to mitigate DoS attacks."""

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_CONTENT_LENGTH:
                    resp = JSONResponse(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        content={
                            "error": "Payload too large",
                            "message": f"Request body exceeds maximum allowed size of {MAX_CONTENT_LENGTH // 1024} KB.",
                        },
                    )
                    return apply_security_headers(resp)
            except ValueError:
                pass
        return await call_next(request)


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
        "script-src 'self' https://unpkg.com https://cdn.tailwindcss.com; "
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

        # Extract client IP — only trust X-Forwarded-For in production (behind a known proxy).
        # In development, spoofed headers would bypass rate limiting, so we use the direct
        # connection IP. This prevents clients from sending arbitrary X-Forwarded-For values
        # to whitelist themselves.
        if settings.environment == "production":
            forwarded_for = request.headers.get("X-Forwarded-For", "")
            # Cloud Run / GCP always appends the real client IP as the LAST entry.
            # Take the last entry to defeat spoofed prepended values.
            if forwarded_for:
                client_ip = forwarded_for.split(",")[-1].strip()
            elif request.client and request.client.host:
                client_ip = request.client.host
            else:
                client_ip = "127.0.0.1"
        else:
            # Development: always use direct TCP connection IP, ignore forwarded headers.
            client_ip = request.client.host if request.client and request.client.host else "127.0.0.1"

        now = time.monotonic()
        _prune_expired_client_ips(now)
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
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Incident dispatch unavailable — STAFF_SECRET_TOKEN not configured. Contact the administrator.",
        )

    if not token or not hmac.compare_digest(token, configured_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Valid X-Staff-Token header is required for operations dispatch.",
        )
    return True
