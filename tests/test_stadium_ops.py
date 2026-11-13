"""
PitchPulse 2026 - Comprehensive Automated Test Suite
Compatible with both pytest and python unittest test runners.
Covers happy paths, security headers, rate limiting (429), authentication (401),
Gemini failure resilience (timeout/empty), XSS sanitization, and language detection.
"""

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure root directory is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from src.main import app
from src.utils.cache import _CACHE, parse_section_number, timed_cache_get, timed_cache_set
from src.utils.security import _CLIENT_REQUESTS

client = TestClient(app)
STAFF_HEADERS = {"X-Staff-Token": "fifa-staff-secure-2026"}


class TestPitchPulseSuite(unittest.TestCase):
    def setUp(self):
        """Reset state between every test case."""
        _CACHE.clear()
        _CLIENT_REQUESTS.clear()

    def tearDown(self):
        _CACHE.clear()
        _CLIENT_REQUESTS.clear()

    # ─────────────────────────── SYSTEM & HEALTH ───────────────────────────

    def test_01_health_returns_200(self):
        """Health check returns 200 OK with Cloud Run deployment label."""
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("Cloud Run", data["deployment_target"])
        self.assertIn("cache", data)

    def test_02_docs_are_accessible(self):
        """Swagger documentation endpoint returns 200."""
        r = client.get("/docs")
        self.assertEqual(r.status_code, 200)

    def test_03_security_headers_present(self):
        """Verifies zero-trust HTTP security headers on API responses."""
        r = client.get("/api/health")
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(r.headers.get("x-frame-options"), "DENY")
        self.assertIn("max-age=31536000", r.headers.get("strict-transport-security", ""))
        self.assertIn("default-src", r.headers.get("content-security-policy", ""))

    # ─────────────────────────── GATE TELEMETRY ───────────────────────────

    def test_04_all_gates_returned(self):
        """Gate telemetry returns exactly 4 MetLife Stadium tournament gates."""
        r = client.get("/api/stadium/gates")
        self.assertEqual(r.status_code, 200)
        gates = r.json()
        self.assertEqual(len(gates), 4)

    def test_05_density_bounds(self):
        """Gate crowd density is bounded between 0 and 100 percent."""
        r = client.get("/api/stadium/gates")
        for g in r.json():
            self.assertGreaterEqual(g["density_percentage"], 0)
            self.assertLessEqual(g["density_percentage"], 100)

    def test_06_gate_b_is_step_free(self):
        """Gate B is verified step-free accessible for ADA compliance."""
        r = client.get("/api/stadium/gates")
        gate_b = next(g for g in r.json() if g["gate_id"] == "gate-b")
        self.assertTrue(gate_b["accessible_ramp"])

    def test_07_surge_prediction_forecast(self):
        """Gate telemetry contains 15-minute predictive surge forecast."""
        r = client.get("/api/stadium/gates")
        for g in r.json():
            self.assertIn("predicted_surge_15m", g)
            self.assertGreaterEqual(g["predicted_surge_15m"], 0)

    def test_08_concessions_endpoint(self):
        """Concessions endpoint returns nutrition queues and free eco-refill locations."""
        r = client.get("/api/stadium/concessions")
        self.assertEqual(r.status_code, 200)
        stands = r.json()
        self.assertGreaterEqual(len(stands), 3)
        self.assertTrue(any(s["has_water_refill"] for s in stands))

    # ─────────────────────────── PARSER REGRESSION ───────────────────────────

    def test_09_section_104_parses_correctly(self):
        """Regression test: Section '104' parses to integer 104 (not '10')."""
        self.assertEqual(parse_section_number("104"), 104)

    def test_10_section_218_parses_correctly(self):
        self.assertEqual(parse_section_number("218"), 218)

    def test_11_alphanumeric_section(self):
        self.assertEqual(parse_section_number("A12"), 12)

    # ─────────────────────────── ACCESSIBLE WAYFINDING ───────────────────────────

    def test_12_wheelchair_route_via_gate_b(self):
        """Wheelchair profile routes via Gate B with priority ADA elevators."""
        r = client.post("/api/stadium/route", json={"ticket_section": "104", "mobility_profile": "wheelchair"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("Gate B", data["recommended_gate"])
        self.assertTrue(data["step_free"])
        self.assertIn("Elevator", data["nearest_elevator"])

    def test_13_sensory_route_has_quiet_room(self):
        """Sensory-sensitive profile designates a Quiet Suite."""
        r = client.post("/api/stadium/route", json={"ticket_section": "201", "mobility_profile": "sensory_sensitive"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("Sensory Quiet Suite", data["nearest_quiet_room"])

    def test_14_empty_section_returns_422(self):
        r = client.post("/api/stadium/route", json={"ticket_section": "", "mobility_profile": "standard"})
        self.assertEqual(r.status_code, 422)

    def test_15_invalid_profile_returns_422(self):
        r = client.post("/api/stadium/route", json={"ticket_section": "104", "mobility_profile": "teleport"})
        self.assertEqual(r.status_code, 422)

    # ─────────────────────────── GEMINI AI CONCIERGE ───────────────────────────

    def test_16_gemini_called_when_key_present(self):
        """When Gemini client is available, it responds with live transit instructions."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Board the FIFA Express Metro train at Gate D Plaza."
        mock_client.models.generate_content.return_value = mock_resp

        with patch("services.gemini_service.get_genai_client", return_value=mock_client):
            r = client.post(
                "/api/assistant/query",
                json={"prompt": "Which train takes me to Penn Station?", "language": "en", "user_role": "fan"},
            )
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertEqual(data["source"], "google-gemini-2.5-flash")
            self.assertIn("FIFA Express", data["response"])
            self.assertIsNotNone(data["maps_transit_link"])

    def test_17_gemini_down_uses_offline_resilient_engine(self):
        """If Gemini raises an exception, the system gracefully falls back to offline engine."""
        with patch("services.gemini_service.get_genai_client") as mock_get:
            mock_inst = MagicMock()
            mock_inst.models.generate_content.side_effect = ConnectionError("Network down")
            mock_get.return_value = mock_inst

            r = client.post(
                "/api/assistant/query",
                json={"prompt": "Where is the wheelchair ramp?", "language": "en", "user_role": "fan"},
            )
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertEqual(data["source"], "offline-resilient-engine")
            self.assertIn("Gate B", data["response"])

    def test_18_gemini_timeout_handled(self):
        """Gemini timeout triggers offline fallback cleanly with 200 status."""
        with patch("services.gemini_service.get_genai_client") as mock_get:
            mock_inst = MagicMock()
            mock_inst.models.generate_content.side_effect = TimeoutError("Deadline exceeded")
            mock_get.return_value = mock_inst

            r = client.post(
                "/api/assistant/query",
                json={"prompt": "How do I exit the stadium?", "language": "en", "user_role": "fan"},
            )
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["source"], "offline-resilient-engine")

    def test_19_empty_gemini_response_fallback(self):
        """Empty or blocked Gemini response triggers offline fallback."""
        with patch("services.gemini_service.get_genai_client") as mock_get:
            mock_inst = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = ""
            mock_inst.models.generate_content.return_value = mock_resp
            mock_get.return_value = mock_inst

            r = client.post(
                "/api/assistant/query", json={"prompt": "Where is gate B?", "language": "en", "user_role": "fan"}
            )
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["source"], "offline-resilient-engine")

    # ─────────────────────────── MULTILINGUAL & EMERGENCY ───────────────────────────

    def test_20_spanish_detection(self):
        r = client.post(
            "/api/assistant/query",
            json={"prompt": "Hola, ¿dónde está el baño accesible?", "language": "auto", "user_role": "fan"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["detected_language"], "es")

    def test_21_french_detection_no_false_positive(self):
        """Word 'you' in English prompt must NOT false-positive as French."""
        r = client.post(
            "/api/assistant/query", json={"prompt": "Can you show me the ramp?", "language": "auto", "user_role": "fan"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["detected_language"], "en")

    def test_22_arabic_detection(self):
        """Arabic script is correctly detected."""
        r = client.post(
            "/api/assistant/query",
            json={"prompt": "أين أجد المدخل المخصص للكراسي المتحركة؟", "language": "auto", "user_role": "fan"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["detected_language"], "ar")

    def test_23_portuguese_detection(self):
        """Portuguese query detected accurately."""
        r = client.post(
            "/api/assistant/query",
            json={"prompt": "Olá, onde fica a cadeira de rodas?", "language": "auto", "user_role": "fan"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["detected_language"], "pt")

    def test_24_offline_safety_emergency_guidance(self):
        """Medical distress prompts route to safety protocol with first aid directions."""
        r = client.post(
            "/api/assistant/query",
            json={"prompt": "I feel dizzy and need urgent medical help", "language": "en", "user_role": "fan"},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["action_type"], "safety")
        self.assertTrue(any(w in data["response"].lower() for w in ["first aid", "911", "medical"]))

    # ─────────────────────────── SECURITY & AUTH ───────────────────────────

    def test_25_incident_without_token_returns_401(self):
        """Unauthenticated incident submission is rejected with 401 Unauthorized."""
        r = client.post(
            "/api/stadium/incident",
            json={
                "zone": "Gate C",
                "incident_type": "congestion",
                "priority": "high",
                "reporter_role": "volunteer",
                "description": "Gate congestion",
            },
        )
        self.assertEqual(r.status_code, 401)

    def test_26_incident_with_bad_token_returns_401(self):
        """Invalid X-Staff-Token is rejected with 401."""
        r = client.post(
            "/api/stadium/incident",
            json={
                "zone": "Gate C",
                "incident_type": "congestion",
                "priority": "high",
                "reporter_role": "venue_staff",
                "description": "Surge",
            },
            headers={"X-Staff-Token": "invalid-hacker-token"},
        )
        self.assertEqual(r.status_code, 401)

    def test_27_incident_with_token_dispatches(self):
        """Valid X-Staff-Token dispatches incident and returns operational recommendation."""
        r = client.post(
            "/api/stadium/incident",
            json={
                "zone": "Gate C",
                "incident_type": "congestion",
                "priority": "high",
                "reporter_role": "venue_staff",
                "description": "Gate C turnstiles crowded",
            },
            headers=STAFF_HEADERS,
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["incident_id"].startswith("INC-"))
        self.assertEqual(data["status"], "dispatched")

    def test_28_rate_limit_429(self):
        """Exceeding rate limit on /api/assistant/query returns 429 with retry info."""
        for i in range(10):
            r = client.post(
                "/api/assistant/query", json={"prompt": f"test rate prompt {i}", "language": "en", "user_role": "fan"}
            )
            self.assertEqual(r.status_code, 200)

        # 11th request exceeds limit of 10
        r_limited = client.post(
            "/api/assistant/query", json={"prompt": "overflow request", "language": "en", "user_role": "fan"}
        )
        self.assertEqual(r_limited.status_code, 429)
        self.assertIn("Rate limit exceeded", r_limited.json()["error"])
        # Check security headers on 429 response
        self.assertEqual(r_limited.headers.get("x-content-type-options"), "nosniff")

    def test_29_xss_input_safety(self):
        """Input containing script tags does not compromise the API response."""
        r = client.post(
            "/api/assistant/query",
            json={"prompt": "<script>alert('xss')</script> where is gate b", "language": "en", "user_role": "fan"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("<script>", r.json().get("response", ""))

    # ─────────────────────────── CACHING & EFFICIENCY ───────────────────────────

    def test_30_cache_ttl_and_eviction(self):
        """Expired entries in TTL cache return None upon retrieval."""
        _CACHE.clear()
        timed_cache_set("test-key", "test-val")
        # Age the entry beyond 60s
        _CACHE["test-key"] = (time.monotonic() - 75, "test-val")
        self.assertIsNone(timed_cache_get("test-key"))

    def test_31_surge_prediction_endpoint(self):
        """Predictive crowd surge endpoint returns 15-minute outlook."""
        r = client.get("/api/stadium/predict/gate-c")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["gate_id"], "gate-c")
        self.assertIn("ai_recommendation", data)

    def test_32_surge_prediction_invalid_gate_404(self):
        r = client.get("/api/stadium/predict/gate-unknown")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
