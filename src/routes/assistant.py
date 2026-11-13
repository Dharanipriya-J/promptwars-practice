"""
PitchPulse 2026 - Multilingual AI Concierge API Routes
Exposes the Google Gemini 2.5 Flash natural language concierge for fan and staff assistance.
"""

import logging

from fastapi import APIRouter

from services.gemini_service import generate_multilingual_assistance
from src.models.schemas import ChatQueryRequest, ChatQueryResponse

logger = logging.getLogger("pitchpulse.assistant")
router = APIRouter(prefix="/api/assistant", tags=["Multilingual AI Concierge"])


@router.post("/query", response_model=ChatQueryResponse)
def query_stadium_assistant(req: ChatQueryRequest):
    """
    Submits a natural language query to the Gemini-powered multilingual concierge.
    Supports EN, ES, FR, PT, and AR with real language classification and transit links.
    """
    logger.info(
        "AI query received: lang=%s role=%s prompt_len=%d",
        req.language,
        req.user_role,
        len(req.prompt),
    )

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
