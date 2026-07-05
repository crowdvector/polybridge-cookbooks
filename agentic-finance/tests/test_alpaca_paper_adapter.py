from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentic_finance.brokers.alpaca import (
    PAPER_BASE_URL,
    AlpacaPaperClient,
    AlpacaPaperConfig,
    AlpacaPaperError,
    create_paper_order_preview,
    read_alpaca_paper_config_from_env,
    validate_alpaca_paper_config,
)
from agentic_finance.evidence import load_offline_evidence
from agentic_finance.gate import apply_gate
from run_alpaca_paper_check import run_preview_only


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BASE_DIR.parent


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None) -> None:
        self.status_code = status_code
        self.payload = payload or {
            "id": "fake_account_id_123",
            "status": "ACTIVE",
            "trading_blocked": False,
            "transfers_blocked": False,
            "buying_power": "123456.78",
        }

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, response: FakeResponse | None = None, error: Exception | None = None) -> None:
        self.response = response or FakeResponse()
        self.error = error
        self.calls: list[dict] = []

    def get(self, url: str, headers: dict, timeout: int) -> FakeResponse:
        self.calls.append({"method": "GET", "url": url, "headers": headers, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response

    def post(self, *args, **kwargs) -> None:
        raise AssertionError("Paper validation must not use POST.")


class AlpacaPaperAdapterTests(unittest.TestCase):
    def test_preview_only_path_requires_no_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            result = run_preview_only(base_dir=BASE_DIR, output_dir=Path(temp_dir))
            paths = result["paths"]

            self.assertIn("paper_preview", paths)
            self.assertTrue(paths["paper_preview"].exists())
            self.assertNotIn("paper_account_check", paths)

    def test_paper_config_reads_apca_env_vars(self) -> None:
        env = {
            "APCA_API_KEY_ID": "paper_key_id",
            "APCA_API_SECRET_KEY": "paper_secret",
            "APCA_API_BASE_URL": PAPER_BASE_URL,
        }

        config = read_alpaca_paper_config_from_env(env)

        self.assertEqual(config.api_key, "paper_key_id")
        self.assertEqual(config.api_secret, "paper_secret")
        self.assertEqual(config.base_url, PAPER_BASE_URL)

    def test_paper_config_reads_alpaca_aliases(self) -> None:
        env = {
            "ALPACA_API_KEY": "alias_key",
            "ALPACA_SECRET_KEY": "alias_secret",
            "ALPACA_PAPER_TRADE": "true",
        }

        config = read_alpaca_paper_config_from_env(env)

        self.assertEqual(config.api_key, "alias_key")
        self.assertEqual(config.api_secret, "alias_secret")
        self.assertEqual(config.paper_trade, "true")

    def test_missing_credentials_fail_clearly(self) -> None:
        with self.assertRaises(AlpacaPaperError) as context:
            validate_alpaca_paper_config(AlpacaPaperConfig(api_key=None, api_secret=None))

        self.assertIn("requires", str(context.exception))

    def test_false_paper_trade_flag_blocks(self) -> None:
        config = AlpacaPaperConfig(api_key="key", api_secret="secret", paper_trade="false")

        with self.assertRaises(AlpacaPaperError):
            validate_alpaca_paper_config(config)

    def test_live_looking_base_url_blocks(self) -> None:
        config = AlpacaPaperConfig(api_key="key", api_secret="secret", base_url="https://api.alpaca.markets")

        with self.assertRaises(AlpacaPaperError):
            validate_alpaca_paper_config(config)

    def test_non_https_paper_url_blocks(self) -> None:
        config = AlpacaPaperConfig(api_key="key", api_secret="secret", base_url="http://paper-api.alpaca.markets")

        with self.assertRaises(AlpacaPaperError):
            validate_alpaca_paper_config(config)

    def test_paper_base_url_passes_validation(self) -> None:
        config = validate_alpaca_paper_config(
            AlpacaPaperConfig(api_key="key", api_secret="secret", base_url=PAPER_BASE_URL)
        )

        self.assertEqual(config.base_url, PAPER_BASE_URL)

    def test_get_account_metadata_uses_get_account_only(self) -> None:
        session = FakeSession()
        client = AlpacaPaperClient(
            AlpacaPaperConfig(api_key="key", api_secret="secret"),
            session=session,
        )

        metadata = client.get_account_metadata()

        self.assertEqual(len(session.calls), 1)
        self.assertEqual(session.calls[0]["method"], "GET")
        self.assertEqual(session.calls[0]["url"], f"{PAPER_BASE_URL}/v2/account")
        self.assertIn("APCA-API-KEY-ID", session.calls[0]["headers"])
        self.assertEqual(metadata["schema_version"], "alpaca_paper_account_check.v1")
        self.assertEqual(metadata["account_id"], "[REDACTED]")
        self.assertEqual(metadata["buying_power"], "[REDACTED]")
        self.assertTrue(metadata["no_order_submission"])

    def test_no_order_submission_path_exists_in_adapter_or_runner(self) -> None:
        files = [
            BASE_DIR / "agentic_finance" / "brokers" / "alpaca.py",
            BASE_DIR / "run_alpaca_paper_check.py",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in files)
        forbidden = (
            "POST" + " " + "/v2/" + "orders",
            "submit_" + "order",
            "place_" + "order",
            "create_" + "order",
        )

        for term in forbidden:
            self.assertNotIn(term, source)

    def test_headers_are_not_exposed_in_redacted_errors(self) -> None:
        session = FakeSession(
            error=RuntimeError("APCA-API-KEY-ID=paper_key APCA-API-SECRET-KEY=paper_secret")
        )
        client = AlpacaPaperClient(
            AlpacaPaperConfig(api_key="paper_key", api_secret="paper_secret"),
            session=session,
        )

        with self.assertRaises(AlpacaPaperError) as context:
            client.get_account_metadata()

        message = str(context.exception)
        self.assertNotIn("paper_key", message)
        self.assertNotIn("paper_secret", message)
        self.assertNotIn("APCA-API-KEY-ID", message)
        self.assertNotIn("APCA-API-SECRET-KEY", message)

    def test_order_payload_builder_does_not_submit(self) -> None:
        intent, packet = load_offline_evidence(BASE_DIR / "fixtures")
        preview = create_paper_order_preview(intent, apply_gate(packet))
        client = AlpacaPaperClient(
            AlpacaPaperConfig(api_key="key", api_secret="secret"),
            session=FakeSession(),
        )

        payload = client.build_order_payload(preview)

        self.assertEqual(payload["symbol"], preview.symbol)
        self.assertEqual(payload["side"], preview.side)
        self.assertEqual(payload["notional"], f"{preview.notional_usd:.2f}")
        self.assertTrue(payload["preview_only"])
        self.assertFalse(payload["submit_supported"])

    def test_sample_account_check_asset_is_valid_and_sanitized(self) -> None:
        path = BASE_DIR / "assets" / "sample-alpaca-paper-account-check.json"
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)

        self.assertEqual(data["schema_version"], "alpaca_paper_account_check.v1")
        self.assertEqual(data["broker"], "alpaca")
        self.assertEqual(data["mode"], "paper_account_validation")
        self.assertTrue(data["paper_endpoint_validated"])
        self.assertTrue(data["no_order_submission"])
        self.assertEqual(data["account_id"], "sample_redacted")
        self.assertEqual(data["buying_power"], "sample_redacted")
        self.assertNotIn("APCA_API_SECRET", text)
        self.assertNotIn("/Users/", text)


if __name__ == "__main__":
    unittest.main()
