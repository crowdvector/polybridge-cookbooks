from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentic_finance.evidence import build_evidence_packet, load_json
from agentic_finance.gate import apply_gate
from agentic_finance.portfolio import (
    PortfolioRiskItem,
    build_portfolio_risk_map,
    exposure_to_intent,
    load_offline_portfolio_evidence,
    map_holdings_to_exposures,
    parse_holdings_csv,
    risk_band,
)
from run_portfolio_risk_map import run_portfolio_risk_map_workflow


BASE_DIR = Path(__file__).resolve().parents[1]
HOLDINGS_PATH = BASE_DIR / "examples" / "sample_holdings.csv"
PORTFOLIO_FIXTURES = BASE_DIR / "fixtures" / "portfolio"
MEMO_BANNED_PATTERN = re.compile(r"\b(buy|sell|recommend(?:ed|s|ation)?|financial advice)\b", re.IGNORECASE)
SECRET_PATTERN = re.compile(
    r"Bearer\s+|\bsk-[A-Za-z0-9]|Authorization|POLYBRIDGE_API_KEY|ALPACA_SECRET",
    re.IGNORECASE,
)


class PortfolioRiskMapTests(unittest.TestCase):
    def test_holdings_csv_parsing(self) -> None:
        holdings = parse_holdings_csv(HOLDINGS_PATH)

        self.assertEqual(len(holdings), 5)
        self.assertEqual(holdings[0].symbol, "SPY")
        self.assertEqual(holdings[0].notional_usd, 6500.0)
        self.assertEqual(holdings[-1].sector, "gold")

    def test_deterministic_exposure_mapping(self) -> None:
        holdings = parse_holdings_csv(HOLDINGS_PATH)
        exposures = map_holdings_to_exposures(holdings)

        self.assertEqual(
            tuple(exposure.exposure_id for exposure in exposures),
            ("rates", "volatility", "ai_regulation", "energy"),
        )
        exposure_by_id = {exposure.exposure_id: exposure for exposure in exposures}
        self.assertEqual(exposure_by_id["rates"].affected_symbols, ("SPY", "QQQ", "TLT", "GLD"))
        self.assertEqual(exposure_by_id["ai_regulation"].affected_symbols, ("QQQ",))
        self.assertEqual(exposure_by_id["energy"].affected_symbols, ("XLE",))

    def test_risk_map_shape(self) -> None:
        holdings = parse_holdings_csv(HOLDINGS_PATH)
        exposures = map_holdings_to_exposures(holdings)
        risk_items = []
        for exposure in exposures:
            packet = load_offline_portfolio_evidence(exposure, PORTFOLIO_FIXTURES)
            decision = apply_gate(packet)
            risk_items.append(PortfolioRiskItem(exposure, packet, decision, risk_band(packet, decision)))

        risk_map = build_portfolio_risk_map("run_test", holdings, exposures, tuple(risk_items), created_at="2026-07-05T12:00:00Z")

        self.assertEqual(risk_map["schema_version"], "portfolio_risk_map.v1")
        self.assertEqual(risk_map["tier"], "portfolio_event_risk_map")
        self.assertEqual(risk_map["methodology"]["adapter_boundary"], "EvidencePacket")
        self.assertEqual(risk_map["methodology"]["probability_source"], "forecast_only")
        self.assertEqual(len(risk_map["risk_items"]), 4)

    def test_portfolio_memo_contains_disclaimer_without_action_language(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_portfolio_risk_map_workflow(
                holdings_path=HOLDINGS_PATH,
                base_dir=BASE_DIR,
                output_dir=Path(temp_dir),
            )

        memo = result["memo"]
        self.assertIn("read-only memo", memo)
        self.assertIn("does not place orders", memo)
        self.assertIn("does not instruct portfolio changes", memo)
        self.assertIsNone(MEMO_BANNED_PATTERN.search(memo))

    def test_offline_portfolio_workflow_writes_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_portfolio_risk_map_workflow(
                holdings_path=HOLDINGS_PATH,
                base_dir=BASE_DIR,
                output_dir=Path(temp_dir),
            )

            paths = result["paths"]
            self.assertTrue(paths["portfolio_risk_map"].exists())
            self.assertTrue(paths["portfolio_risk_memo"].exists())
            self.assertTrue(paths["audit_log"].exists())
            self.assertNotIn("paper_preview", paths)
            self.assertNotIn("alpaca", "\n".join(str(path).lower() for path in paths.values()))

    def test_portfolio_audit_log_is_valid_jsonl_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_portfolio_risk_map_workflow(
                holdings_path=HOLDINGS_PATH,
                base_dir=BASE_DIR,
                output_dir=Path(temp_dir),
            )

            audit_text = result["paths"]["audit_log"].read_text(encoding="utf-8")
            lines = audit_text.strip().splitlines()
            self.assertEqual(len(lines), 1)
            audit = json.loads(lines[0])
            self.assertEqual(audit["schema_version"], "portfolio_audit_record.v1")
            self.assertEqual(audit["tier"], "portfolio_event_risk_map")
            self.assertEqual(audit["holdings_source"], "examples/sample_holdings.csv")
            self.assertTrue(audit["guardrails"]["no_broker_submission"])
            self.assertTrue(audit["guardrails"]["no_raw_polybridge_responses_persisted"])
            self.assertFalse(Path(audit["holdings_source"]).is_absolute())
            self.assertNotIn("/Users/", audit_text)
            self.assertIsNone(SECRET_PATTERN.search(audit_text))

    def test_search_relevance_is_not_used_as_probability(self) -> None:
        holdings = parse_holdings_csv(HOLDINGS_PATH)
        exposure = map_holdings_to_exposures(holdings)[0]
        forecast = load_json(PORTFOLIO_FIXTURES / "rates_forecast.response.json")
        search = load_json(PORTFOLIO_FIXTURES / "rates_search.response.json")
        forecast["probability"] = 0.37
        search["results"][0]["relevance"] = 0.99

        packet = build_evidence_packet(exposure_to_intent(exposure), forecast, search)

        self.assertEqual(packet.probability, 0.37)
        self.assertEqual(packet.evidence_profile["search_max_relevance"], 0.99)

    def test_forecast_probability_is_used_as_probability(self) -> None:
        holdings = parse_holdings_csv(HOLDINGS_PATH)
        exposure = map_holdings_to_exposures(holdings)[0]
        packet = load_offline_portfolio_evidence(exposure, PORTFOLIO_FIXTURES)

        self.assertEqual(packet.probability, 0.62)

    def test_failure_flags_block_gate_for_affected_exposure(self) -> None:
        holdings = parse_holdings_csv(HOLDINGS_PATH)
        exposure = map_holdings_to_exposures(holdings)[0]
        forecast = load_json(PORTFOLIO_FIXTURES / "rates_forecast.response.json")
        search = load_json(PORTFOLIO_FIXTURES / "rates_search.response.json")
        search["status"] = "error"

        packet = build_evidence_packet(exposure_to_intent(exposure), forecast, search)
        decision = apply_gate(packet)

        self.assertIn("search_unavailable", packet.quality_flags)
        self.assertEqual(decision.decision, "blocked_api_error")

    def test_no_alpaca_or_broker_path_is_involved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_portfolio_risk_map_workflow(
                holdings_path=HOLDINGS_PATH,
                base_dir=BASE_DIR,
                output_dir=Path(temp_dir),
            )

        self.assertTrue(result["risk_map"]["guardrails"]["no_live_broker_calls"])
        self.assertTrue(result["risk_map"]["guardrails"]["no_broker_submission"])
        self.assertNotIn("paper_preview", result["paths"])


if __name__ == "__main__":
    unittest.main()
