from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentic_finance.redaction import REDACTED, redact, redact_string


class RedactionTests(unittest.TestCase):
    def test_redacts_bearer_tokens_and_polybridge_env_secret(self) -> None:
        text = (
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789 "
            "POLYBRIDGE_API_KEY=pb_live_abcdefghijklmnopqrstuvwxyz"
        )

        redacted = redact_string(text)

        self.assertNotIn("abcdefghijklmnopqrstuvwxyz0123456789", redacted)
        self.assertNotIn("pb_live_abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertIn(REDACTED, redacted)

    def test_redacts_any_authorization_header_value(self) -> None:
        cases = {
            "Authorization: Bearer abc123": "Authorization: [REDACTED]",
            "Authorization: Basic abc123": "Authorization: [REDACTED]",
            "Authorization: ApiKey abc123": "Authorization: [REDACTED]",
            "authorization: custom-token": "authorization: [REDACTED]",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(redact_string(raw), expected)

    def test_redacts_sensitive_dict_keys_but_keeps_sha256(self) -> None:
        payload = {
            "Authorization": "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
            "POLYBRIDGE_API_KEY": "pb_live_abcdefghijklmnopqrstuvwxyz",
            "raw_response_sha256": "0" * 64,
        }

        redacted = redact(payload)

        self.assertEqual(redacted["Authorization"], REDACTED)
        self.assertEqual(redacted["POLYBRIDGE_API_KEY"], REDACTED)
        self.assertEqual(redacted["raw_response_sha256"], "0" * 64)

    def test_preserves_safe_schema_and_path_metadata(self) -> None:
        payload = {
            "schema_version": "sim_broker_audit_record.v1",
            "tier": "sim_broker_paper_trade",
            "paper_portfolio_path": "outputs/paper_portfolio.jsonl",
            "secret_note": "hidden",
        }

        redacted = redact(payload)

        self.assertEqual(redacted["schema_version"], "sim_broker_audit_record.v1")
        self.assertEqual(redacted["tier"], "sim_broker_paper_trade")
        self.assertEqual(redacted["paper_portfolio_path"], "outputs/paper_portfolio.jsonl")
        self.assertEqual(redacted["secret_note"], REDACTED)


if __name__ == "__main__":
    unittest.main()
