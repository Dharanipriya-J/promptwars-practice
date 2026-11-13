# ── PitchPulse 2026 — Cloud Run Dockerfile ──────────────────────────────────
# Build:  docker build -t pitchpulse .
# Run:    docker run -p 8080:8080 --env-file .env pitchpulse
# Deploy: gcloud run deploy pitchpulse --source . --region us-central1
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.13-slim AS base

# Security: run as non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/       ./src/
COPY services/  ./services/
COPY index.html ./index.html
COPY .env.example .env.example

# Static assets (served by FastAPI StaticFiles if present)
RUN mkdir -p ./static ./docs
COPY static/ ./static/

# Non-root execution
RUN chown -R appuser:appgroup /app
USER appuser

# Cloud Run expects PORT env var (default 8080)
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')"

CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port $PORT --workers 2"]
