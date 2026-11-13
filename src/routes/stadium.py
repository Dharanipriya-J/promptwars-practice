"""
PitchPulse 2026 - Stadium Operations & Accessible Wayfinding Routes
Manages live gate telemetry, crowd density simulation, ADA accessible navigation,
predictive surge analytics, and staff incident dispatching.
"""

import logging
import random
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status

from services.gemini_service import (
    analyze_crowd_surge,
    build_maps_transit_url,
    generate_predictive_surge,
    update_live_gate_cache,
)
from src.models.enums import GateStatusLevel
from src.models.schemas import (
    AccessibleRouteRequest,
    AccessibleRouteResponse,
    ConcessionStand,
    GateStatus,
    IncidentReportRequest,
    IncidentReportResponse,
)
from src.utils.cache import timed_cache_get, timed_cache_set
from src.utils.routing import stadium_graph
from src.utils.security import verify_staff_token

logger = logging.getLogger("pitchpulse.stadium")
router = APIRouter(prefix="/api/stadium", tags=["Stadium Operations"])

# Incident Persistence Store (in-memory persistent registry across turns)
INCIDENTS_STORE: list[dict] = []


def _init_gates() -> list[GateStatus]:
    return [
        GateStatus(
            gate_id="gate-a",
            name="Gate A — North Main Concourse Plaza",
            density_percentage=42,
            wait_time_minutes=4,
            accessible_ramp=True,
            status_level=GateStatusLevel.NORMAL,
            predicted_surge_15m=58,
        ),
        GateStatus(
            gate_id="gate-b",
            name="Gate B — East ADA Accessible Concourse",
            density_percentage=28,
            wait_time_minutes=2,
            accessible_ramp=True,
            status_level=GateStatusLevel.NORMAL,
            predicted_surge_15m=35,
        ),
        GateStatus(
            gate_id="gate-c",
            name="Gate C — South Concourse Boulevard",
            density_percentage=78,
            wait_time_minutes=14,
            accessible_ramp=False,
            status_level=GateStatusLevel.SURGE,
            predicted_surge_15m=91,
        ),
        GateStatus(
            gate_id="gate-d",
            name="Gate D — West NJ Transit Hub",
            density_percentage=35,
            wait_time_minutes=3,
            accessible_ramp=True,
            status_level=GateStatusLevel.NORMAL,
            predicted_surge_15m=42,
        ),
    ]


GATES_DATA: list[GateStatus] = _init_gates()
update_live_gate_cache(GATES_DATA)

CONCESSIONS_DATA = [
    ConcessionStand(
        stand_id="c-1",
        name="Pitchside Artisan Grill",
        section="Sec 112",
        queue_wait_minutes=3,
        has_water_refill=True,
        dietary_options=["Halal", "Vegan", "Gluten-Free"],
    ),
    ConcessionStand(
        stand_id="c-2",
        name="World Cup Cantina",
        section="Sec 104",
        queue_wait_minutes=11,
        has_water_refill=True,
        dietary_options=["Vegetarian"],
    ),
    ConcessionStand(
        stand_id="c-3",
        name="Eco Hydration & Fruit Bar",
        section="Sec 128",
        queue_wait_minutes=1,
        has_water_refill=True,
        dietary_options=["Organic", "Nut-Free"],
    ),
]


def _simulate_gate_update() -> None:
    """
    Simulates real-time IoT gate sensor telemetry fluctuations.
    Dynamically recalculates status level and 15-minute surge projections.
    """
    for gate in GATES_DATA:
        # Subtle drift for simulation realism
        drift = random.choice([-3, -2, -1, 0, 1, 2, 3])
        new_density = max(5, min(98, gate.density_percentage + drift))
        gate.density_percentage = new_density
        gate.wait_time_minutes = max(1, int(new_density / 6))

        if new_density >= 70:
            gate.status_level = GateStatusLevel.SURGE
        elif new_density >= 40:
            gate.status_level = GateStatusLevel.MODERATE
        else:
            gate.status_level = GateStatusLevel.NORMAL

        gate.predicted_surge_15m = min(100, new_density + random.randint(2, 12))

    update_live_gate_cache(GATES_DATA)


@router.get("/gates", response_model=list[GateStatus])
def get_live_gate_status():
    """
    Returns live gate crowd telemetry with 15-minute predictive surge forecast.
    Advances real-time simulator to provide fresh decision-support data on every poll.
    """
    _simulate_gate_update()
    logger.info("Gate telemetry updated via live sensor simulator.")
    return GATES_DATA


@router.get("/concessions", response_model=list[ConcessionStand])
def get_concessions_status():
    """Returns queue wait times, dietary options, and eco-refill locations for venue concessions."""
    return CONCESSIONS_DATA


@router.post("/route", response_model=AccessibleRouteResponse)
def calculate_accessible_route(payload: AccessibleRouteRequest):
    """
    Generates verified step-free, ADA-compliant wayfinding directions for MetLife Stadium.
    Uses Dijkstra's algorithm over venue graph topology, evaluating every path segment
    for ramps, stairs, elevators, closures, and sensory quiet corridors.
    """
    # Live gate context dictionary for congestion penalty in Dijkstra routing
    gate_statuses = {
        g.gate_id: {"density": g.density_percentage, "surge": g.status_level.value == "surge"}
        for g in GATES_DATA
    }

    # Dijkstra graph-based accessible routing calculation
    route_calc = stadium_graph.find_accessible_route(
        target_section=payload.ticket_section,
        mobility_profile=payload.mobility_profile.value,
        prefer_elevators=payload.prefer_elevators,
        gate_statuses=gate_statuses,
    )

    maps_url = build_maps_transit_url(f"MetLife+Stadium+Section+{payload.ticket_section}+East+Rutherford+NJ")
    logger.info(
        "Dijkstra graph route calculated: section=%s profile=%s gate=%s step_free=%s",
        payload.ticket_section,
        payload.mobility_profile,
        route_calc.recommended_gate,
        route_calc.step_free,
    )

    return AccessibleRouteResponse(
        recommended_gate=route_calc.recommended_gate,
        accessible_path=route_calc.accessible_path,
        step_free=route_calc.step_free,
        nearest_quiet_room=route_calc.nearest_quiet_room,
        nearest_elevator=route_calc.nearest_elevator,
        estimated_walk_minutes=route_calc.estimated_walk_minutes,
        google_maps_directions_url=maps_url,
        routing_method=route_calc.routing_method,
    )


@router.get("/predict/{gate_id}")
def get_surge_prediction(gate_id: str):
    """
    Gemini GenAI predictive crowd surge forecast for a specific gate over the next 15 minutes.
    Provides automated operational advice to dispatch teams before bottleneck formation.
    """
    gate = next((g for g in GATES_DATA if g.gate_id == gate_id), None)
    if not gate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gate '{gate_id}' not found.",
        )

    cache_key = f"surge_prediction:{gate_id}:{gate.density_percentage}"
    cached = timed_cache_get(cache_key)
    if cached:
        return cached

    prediction_text = generate_predictive_surge(
        gate_density=gate.density_percentage,
        gate_name=gate.name,
        minutes_ahead=15,
    )
    result = {
        "gate_id": gate_id,
        "gate_name": gate.name,
        "current_density_pct": gate.density_percentage,
        "predicted_density_15m_pct": gate.predicted_surge_15m,
        "ai_recommendation": prediction_text,
        "powered_by": "Google Gemini 2.5 Flash — Predictive Crowd Intelligence",
    }
    timed_cache_set(cache_key, result)
    return result


@router.post("/incident", response_model=IncidentReportResponse)
def submit_incident_report(
    payload: IncidentReportRequest,
    request: Request,
    _auth: bool = Depends(verify_staff_token),
):
    """
    Staff-authenticated incident dispatch with Gemini AI operational recommendation.
    Protected by HMAC constant-time token comparison against unauthorized access.
    """
    incident_id = f"INC-{uuid.uuid4().hex[:6].upper()}"
    logged_at = datetime.now(UTC).isoformat()

    gate = next((g for g in GATES_DATA if payload.zone.lower() in g.name.lower()), None)
    density_context = gate.density_percentage if gate else 50

    ai_guidance = analyze_crowd_surge(
        zone=payload.zone,
        density=density_context,
        incident_type=payload.incident_type.value,
        description=payload.description,
    )

    assigned_team = (
        "Rapid Accessibility Unit (ADA Response)"
        if payload.incident_type.value == "accessibility_assist"
        else "Stadium Operations Command Unit 4"
    )

    logger.warning(
        "INCIDENT %s dispatched: zone=%s priority=%s team=%s",
        incident_id,
        payload.zone,
        payload.priority,
        assigned_team,
    )

    incident_record = {
        "incident_id": incident_id,
        "zone": payload.zone,
        "incident_type": payload.incident_type.value,
        "priority": payload.priority.value,
        "description": payload.description,
        "reporter_role": payload.reporter_role.value,
        "status": "dispatched",
        "assigned_team": assigned_team,
        "ai_recommendation": ai_guidance,
        "logged_at_utc": logged_at,
    }
    INCIDENTS_STORE.append(incident_record)

    return IncidentReportResponse(
        incident_id=incident_id,
        status="dispatched",
        assigned_team=assigned_team,
        estimated_response_minutes=3,
        ai_recommendation=ai_guidance,
        logged_at_utc=logged_at,
    )


@router.get("/incidents")
def list_incidents(_auth: bool = Depends(verify_staff_token)):
    """
    Staff-authenticated retrieval of persisted stadium operational incidents.
    Provides complete incident status tracking and history across turns.
    """
    return {
        "total_incidents": len(INCIDENTS_STORE),
        "incidents": INCIDENTS_STORE,
    }
