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
        self.assertEqual(record["schema_version"], "audit_record.v1")
        self.assertEqual(record["guardrails"]["paper_preview_only"], True)

    def test_sample_audit_log_has_no_absolute_local_paths(self) -> None:
        text = (BASE_DIR / "assets" / "sample-audit-log.jsonl").read_text(encoding="utf-8")
        record = json.loads(text)

        self.assertFalse(record["memo_path"].startswith("/"))
        self.assertFalse(record["paper_preview_path"].startswith("/"))
        self.assertNotIn("/Users/", text)
        self.assertNotIn("/home/", text)
        self.assertNotRegex(text, r"[A-Za-z]:\\\\")

    def test_sample_audit_log_has_no_obvious_secrets(self) -> None:
        text = (BASE_DIR / "assets" / "sample-audit-log.jsonl").read_text(encoding="utf-8")

        self.assertIsNone(SECRET_PATTERN.search(text))


if __name__ == "__main__":
    unittest.main()
