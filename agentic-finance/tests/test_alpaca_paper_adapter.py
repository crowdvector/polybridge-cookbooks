from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_alpaca_paper_check as paper_runner
from agentic_finance.brokers.alpaca import (
    PAPER_BASE_URL,
    AlpacaPaperClient,
    AlpacaPaperConfig,
    AlpacaPaperError,
    create_paper_order_preview,
    read_alpaca_paper_config_from_env,
    submit_paper_order,
    validate_alpaca_paper_config,
)
from agentic_finance.evidence import load_offline_evidence
from agentic_finance.gate import apply_gate
from agentic_finance.models import GateDecision, PaperOrderPreview
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
    def __init__(
        self,
        response: FakeResponse | None = None,
        error: Exception | None = None,
        post_response: FakeResponse | None = None,
        post_error: Exception | None = None,
    ) -> None:
        self.response = response or FakeResponse()
        self.error = error
        self.post_response = post_response or FakeResponse(
            status_code=201,
            payload={
                "id": "fake_paper_order_id_123",
                "client_order_id": "fake_client_order_id_456",
                "status": "accepted",
            },
        )
        self.post_error = post_error
        self.calls: list[dict] = []

    def get(self, url: str, headers: dict, timeout: int) -> FakeResponse:
        self.calls.append({"method": "GET", "url": url, "headers": headers, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response

    def post(self, url: str, headers: dict, json: dict, timeout: int) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, "headers": headers, "json": json, "timeout": timeout})
        if self.post_error:
            raise self.post_error
        return self.post_response


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

    def paper_config(self, **overrides) -> AlpacaPaperConfig:
        values = {
            "api_key": "paper_key",
            "api_secret": "paper_secret",
            "base_url": PAPER_BASE_URL,
            "paper_trade": "true",
        }
        values.update(overrides)
        return AlpacaPaperConfig(**values)

    def paper_preview(self, **overrides) -> PaperOrderPreview:
        intent, packet = load_offline_evidence(BASE_DIR / "fixtures")
        preview = create_paper_order_preview(intent, apply_gate(packet))
        values = {
            "symbol": preview.symbol,
            "side": preview.side,
            "notional_usd": preview.notional_usd,
            "created_at": preview.created_at,
            "broker": preview.broker,
            "mode": preview.mode,
            "human_approval_required": preview.human_approval_required,
            "submit_supported": preview.submit_supported,
            "schema_version": preview.schema_version,
            "allowed_use": preview.allowed_use,
        }
        values.update(overrides)
        return PaperOrderPreview(**values)

    def cleared_gate_decision(self) -> GateDecision:
        _intent, packet = load_offline_evidence(BASE_DIR / "fixtures")
        return apply_gate(packet)

    def test_no_unguarded_submission_names_exist_in_adapter_or_runner(self) -> None:
        files = [
            BASE_DIR / "agentic_finance" / "brokers" / "alpaca.py",
            BASE_DIR / "run_alpaca_paper_check.py",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in files)
        forbidden = (
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

    def test_submit_path_fails_if_any_confirmation_flag_is_missing(self) -> None:
        flag_sets = [
            {"confirm_paper_trading": False, "confirm_not_financial_advice": True, "confirm_human_approval": True},
            {"confirm_paper_trading": True, "confirm_not_financial_advice": False, "confirm_human_approval": True},
            {"confirm_paper_trading": True, "confirm_not_financial_advice": True, "confirm_human_approval": False},
        ]

        for flags in flag_sets:
            with self.subTest(flags=flags):
                session = FakeSession()
                with self.assertRaises(AlpacaPaperError):
                    submit_paper_order(
                        self.paper_preview(),
                        self.paper_config(),
                        gate_decision=self.cleared_gate_decision(),
                        session=session,
                        **flags,
                    )
                self.assertEqual(session.calls, [])

    def test_submit_path_fails_if_paper_trade_flag_is_false(self) -> None:
        session = FakeSession()

        with self.assertRaises(AlpacaPaperError):
            submit_paper_order(
                self.paper_preview(),
                self.paper_config(paper_trade="false"),
                gate_decision=self.cleared_gate_decision(),
                confirm_paper_trading=True,
                confirm_not_financial_advice=True,
                confirm_human_approval=True,
                session=session,
            )

        self.assertEqual(session.calls, [])

    def test_submit_path_fails_if_base_url_is_not_exact_paper_endpoint(self) -> None:
        session = FakeSession()

        with self.assertRaises(AlpacaPaperError):
            submit_paper_order(
                self.paper_preview(),
                self.paper_config(base_url="https://paper-api.alpaca.markets.example.invalid"),
                gate_decision=self.cleared_gate_decision(),
                confirm_paper_trading=True,
                confirm_not_financial_advice=True,
                confirm_human_approval=True,
                session=session,
            )

        self.assertEqual(session.calls, [])

    def test_submit_path_fails_if_symbol_not_allowlisted(self) -> None:
        session = FakeSession()

        with self.assertRaises(AlpacaPaperError):
            submit_paper_order(
                self.paper_preview(symbol="TSLA"),
                self.paper_config(),
                gate_decision=self.cleared_gate_decision(),
                confirm_paper_trading=True,
                confirm_not_financial_advice=True,
                confirm_human_approval=True,
                session=session,
            )

        self.assertEqual(session.calls, [])

    def test_submit_path_fails_if_notional_exceeds_cap(self) -> None:
        session = FakeSession()

        with self.assertRaises(AlpacaPaperError):
            submit_paper_order(
                self.paper_preview(notional_usd=1000.01),
                self.paper_config(),
                gate_decision=self.cleared_gate_decision(),
                confirm_paper_trading=True,
                confirm_not_financial_advice=True,
                confirm_human_approval=True,
                session=session,
            )

        self.assertEqual(session.calls, [])

    def test_submit_path_fails_if_gate_did_not_clear(self) -> None:
        blocked_decision = GateDecision(
            decision="blocked_weak_evidence",
            cleared_for_paper_preview=False,
            reasons=("Synthetic blocked decision for test.",),
            next_step="Memo only.",
            config_snapshot={},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                paper_runner,
                "run_offline_workflow",
                return_value={"gate_decision": blocked_decision, "paper_preview": None},
            ):
                with self.assertRaises(AlpacaPaperError):
                    paper_runner.run_submit_paper_order(
                        base_dir=BASE_DIR,
                        output_dir=Path(temp_dir),
                        config=self.paper_config(),
                        session=FakeSession(),
                        confirm_paper_trading=True,
                        confirm_not_financial_advice=True,
                        confirm_human_approval=True,
                    )

    def test_submit_path_posts_orders_endpoint_only_after_checks_pass(self) -> None:
        session = FakeSession()

        result = submit_paper_order(
            self.paper_preview(),
            self.paper_config(),
            gate_decision=self.cleared_gate_decision(),
            confirm_paper_trading=True,
            confirm_not_financial_advice=True,
            confirm_human_approval=True,
            session=session,
        )

        self.assertEqual(len(session.calls), 1)
        call = session.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], f"{PAPER_BASE_URL}/v2/orders")
        self.assertEqual(
            call["json"],
            {
                "symbol": "AAPL",
                "side": "buy",
                "type": "market",
                "time_in_force": "day",
                "notional": "1000.00",
            },
        )
        self.assertEqual(result["schema_version"], "alpaca_paper_submission_result.v1")
        self.assertEqual(result["mode"], "paper_submission_result")
        self.assertEqual(result["status"], "accepted")

    def test_fake_successful_paper_response_is_sanitized(self) -> None:
        session = FakeSession()

        result = submit_paper_order(
            self.paper_preview(),
            self.paper_config(),
            gate_decision=self.cleared_gate_decision(),
            confirm_paper_trading=True,
            confirm_not_financial_advice=True,
            confirm_human_approval=True,
            session=session,
        )
        text = json.dumps(result, sort_keys=True)

        self.assertEqual(result["order_id"], "[REDACTED]")
        self.assertEqual(result["client_order_id"], "[REDACTED]")
        self.assertNotIn("fake_paper_order_id_123", text)
        self.assertNotIn("paper_secret", text)
        self.assertTrue(result["no_live_trading"])
        self.assertTrue(result["human_approval_confirmed"])

    def test_submit_error_does_not_leak_headers_or_secrets(self) -> None:
        session = FakeSession(
            post_error=RuntimeError("APCA-API-KEY-ID=paper_key APCA-API-SECRET-KEY=paper_secret")
        )

        with self.assertRaises(AlpacaPaperError) as context:
            submit_paper_order(
                self.paper_preview(),
                self.paper_config(),
                gate_decision=self.cleared_gate_decision(),
                confirm_paper_trading=True,
                confirm_not_financial_advice=True,
                confirm_human_approval=True,
                session=session,
            )

        message = str(context.exception)
        self.assertNotIn("paper_key", message)
        self.assertNotIn("paper_secret", message)
        self.assertNotIn("APCA-API-KEY-ID", message)
        self.assertNotIn("APCA-API-SECRET-KEY", message)

    def test_no_live_endpoint_can_be_used_for_submit_path(self) -> None:
        session = FakeSession()

        with self.assertRaises(AlpacaPaperError):
            submit_paper_order(
                self.paper_preview(),
                self.paper_config(base_url="https://api.alpaca.markets"),
                gate_decision=self.cleared_gate_decision(),
                confirm_paper_trading=True,
                confirm_not_financial_advice=True,
                confirm_human_approval=True,
                session=session,
            )

        self.assertEqual(session.calls, [])

    def test_runner_writes_sanitized_submission_result_and_audit_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = paper_runner.run_submit_paper_order(
                base_dir=BASE_DIR,
                output_dir=Path(temp_dir),
                config=self.paper_config(),
                session=FakeSession(),
                confirm_paper_trading=True,
                confirm_not_financial_advice=True,
                confirm_human_approval=True,
            )

            result_path = result["paths"]["paper_submission_result"]
            audit_path = result["paths"]["audit_log"]
            result_text = result_path.read_text(encoding="utf-8")
            audit_lines = audit_path.read_text(encoding="utf-8").splitlines()
            submission = json.loads(result_text)
            audit_record = json.loads(audit_lines[-1])

        self.assertEqual(submission["schema_version"], "alpaca_paper_submission_result.v1")
        self.assertEqual(submission["order_id"], "[REDACTED]")
        self.assertEqual(audit_record["tier"], "alpaca_paper_submission")
        self.assertTrue(audit_record["paper_only"])
        self.assertTrue(audit_record["human_approval_confirmed"])
        self.assertTrue(audit_record["no_live_trading"])
        self.assertEqual(audit_record["order_result_path"], "external-output/alpaca-paper-submission-result.json")
        self.assertNotIn("fake_paper_order_id_123", result_text)

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

    def test_sample_paper_submission_result_asset_is_valid_and_sanitized(self) -> None:
        path = BASE_DIR / "assets" / "sample-alpaca-paper-submission-result.json"
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)

        self.assertEqual(data["schema_version"], "alpaca_paper_submission_result.v1")
        self.assertEqual(data["broker"], "alpaca")
        self.assertEqual(data["mode"], "paper_submission_result")
        self.assertTrue(data["submitted"])
        self.assertTrue(data["paper_endpoint_validated"])
        self.assertTrue(data["no_live_trading"])
        self.assertTrue(data["human_approval_confirmed"])
        self.assertEqual(data["order_id"], "sample_redacted")
        self.assertEqual(data["client_order_id"], "sample_redacted")
        self.assertNotIn("APCA_API_SECRET", text)
        self.assertNotIn("/Users/", text)


if __name__ == "__main__":
    unittest.main()
