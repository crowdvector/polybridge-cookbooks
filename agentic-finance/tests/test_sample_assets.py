from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
SECRET_PATTERN = re.compile(
    r"Bearer\s+|sk-|ALPACA_SECRET|POLYBRIDGE_API_KEY=.*[A-Za-z0-9]|APCA_API_SECRET|Authorization",
    re.IGNORECASE,
)


class SampleAssetTests(unittest.TestCase):
    def test_sample_audit_log_is_valid_jsonl(self) -> None:
        lines = (BASE_DIR / "assets" / "sample-audit-log.jsonl").read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["schema_version"], "multi_leg_decision_audit_record.v1")
        self.assertEqual(record["tier"], "multi_leg_evidence_gate")
        self.assertTrue(record["guardrails"]["paper_preview_requires_gate_proceed"])

    def test_sample_audit_log_has_no_absolute_local_paths(self) -> None:
        text = (BASE_DIR / "assets" / "sample-audit-log.jsonl").read_text(encoding="utf-8")
        record = json.loads(text)

        for path in record["output_paths"].values():
            self.assertFalse(path.startswith("/"))
        self.assertNotIn("/Users/", text)
        self.assertNotIn("/home/", text)
        self.assertNotRegex(text, r"[A-Za-z]:\\\\")

    def test_sample_audit_log_has_no_obvious_secrets(self) -> None:
        text = (BASE_DIR / "assets" / "sample-audit-log.jsonl").read_text(encoding="utf-8")

        self.assertIsNone(SECRET_PATTERN.search(text))

    def test_sample_portfolio_risk_map_is_valid_json(self) -> None:
        asset_name = "sample-portfolio-" + "risk" + "-map.json"
        text = (BASE_DIR / "assets" / asset_name).read_text(encoding="utf-8")
        record = json.loads(text)

        self.assertEqual(record["schema_version"], "portfolio_risk_map.v1")
        self.assertEqual(record["tier"], "portfolio_event_risk_map")
        self.assertEqual(record["methodology"]["probability_source"], "forecast_only")
        self.assertEqual(record["methodology"]["search_relevance_use"], "metadata_only")
        self.assertTrue(record["guardrails"]["no_broker_submission"])
        self.assertIsNone(SECRET_PATTERN.search(text))
        self.assertNotIn("/Users/", text)
        self.assertNotIn("/home/", text)

    def test_sample_portfolio_memo_has_no_action_language(self) -> None:
        asset_name = "sample-portfolio-" + "risk" + "-memo.md"
        text = (BASE_DIR / "assets" / asset_name).read_text(encoding="utf-8")
        banned = re.compile(r"\b(buy|sell|recommend(?:ed|s|ation)?|financial advice)\b", re.IGNORECASE)

        self.assertIn("read-only memo", text)
        self.assertIn("does not place orders", text)
        self.assertIsNone(banned.search(text))
        self.assertIsNone(SECRET_PATTERN.search(text))


if __name__ == "__main__":
    unittest.main()
