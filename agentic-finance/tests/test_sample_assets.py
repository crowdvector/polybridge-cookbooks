from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
SECRET_PATTERN = re.compile(r"Bearer\s+|sk-|POLYBRIDGE_API_KEY=.*[A-Za-z0-9]|Authorization", re.IGNORECASE)


class SampleAssetTests(unittest.TestCase):
    def test_sample_labor_assets_are_valid_and_sanitized(self) -> None:
        json_assets = (
            "sample-labor-resilience-paper-preview.json",
            "sample-simbroker-paper-preview.json",
            "sample-simbroker-order-result.json",
        )
        for name in json_assets:
            with self.subTest(name=name):
                text = (BASE_DIR / "assets" / name).read_text(encoding="utf-8")
                json.loads(text)
                self.assertIsNone(SECRET_PATTERN.search(text))
                self.assertNotIn("/Users/", text)
                self.assertNotIn("/home/", text)

    def test_sample_jsonl_assets_are_valid_and_sanitized(self) -> None:
        for name in ("sample-labor-resilience-audit-log.jsonl", "sample-decisions.jsonl", "sample-paper-portfolio.jsonl"):
            with self.subTest(name=name):
                text = (BASE_DIR / "assets" / name).read_text(encoding="utf-8")
                self.assertTrue(text.strip())
                for line in text.splitlines():
                    json.loads(line)
                self.assertIsNone(SECRET_PATTERN.search(text))
                self.assertNotIn("/Users/", text)
                self.assertNotIn("/home/", text)

    def test_sample_memo_is_not_financial_advice(self) -> None:
        text = (BASE_DIR / "assets" / "sample-labor-resilience-decision-memo.md").read_text(encoding="utf-8")

        self.assertIn("not financial advice", text.lower())
        self.assertIn("PROCEED", text)
        self.assertIsNone(SECRET_PATTERN.search(text))

    def test_removed_launch_terms_are_absent_from_source(self) -> None:
        banned = (
            "al" + "paca",
            "AP" + "CA_",
            "AL" + "PACA_",
            "api." + "al" + "paca.markets",
            "AA" + "PL",
            "aa" + "pl",
            "portfolio " + "risk",
            "oil-" + "shock",
            "rates-" + "fall",
            "X" + "LE",
            "T" + "LT",
            "run_" + "portfolio_" + "risk_map",
            "tier3_" + "al" + "paca",
            "run_" + "al" + "paca",
        )
        paths = [
            path
            for path in BASE_DIR.rglob("*")
            if path.is_file()
            and "outputs" not in path.parts
            and "__pycache__" not in path.parts
            and "dist" not in path.parts
            and path.suffix not in {".pyc", ".ipynb"}
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for term in banned:
                self.assertNotIn(term, text, f"{term!r} found in {path}")


if __name__ == "__main__":
    unittest.main()
