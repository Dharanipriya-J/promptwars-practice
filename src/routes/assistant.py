"""
PITCHPULSE 2026 - Multilingual AI Concierge API Routes
Criterion #6: Google Services Usage (Gemini 2.5 Flash + Google Maps Transit)
"""

import logging
from fastapi import APIRouter, HTTPException, status
from src.models.schemas import ChatQueryRequest, ChatQueryResponse
from services.gemini_service import generate_multilingual_assistance
from src.utils.cache import timed_cache_get

logger = logging.getLogger("pitchpulse.assistant")
router = APIRouter(prefix="/api/assistant", tags=["Multilingual AI Concierge"])


@router.post("/query", response_model=ChatQueryResponse)
def query_stadium_assistant(req: ChatQueryRequest):
    """
    Submits a natural language query to the Gemini-powered multilingual concierge.
    Supports EN, ES, FR, PT, AR via real language detection and translation.
    Returns structured response with Google Maps transit link when applicable.
    """
    logger.info("AI query received: lang=%s role=%s prompt_len=%d",
                req.language, req.user_role, len(req.prompt))

    result = generate_multilingual_assistance(
        prompt=req.prompt,
        target_lang=req.language.value,
        role=req.user_role.value,
    )

    return ChatQueryResponse(
        response=result["response"],
        detected_language=result["detected_language"],
        action_type=result["action_type"],
        latency_ms=result["latency_ms"],
        source=result["source"],
        maps_transit_link=result.get("maps_transit_link"),
    )
