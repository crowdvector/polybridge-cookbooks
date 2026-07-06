from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tier1_evidence_gate as tier1
import tier3_alpaca_paper_trader as tier3
from agentic_finance.brokers.alpaca import PAPER_BASE_URL, AlpacaPaperConfig, AlpacaPaperError
from agentic_finance.multileg import (
    classify_leg,
    evaluate_thesis,
    load_recorded_run,
    load_theses,
)


BASE_DIR = Path(__file__).resolve().parents[1]
THESES_PATH = BASE_DIR / "examples" / "sample_theses.json"
REPLAY_PATH = BASE_DIR / "examples" / "recorded_run_2026-07-04.json"


class FakeResponse:
    status_code = 201

    def json(self) -> dict:
        return {
            "id": "fake_order_id",
            "client_order_id": "fake_client_order_id",
            "status": "accepted",
        }


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def post(self, url: str, headers: dict, json: dict, timeout: int) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse()


class LaborResilienceDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.theses = load_theses(THESES_PATH)
        self.replay = load_recorded_run(REPLAY_PATH)

    def test_labor_resilience_recorded_replay_proceeds(self) -> None:
        decision = evaluate_thesis(self.theses["labor-resilience-jul2026"], self.replay)

        self.assertEqual(decision.verdict, "PROCEED")
        self.assertEqual(decision.weighted_support, 3.0)
        self.assertEqual(decision.direct_evidence_legs, 3)
        self.assertEqual(decision.full_weight_contradictions, ())
        self.assertEqual([leg.classification for leg in decision.leg_decisions], ["SUPPORTS", "SUPPORTS", "SUPPORTS"])

    def test_oil_shock_recorded_replay_declines(self) -> None:
        decision = evaluate_thesis(self.theses["oil-shock-jul2026"], self.replay)

        self.assertEqual(decision.verdict, "DECLINE")
        self.assertEqual(decision.weighted_support, 1.0)
        self.assertEqual([leg.classification for leg in decision.leg_decisions], ["SUPPORTS", "NEUTRAL", "CONTRADICTS"])
        self.assertEqual(decision.leg_decisions[2].weight, 0.5)

    def test_rates_fall_recorded_replay_declines_on_full_weight_contradictions(self) -> None:
        decision = evaluate_thesis(self.theses["rates-fall-2026"], self.replay)

        self.assertEqual(decision.verdict, "DECLINE")
        self.assertGreaterEqual(len(decision.full_weight_contradictions), 1)
        self.assertIn("Will the Fed cut rates at its September 2026 meeting?", decision.full_weight_contradictions)

    def test_labor_resilience_paper_preview_is_spy_buy_1000(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            result = tier3.run_preview_or_submit(
                thesis_id="labor-resilience-jul2026",
                replay_path=REPLAY_PATH,
                theses_path=THESES_PATH,
                output_dir=Path(temp_dir),
                submit=False,
                base_dir=BASE_DIR,
            )
            self.assertTrue(result["paths"]["paper_preview"].exists())

        preview = result["paper_preview"]
        self.assertEqual(preview.symbol, "SPY")
        self.assertEqual(preview.side, "buy")
        self.assertEqual(preview.notional_usd, 1000.0)

    def test_decline_examples_do_not_create_paper_preview(self) -> None:
        for thesis_id in ("oil-shock-jul2026", "rates-fall-2026"):
            with self.subTest(thesis_id=thesis_id), tempfile.TemporaryDirectory() as temp_dir:
                result = tier3.run_preview_or_submit(
                    thesis_id=thesis_id,
                    replay_path=REPLAY_PATH,
                    theses_path=THESES_PATH,
                    output_dir=Path(temp_dir),
                    submit=False,
                    base_dir=BASE_DIR,
                )

                self.assertEqual(result["multi_leg_decision"].verdict, "DECLINE")
                self.assertIsNone(result["paper_preview"])
                self.assertNotIn("paper_preview", result["paths"])

    def test_gate_ignores_confidence_scalar_if_present(self) -> None:
        replay = copy.deepcopy(self.replay)
        for thesis in replay["theses"].values():
            for leg in thesis["legs"]:
                leg["confidence"] = 0.01

        original = evaluate_thesis(self.theses["labor-resilience-jul2026"], self.replay)
        changed = evaluate_thesis(self.theses["labor-resilience-jul2026"], replay)

        self.assertEqual(changed.verdict, original.verdict)
        self.assertEqual(
            [leg.classification for leg in changed.leg_decisions],
            [leg.classification for leg in original.leg_decisions],
        )

    def test_thresholds_are_read_from_thesis_config(self) -> None:
        thesis = self.theses["labor-resilience-jul2026"]
        first_leg = thesis.questions[0]
        tightened = replace(first_leg, threshold=0.1)
        recorded_leg = self.replay["theses"][thesis.thesis_id]["legs"][0]

        original_decision = classify_leg(thesis, first_leg, recorded_leg)
        tightened_decision = classify_leg(thesis, tightened, recorded_leg)

        self.assertEqual(original_decision.classification, "SUPPORTS")
        self.assertEqual(tightened_decision.classification, "NEUTRAL")

    def test_proxy_only_evidence_gets_half_weight(self) -> None:
        thesis = self.theses["oil-shock-jul2026"]
        leg = thesis.questions[2]
        recorded_leg = self.replay["theses"][thesis.thesis_id]["legs"][2]

        decision = classify_leg(thesis, leg, recorded_leg)

        self.assertEqual(decision.evidence_profile, "proxy_only")
        self.assertEqual(decision.weight, 0.5)

    def test_insufficient_or_failed_legs_get_zero_weight(self) -> None:
        thesis = self.theses["labor-resilience-jul2026"]
        leg = thesis.questions[0]
        recorded_leg = copy.deepcopy(self.replay["theses"][thesis.thesis_id]["legs"][0])
        recorded_leg["insufficient_data"] = True

        decision = classify_leg(thesis, leg, recorded_leg)

        self.assertEqual(decision.classification, "INSUFFICIENT")
        self.assertEqual(decision.weight, 0.0)

    def test_tier1_replay_runs_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = tier1.run_replay(
                thesis_id="labor-resilience-jul2026",
                replay_path=REPLAY_PATH,
                theses_path=THESES_PATH,
                output_dir=Path(temp_dir),
                base_dir=BASE_DIR,
            )
            self.assertTrue(result["paths"]["decision_memo"].exists())
            self.assertTrue(result["paths"]["decisions_log"].exists())

        self.assertEqual(result["multi_leg_decision"].verdict, "PROCEED")

    def test_tier3_preview_only_runs_without_credentials_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            result = tier3.run_preview_or_submit(
                thesis_id="labor-resilience-jul2026",
                replay_path=REPLAY_PATH,
                theses_path=THESES_PATH,
                output_dir=Path(temp_dir),
                submit=False,
                base_dir=BASE_DIR,
            )

        self.assertEqual(result["mode"], "preview_only")
        self.assertEqual(result["paper_preview"].symbol, "SPY")

    def test_guarded_submission_still_requires_confirmations_before_request(self) -> None:
        session = FakeSession()
        with tempfile.TemporaryDirectory() as temp_dir, self.assertRaises(AlpacaPaperError):
            tier3.run_preview_or_submit(
                thesis_id="labor-resilience-jul2026",
                replay_path=REPLAY_PATH,
                theses_path=THESES_PATH,
                output_dir=Path(temp_dir),
                submit=True,
                config=AlpacaPaperConfig(
                    api_key="paper_key",
                    api_secret="paper_secret",
                    base_url=PAPER_BASE_URL,
                    paper_trade="true",
                ),
                session=session,
                confirm_paper_trading=False,
                confirm_not_financial_advice=True,
                confirm_human_approval=True,
                base_dir=BASE_DIR,
            )

        self.assertEqual(session.calls, [])

    def test_guarded_submission_blocks_live_endpoint_before_request(self) -> None:
        session = FakeSession()
        with tempfile.TemporaryDirectory() as temp_dir, self.assertRaises(AlpacaPaperError):
            tier3.run_preview_or_submit(
                thesis_id="labor-resilience-jul2026",
                replay_path=REPLAY_PATH,
                theses_path=THESES_PATH,
                output_dir=Path(temp_dir),
                submit=True,
                config=AlpacaPaperConfig(
                    api_key="paper_key",
                    api_secret="paper_secret",
                    base_url="https://api.alpaca.markets",
                    paper_trade="true",
                ),
                session=session,
                confirm_paper_trading=True,
                confirm_not_financial_advice=True,
                confirm_human_approval=True,
                base_dir=BASE_DIR,
            )

        self.assertEqual(session.calls, [])

    def test_sample_labor_assets_are_valid_and_sanitized(self) -> None:
        json_assets = [
            BASE_DIR / "assets" / "sample-labor-resilience-paper-preview.json",
        ]
        for path in json_assets:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                json.loads(text)
                self.assertNotIn("/Users/", text)
                self.assertNotIn("APCA_API_SECRET", text)
                self.assertNotIn("paper_secret", text)

        audit_text = (BASE_DIR / "assets" / "sample-labor-resilience-audit-log.jsonl").read_text(encoding="utf-8")
        self.assertEqual(len(audit_text.splitlines()), 1)
        json.loads(audit_text)
        self.assertNotIn("/Users/", audit_text)
        self.assertNotIn("fake_order_id", audit_text)


if __name__ == "__main__":
    unittest.main()
