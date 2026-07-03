from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentic_finance.redaction import REDACTED, redact, redact_string


class RedactionTests(unittest.TestCase):
    def test_redacts_bearer_tokens_and_env_secrets(self) -> None:
        text = (
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789 "
            "POLYBRIDGE_API_KEY=pb_live_abcdefghijklmnopqrstuvwxyz "
            "ALPACA_SECRET_KEY=alpaca_secret_abcdefghijklmnopqrstuvwxyz"
        )

        redacted = redact_string(text)

        self.assertNotIn("abcdefghijklmnopqrstuvwxyz0123456789", redacted)
        self.assertNotIn("pb_live_abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertNotIn("alpaca_secret_abcdefghijklmnopqrstuvwxyz", redacted)
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
            "ALPACA_API_KEY": "AKIA1234567890SECRET",
            "raw_response_sha256": "0" * 64,
        }

        redacted = redact(payload)

        self.assertEqual(redacted["Authorization"], REDACTED)
        self.assertEqual(redacted["ALPACA_API_KEY"], REDACTED)
        self.assertEqual(redacted["raw_response_sha256"], "0" * 64)


if __name__ == "__main__":
    unittest.main()
