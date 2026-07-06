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


BASE_DIR = Path(__file__).resolve().parents[1]
THESES_PATH = BASE_DIR / "examples" / "sample_theses.json"
REPLAY_PATH = BASE_DIR / "examples" / "recorded_run_2026-07-04.json"


def write_synthetic_decline(temp_dir: Path) -> tuple[Path, Path]:
    theses = {
        "thesis_id": "synthetic-weak-labor",
        "as_of": "2026-07-04",
        "demo": True,
        "evergreen": True,
        "thesis": "Synthetic weak labor thesis",
        "instrument": "SPY",
        "direction": "long",
        "notional_usd": 1000,
        "questions": [
            {"q": "Will synthetic jobs remain strong?", "supports_when": "YES", "threshold": 0.7},
            {"q": "Will synthetic unemployment stay contained?", "supports_when": "YES", "threshold": 0.7},
            {"q": "Will synthetic policy stay steady?", "supports_when": "YES", "threshold": 0.7},
        ],
    }
    replay = {
        "theses": {
            "synthetic-weak-labor": {
                "legs": [
                    {"probability": 0.2, "interval": [0.18, 0.25], "evidence_profile": "direct_only"},
                    {"probability": 0.45, "interval": [0.4, 0.5], "evidence_profile": "direct_only"},
                    {"probability": 0.8, "interval": [0.75, 0.85], "evidence_profile": "proxy_only"},
                ]
            }
        }
    }
    thesis_path = temp_dir / "synthetic_thesis.json"
    replay_path = temp_dir / "synthetic_replay.json"
    thesis_path.write_text(json.dumps(theses), encoding="utf-8")
    replay_path.write_text(json.dumps(replay), encoding="utf-8")
    return thesis_path, replay_path


class SimBrokerPaperTraderTests(unittest.TestCase):
    def run_default(self, output_dir: Path, confirmation: str = "y") -> dict:
        return paper_trader.run_paper_trader(
            thesis_id="labor-resilience-jul2026",
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
        self.assertTrue(result["broker_result"]["no_real_trading"])

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
        self.assertEqual(record["notional_usd"], 1000.0)
        self.assertTrue(record["order_id"].startswith("sim_"))
        self.assertTrue(record["simulated"])
        self.assertTrue(record["no_real_trading"])

    def test_human_decline_records_decline_and_no_simulated_fill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_default(Path(temp_dir), confirmation="n")
            output_dir = Path(temp_dir)
            decisions = output_dir / "decisions.jsonl"
            portfolio = output_dir / "paper_portfolio.jsonl"
            decision_lines = decisions.read_text(encoding="utf-8").splitlines()

        self.assertEqual(result["broker_event"], "human_declined")
        self.assertFalse(portfolio.exists())
        self.assertTrue(any(json.loads(line).get("human_decision") == "human_declined" for line in decision_lines))

    def test_synthetic_decline_does_not_call_broker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            thesis_path, replay_path = write_synthetic_decline(temp_path)
            result = paper_trader.run_paper_trader(
                thesis_id="synthetic-weak-labor",
                replay_path=replay_path,
                theses_path=thesis_path,
                output_dir=temp_path / "outputs",
                confirmation="y",
                base_dir=BASE_DIR,
            )

            self.assertEqual(result["broker_event"], "skipped_decline")
            self.assertFalse((temp_path / "outputs" / "paper_portfolio.jsonl").exists())
            self.assertFalse((temp_path / "outputs" / "paper-order-preview.json").exists())

    def test_paper_portfolio_jsonl_is_sanitized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.run_default(Path(temp_dir), confirmation="y")
            text = result["paths"]["paper_portfolio"].read_text(encoding="utf-8")

        self.assertNotIn("/Users/", text)
        self.assertNotIn("/home/", text)
        self.assertNotIn("account_id", text)

    def test_decisions_jsonl_includes_expected_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            proceed = self.run_default(output_dir, confirmation="y")
            lines = (output_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()

        parsed = [json.loads(line) for line in lines]
        self.assertEqual(proceed["multi_leg_decision"].verdict, "PROCEED")
        broker_records = [record for record in parsed if record.get("schema_version") == "sim_broker_audit_record.v1"]
        self.assertEqual(len(broker_records), 1)
        record = broker_records[0]
        self.assertEqual(record["verdict"], "PROCEED")
        self.assertEqual(record["human_decision"], "approved")
        self.assertTrue(record["order_id"].startswith("sim_"))
        self.assertIn("leg_summaries", record)
        self.assertIn("paths", record)

    def test_public_runner_has_no_real_broker_option(self) -> None:
        source = (BASE_DIR / "tier3_paper_trader.py").read_text(encoding="utf-8")
        self.assertNotIn("--broker", source)
        self.assertNotIn("place_" + "order", source)
        self.assertNotIn("create_" + "order", source)


if __name__ == "__main__":
    unittest.main()
