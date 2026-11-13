"""
Vercel serverless entry point for PitchPulse 2026.
Imports the FastAPI app instance for Vercel's Python runtime.
"""
from src.main import app  # noqa: F401 — Vercel picks up `app` automatically
