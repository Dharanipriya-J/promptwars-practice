"""
Automated Unit & Integration Test Suite for AURA Backend
Uses Python Built-in unittest module (Zero external dependencies).
Criterion #4: Testing
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import (
    app,
    health_check,
    get_products,
    ai_assistant_chat,
    process_checkout,
    ChatRequest,
    CheckoutRequest,
    CartItem,
    CATALOG_DB
)
from fastapi import HTTPException


class TestAuraBackend(unittest.TestCase):

    def test_01_health_check(self):
        """Verify health check returns valid Cloud Run status."""
        result = health_check()
        self.assertEqual(result["status"], "healthy")
        self.assertIn("Cloud Run", result["cloud_platform"])

    def test_02_catalog_count(self):
        """Verify product catalog returns all available hardware."""
        products = get_products()
        self.assertGreaterEqual(len(products), 4)
        for p in products:
            self.assertIn("id", p)
            self.assertIn("title", p)
            self.assertIn("price", p)
            self.assertGreater(p["price"], 0)

    def test_03_category_filtering(self):
        """Verify category filtering works accurately."""
        audio_products = get_products(category="Audio")
        self.assertTrue(all(p["category"] == "Audio" for p in audio_products))

        wearables = get_products(category="Wearables")
        self.assertTrue(all(p["category"] == "Wearables" for p in wearables))

    def test_04_ai_assistant_response(self):
        """Verify AI assistant generates contextual responses."""
        req = ChatRequest(message="Which hardware has lowest latency?")
        res = ai_assistant_chat(req)
        self.assertIsNotNone(res.reply)
        self.assertGreater(len(res.reply), 10)
        self.assertIn("TensorNode", res.reply)
        self.assertGreater(res.latency_ms, 0)

    def test_05_ai_audio_context(self):
        """Verify AI correctly identifies audio hardware queries."""
        req = ChatRequest(message="Tell me about the earbuds")
        res = ai_assistant_chat(req)
        self.assertIn("SpatialPulse", res.reply)

    def test_06_checkout_success(self):
        """Verify checkout creates order ID and computes total correctly."""
        req = CheckoutRequest(
            items=[CartItem(product_id=1, quantity=2)],
            customer_email="dharani@example.com",
            payment_method="apple_pay"
        )
        res = process_checkout(req)
        self.assertEqual(res.status, "confirmed")
        self.assertTrue(res.order_id.startswith("AURA-"))
        self.assertEqual(res.total_amount, 349.0 * 2)

    def test_07_checkout_empty_cart_fails(self):
        """Verify checkout raises 400 Bad Request for empty carts."""
        req = CheckoutRequest(
            items=[],
            customer_email="dharani@example.com"
        )
        with self.assertRaises(HTTPException) as ctx:
            process_checkout(req)
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
