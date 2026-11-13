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
from src.utils.cache import calculate_optimal_path, timed_cache_get, timed_cache_set
from src.utils.security import verify_staff_token

logger = logging.getLogger("pitchpulse.stadium")
router = APIRouter(prefix="/api/stadium", tags=["Stadium Operations"])


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
    Dynamically routes sensory-sensitive fans away from congested or non-accessible gates.
    """
    gate, elevator, quiet_room, walk_time = calculate_optimal_path(
        payload.ticket_section, payload.mobility_profile.value
    )

    # Determine actual step_free status by checking the assigned gate's accessible_ramp field.
    # This prevents returning step_free=True for a gate that lacks a ramp.
    # For wheelchair/low_mobility profiles: if the assigned gate has no ramp, find the best
    # accessible alternative rather than returning an inaccessible route.
    needs_step_free = payload.mobility_profile.value in ("wheelchair", "low_mobility", "sensory_sensitive")

    # Find the gate record matching the recommended gate name
    gate_record = None
    for g in GATES_DATA:
        if g.gate_id in gate.lower().replace(" ", "-"):
            gate_record = g
            break
    # Fallback: search by partial name match
    if gate_record is None:
        for g in GATES_DATA:
            if any(part in gate for part in [g.gate_id.upper(), g.gate_id.capitalize()]):
                gate_record = g
                break

    # Verify the route is truly step-free if the profile requires it
    route_accessible = True
    accessibility_warning = None

    if needs_step_free and gate_record is not None and not gate_record.accessible_ramp:
        # The assigned gate has no ramp — find an accessible alternative
        accessible_gates = [g for g in GATES_DATA if g.accessible_ramp and g.status_level.value != "surge"]
        if accessible_gates:
            # Prefer least-crowded accessible gate
            best = min(accessible_gates, key=lambda g: g.density_percentage)
            original_gate = gate
            gate = f"{best.name} [Rerouted — {original_gate.split('(')[0].strip()} inaccessible]"
            gate_record = best
            logger.warning(
                "Rerouted %s profile: original gate has no ramp. Using %s instead.",
                payload.mobility_profile.value,
                best.gate_id,
            )
        else:
            route_accessible = False
            accessibility_warning = (
                "No fully accessible step-free gate is currently available. "
                "Please contact a stadium accessibility assistant for personal escort."
            )
            logger.warning("No accessible gate available for mobility profile %s.", payload.mobility_profile.value)

    # Determine final step_free value: True only if the entire route is verified accessible
    is_step_free = route_accessible and (gate_record.accessible_ramp if gate_record else False or not needs_step_free)

    # Dynamic safety check: If sensory route resolves to a surging gate, redirect to Gate B
    if payload.mobility_profile.value == "sensory_sensitive":
        gate_c = next((g for g in GATES_DATA if g.gate_id == "gate-c"), None)
        if gate_c and gate_c.density_percentage >= 70:
            # Also check that gate B is accessible
            gate_b = next((g for g in GATES_DATA if g.gate_id == "gate-b"), None)
            if gate_b and gate_b.accessible_ramp:
                logger.info("Rerouting sensory-sensitive fan away from congested Gate C to Gate B.")
                gate = "Gate B (East Accessible Concourse — Quiet Alternate) — MetLife Stadium"
                quiet_room = "Sensory Quiet Suite #2 (North Mezzanine Level 2) — Quiet zone active"
                is_step_free = True

    maps_url = build_maps_transit_url(f"MetLife+Stadium+Section+{payload.ticket_section}+East+Rutherford+NJ")
    logger.info(
        "Route calculated: section=%s profile=%s gate=%s",
        payload.ticket_section,
        payload.mobility_profile,
        gate,
    )

    return AccessibleRouteResponse(
        recommended_gate=gate,
        accessible_path=[
            f"Enter via {gate} — priority ADA turnstiles active",
            "Follow illuminated high-contrast tactile flooring path (zero stairs)",
            f"Board {elevator} — ADA compliant with audible floor alerts",
            f"Exit at Concourse Level — direct level path to Section {payload.ticket_section.upper()}",
            *(
                [f"⚠ Accessibility Notice: {accessibility_warning}"]
                if accessibility_warning
                else []
            ),
        ],
        step_free=is_step_free,
        nearest_quiet_room=quiet_room,
        nearest_elevator=elevator,
        estimated_walk_minutes=walk_time,
        google_maps_directions_url=maps_url,
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

    return IncidentReportResponse(
        incident_id=incident_id,
        status="dispatched",
        assigned_team=assigned_team,
        estimated_response_minutes=3,
        ai_recommendation=ai_guidance,
        logged_at_utc=logged_at,
    )
