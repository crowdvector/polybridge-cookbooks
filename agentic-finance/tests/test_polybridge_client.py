from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentic_finance.polybridge import FORECAST_ENDPOINT, PolyBridgeAuthError, PolyBridgeClient, PolyBridgeError


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, headers: dict | None = None) -> None:
        self.status_code = status_code
        self.payload = payload or {"status": "ok", "probability": 0.5}
        self.headers = headers or {}

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse] | None = None, error: Exception | None = None) -> None:
        self.responses = list(responses or [])
        self.error = error
        self.calls: list[dict] = []

    def post(self, endpoint: str, headers: dict, json: dict, timeout: int) -> FakeResponse:
        self.calls.append({"endpoint": endpoint, "headers": headers, "json": json, "timeout": timeout})
        if self.error:
            raise self.error
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(200)


class PolyBridgeClientTests(unittest.TestCase):
    def test_no_authorization_header_when_api_key_unset(self) -> None:
        session = FakeSession([FakeResponse(200)])

        with patch.dict(os.environ, {}, clear=True):
            client = PolyBridgeClient(session=session, sleep=lambda _: None)
            client.forecast("Will the fixture pass?")

        self.assertEqual(session.calls[0]["endpoint"], FORECAST_ENDPOINT)
        self.assertNotIn("Authorization", session.calls[0]["headers"])

    def test_authorization_header_present_when_api_key_set(self) -> None:
        session = FakeSession([FakeResponse(200)])

        with patch.dict(os.environ, {"POLYBRIDGE_API_KEY": "pb_test_secret_1234567890"}, clear=True):
            client = PolyBridgeClient(session=session, sleep=lambda _: None)
            client.forecast("Will the fixture pass?")

        self.assertEqual(session.calls[0]["headers"]["Authorization"], "Bearer pb_test_secret_1234567890")

    def test_auth_failure_with_key_does_not_retry_anonymous(self) -> None:
        for status_code in (401, 403):
            with self.subTest(status_code=status_code):
                session = FakeSession([FakeResponse(status_code)])

                with patch.dict(os.environ, {"POLYBRIDGE_API_KEY": "pb_test_secret_1234567890"}, clear=True):
                    client = PolyBridgeClient(session=session, sleep=lambda _: None)
                    with self.assertRaises(PolyBridgeAuthError):
                        client.forecast("Will auth fail?")

                self.assertEqual(len(session.calls), 1)
                self.assertIn("Authorization", session.calls[0]["headers"])

    def test_retry_on_429_and_503(self) -> None:
        session = FakeSession(
            [
                FakeResponse(429, headers={"Retry-After": "0"}),
                FakeResponse(503),
                FakeResponse(200, payload={"status": "ok", "probability": 0.62}),
            ]
        )
        sleeps: list[float] = []
        client = PolyBridgeClient(session=session, sleep=sleeps.append)

        payload = client.forecast("Will retry succeed?")

        self.assertEqual(payload["probability"], 0.62)
        self.assertEqual(len(session.calls), 3)
        self.assertEqual(sleeps[0], 0.0)

    def test_redacted_errors_do_not_leak_authorization_or_tokens(self) -> None:
        session = FakeSession(error=RuntimeError("Authorization: Bearer pb_test_secret_1234567890"))
        client = PolyBridgeClient(session=session, max_retries=0, sleep=lambda _: None)

        with self.assertRaises(PolyBridgeError) as context:
            client.forecast("Will the error be redacted?")

        message = str(context.exception)
        self.assertNotIn("pb_test_secret_1234567890", message)
        self.assertNotIn("Authorization: Bearer", message)
        self.assertIn("[REDACTED]", message)


if __name__ == "__main__":
    unittest.main()
