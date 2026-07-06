from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tier3_paper_trader as paper_trader
from agentic_finance.brokers.alpaca import PAPER_BASE_URL, AlpacaPaperConfig, AlpacaPaperError


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


class SimBrokerPaperTraderTests(unittest.TestCase):
    def run_default(self, output_dir: Path, confirmation: str = "y", thesis_id: str = "labor-resilience-jul2026") -> dict:
        return paper_trader.run_paper_trader(
            thesis_id=thesis_id,
            replay_path=REPLAY_PATH,
            theses_path=THESES_PATH,
            output_dir=output_dir,
            confirmation=confirmation,
            base_dir=BASE_DIR,
        )

    def test_default_broker_is_simbroker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_default(Path(temp_dir), confirmation="n")

        self.assertEqual(result["broker"], "sim")
        self.assertEqual(result["broker_preview"]["broker_name"], "SimBroker")
        self.assertTrue(result["broker_preview"]["no_brokerage_account_required"])

    def test_simbroker_requires_no_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            result = self.run_default(Path(temp_dir), confirmation="y")

        self.assertEqual(result["broker_event"], "simulated_fill_recorded")
        self.assertEqual(result["broker_result"]["symbol"], "SPY")

    def test_simbroker_makes_no_network_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_default(Path(temp_dir), confirmation="y")

        self.assertTrue(result["broker_preview"]["no_network_calls"])
        self.assertTrue(result["broker_result"]["no_live_trading"])

    def test_labor_resilience_y_records_spy_buy_1000_simulated_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_default(Path(temp_dir), confirmation="y")
            lines = result["paths"]["paper_portfolio"].read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["broker"], "sim")
        self.assertEqual(record["thesis_id"], "labor-resilience-jul2026")
        self.assertEqual(record["symbol"], "SPY")
        self.assertEqual(record["side"], "buy")
        self.assertEqual(record["notional"], "1000.00")
        self.assertTrue(record["simulated_order_id"].startswith("sim_"))

    def test_human_decline_records_decline_and_no_simulated_fill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_default(Path(temp_dir), confirmation="n")
            output_dir = Path(temp_dir)
            decisions = output_dir / "decisions.jsonl"
            portfolio = output_dir / "paper_portfolio.jsonl"
            decision_lines = decisions.read_text(encoding="utf-8").splitlines()

        self.assertEqual(result["broker_event"], "human_declined")
        self.assertFalse(portfolio.exists())
        self.assertTrue(any(json.loads(line).get("event") == "human_declined" for line in decision_lines))

    def test_decline_examples_do_not_call_broker(self) -> None:
        for thesis_id in ("oil-shock-jul2026", "rates-fall-2026"):
            with self.subTest(thesis_id=thesis_id), tempfile.TemporaryDirectory() as temp_dir:
                result = self.run_default(Path(temp_dir), confirmation="y", thesis_id=thesis_id)
                output_dir = Path(temp_dir)

                self.assertEqual(result["broker_event"], "skipped_decline")
                self.assertFalse((output_dir / "paper_portfolio.jsonl").exists())
                self.assertFalse((output_dir / "paper-order-preview.json").exists())

    def test_paper_portfolio_jsonl_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_default(Path(temp_dir), confirmation="y")
            text = result["paths"]["paper_portfolio"].read_text(encoding="utf-8")

        self.assertNotIn("/Users/", text)
        self.assertNotIn("/home/", text)
        self.assertNotIn("APCA_API_SECRET", text)
        self.assertNotIn("paper_secret", text)
        self.assertNotIn("account_id", text)

    def test_decisions_jsonl_includes_proceed_and_decline_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            proceed = self.run_default(output_dir, confirmation="y")
            decline = self.run_default(output_dir, confirmation="y", thesis_id="oil-shock-jul2026")
            lines = (output_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()

        parsed = [json.loads(line) for line in lines]
        self.assertEqual(proceed["multi_leg_decision"].verdict, "PROCEED")
        self.assertEqual(decline["multi_leg_decision"].verdict, "DECLINE")
        self.assertTrue(any(record.get("verdict") == "PROCEED" for record in parsed))
        self.assertTrue(any(record.get("verdict") == "DECLINE" for record in parsed))
        self.assertTrue(any(record.get("event") == "simulated_fill_recorded" for record in parsed))

    def test_optional_alpaca_path_remains_guarded(self) -> None:
        session = FakeSession()
        with tempfile.TemporaryDirectory() as temp_dir, self.assertRaises(AlpacaPaperError):
            paper_trader.run_paper_trader(
                thesis_id="labor-resilience-jul2026",
                replay_path=REPLAY_PATH,
                theses_path=THESES_PATH,
                output_dir=Path(temp_dir),
                broker_name="alpaca",
                submit_paper_order=True,
                config=AlpacaPaperConfig(
                    api_key="paper_key",
                    api_secret="paper_secret",
                    base_url=PAPER_BASE_URL,
                    paper_trade="true",
                ),
                session=session,
                confirm_paper_trading=True,
                confirm_not_financial_advice=False,
                confirm_human_approval=True,
                base_dir=BASE_DIR,
            )

        self.assertEqual(session.calls, [])

    def test_alpaca_broker_requires_explicit_submit_flag(self) -> None:
        session = FakeSession()
        with tempfile.TemporaryDirectory() as temp_dir, self.assertRaises(AlpacaPaperError):
            paper_trader.run_paper_trader(
                thesis_id="labor-resilience-jul2026",
                replay_path=REPLAY_PATH,
                theses_path=THESES_PATH,
                output_dir=Path(temp_dir),
                broker_name="alpaca",
                session=session,
                base_dir=BASE_DIR,
            )

        self.assertEqual(session.calls, [])

    def test_no_unguarded_order_submission_helper_in_public_runner(self) -> None:
        source = (BASE_DIR / "tier3_paper_trader.py").read_text(encoding="utf-8")
        self.assertNotIn("submit_order", source)
        self.assertNotIn("place_order", source)
        self.assertNotIn("create_order", source)
        self.assertNotIn("https://api.alpaca.markets", source)

    def test_sample_simbroker_assets_are_valid_and_sanitized(self) -> None:
        asset_names = (
            "sample-simbroker-paper-preview.json",
            "sample-simbroker-order-result.json",
        )
        for name in asset_names:
            with self.subTest(name=name):
                text = (BASE_DIR / "assets" / name).read_text(encoding="utf-8")
                json.loads(text)
                self.assertNotIn("/Users/", text)
                self.assertNotIn("APCA_API_SECRET", text)

        for name in ("sample-paper-portfolio.jsonl", "sample-decisions.jsonl"):
            text = (BASE_DIR / "assets" / name).read_text(encoding="utf-8")
            self.assertTrue(text.strip())
            for line in text.splitlines():
                json.loads(line)
            self.assertNotIn("/Users/", text)
            self.assertNotIn("APCA_API_SECRET", text)


if __name__ == "__main__":
    unittest.main()
