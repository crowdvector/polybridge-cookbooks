from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentic_finance.evidence import fetch_live_evidence, load_intent, load_json
from agentic_finance.gate import apply_gate
from agentic_finance.polybridge import PolyBridgeError


BASE_DIR = Path(__file__).resolve().parents[1]


class FakeLiveClient:
    def __init__(self, forecast_response: dict, search_response: dict | Exception) -> None:
        self.forecast_response = forecast_response
        self.search_response = search_response

    def search(self, query: str) -> dict:
        if isinstance(self.search_response, Exception):
            raise self.search_response
        return self.search_response

    def forecast(self, question: str) -> dict:
        return self.forecast_response


class LiveEvidenceTests(unittest.TestCase):
    def test_live_shaped_responses_normalize_into_evidence_packet(self) -> None:
        intent = load_intent(BASE_DIR / "fixtures")
        forecast = load_json(BASE_DIR / "fixtures" / "polybridge_forecast.live-shape.json")
        search = load_json(BASE_DIR / "fixtures" / "polybridge_search.live-shape.json")

        packet = fetch_live_evidence(intent, FakeLiveClient(forecast, search))

        self.assertIn("live_polybridge", packet.quality_flags)
        self.assertNotIn("offline_fixture", packet.quality_flags)
        self.assertEqual(packet.probability, 0.64)
        self.assertEqual(packet.evidence_profile["search_result_count"], 1)
        self.assertEqual(packet.evidence_profile["search_max_relevance"], 0.99)

    def test_search_relevance_is_not_used_as_forecast_probability(self) -> None:
        intent = load_intent(BASE_DIR / "fixtures")
        forecast = load_json(BASE_DIR / "fixtures" / "polybridge_forecast.live-shape.json")
        search = load_json(BASE_DIR / "fixtures" / "polybridge_search.live-shape.json")
        search["results"][0]["relevance"] = 0.99
        forecast["probability"] = 0.37

        packet = fetch_live_evidence(intent, FakeLiveClient(forecast, search))

        self.assertEqual(packet.probability, 0.37)
        self.assertEqual(packet.evidence_profile["search_max_relevance"], 0.99)

    def test_live_search_failure_sets_fetch_failure_flag_and_gate_blocks(self) -> None:
        intent = load_intent(BASE_DIR / "fixtures")
        forecast = load_json(BASE_DIR / "fixtures" / "polybridge_forecast.live-shape.json")

        packet = fetch_live_evidence(intent, FakeLiveClient(forecast, PolyBridgeError("search unavailable")))
        decision = apply_gate(packet)

        self.assertIn("search_unavailable", packet.quality_flags)
        self.assertEqual(decision.decision, "blocked_api_error")
        self.assertFalse(decision.cleared_for_paper_preview)


if __name__ == "__main__":
    unittest.main()
