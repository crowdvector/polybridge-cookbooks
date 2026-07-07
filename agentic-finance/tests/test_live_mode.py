from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tier1_evidence_gate as tier1
import tier3_paper_trader as tier3
from agentic_finance.multileg import LIVE_MODE_NOTICE, live_leg_record
from agentic_finance.polybridge import PolyBridgeClient, PolyBridgeError


BASE_DIR = Path(__file__).resolve().parents[1]
THESES_PATH = BASE_DIR / "examples" / "sample_theses.json"
REPLAY_PATH = BASE_DIR / "examples" / "recorded_run_2026-07-04.json"
MISSING_REQUESTS_MESSAGE = "Live mode needs the requests package: run bash setup.sh"


def live_response(probability: float, direct: int = 3, proxy: int = 0) -> dict:
    markets = []
    for index in range(direct):
        markets.append(
            {
                "source": "fake_live_market",
                "question": f"Direct market {index}?",
                "url": "https://example.invalid/markets/direct",
                "probability": probability,
                "relevance": 0.9,
                "is_proxy": False,
            }
        )
    for index in range(proxy):
        markets.append(
            {
                "source": "fake_live_market",
                "question": f"Proxy market {index}?",
                "url": "https://example.invalid/markets/proxy",
                "probability": probability,
                "relevance": 0.6,
                "is_proxy": True,
            }
        )
    return {
        "status": "ok",
        "probability": probability,
        "confidence": 0.8,
        "confidence_interval": {"lower": max(0.0, probability - 0.05), "upper": min(1.0, probability + 0.05)},
        "markets_used": markets,
        "reasoning_summary": "Fake live forecast.",
        "evidence_profile": {"type": "direct_only" if proxy == 0 else "direct_mixed"},
    }


def timeout_error() -> PolyBridgeError:
    return PolyBridgeError("PolyBridge forecast request failed: read timed out")


class FakeClient:
    def __init__(self, script: list) -> None:
        self.script = list(script)
        self.questions: list[str] = []

    def forecast(self, question: str) -> dict:
        self.questions.append(question)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class BoomClient:
    def forecast(self, question: str) -> dict:
        raise AssertionError("live client must not be called when --replay is given")


SUPPORTIVE_LABOR_SCRIPT = [live_response(0.1), live_response(0.2), live_response(0.05)]


class LiveModeRoutingTests(unittest.TestCase):
    def test_tier1_omitting_replay_routes_each_leg_live(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(list(SUPPORTIVE_LABOR_SCRIPT))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = tier1.run_replay(
                    thesis_id="labor-resilience-jul2026",
                    output_dir=tmp,
                    client=client,
                )

            self.assertIn(LIVE_MODE_NOTICE, stdout.getvalue())
            self.assertEqual(client.questions, [leg.question for leg in result["thesis"].questions])
            self.assertEqual(result["multi_leg_decision"].verdict, "PROCEED")
            self.assertEqual(result["audit_record"]["replay_source"], "live_polybridge")
            first_packet = result["multi_leg_decision"].leg_decisions[0].evidence_packet
            self.assertIn("live_polybridge", first_packet.quality_flags)
            self.assertNotIn("recorded_replay", first_packet.quality_flags)

    def test_tier3_omitting_replay_routes_live(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(list(SUPPORTIVE_LABOR_SCRIPT))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = tier3.run_paper_trader(
                    thesis_id="labor-resilience-jul2026",
                    output_dir=tmp,
                    confirmation="n",
                    client=client,
                )

            self.assertIn(LIVE_MODE_NOTICE, stdout.getvalue())
            self.assertEqual(len(client.questions), 3)
            self.assertEqual(result["multi_leg_decision"].verdict, "PROCEED")
            self.assertEqual(result["broker_event"], "human_declined")

    def test_custom_thesis_without_fixtures_runs_live(self) -> None:
        custom_thesis = {
            "thesis_id": "custom-idea",
            "as_of": "2026-07-07",
            "demo": True,
            "evergreen": True,
            "thesis": "Custom idea runs live without recorded data",
            "instrument": "SPY",
            "direction": "long",
            "notional_usd": 1000,
            "questions": [
                {"q": "Will the custom downside event happen?", "supports_when": "NO", "threshold": 0.3},
                {"q": "Will the custom upside event happen?", "supports_when": "YES", "threshold": 0.6},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            theses_path = Path(tmp) / "custom_theses.json"
            theses_path.write_text(json.dumps(custom_thesis), encoding="utf-8")
            client = FakeClient([live_response(0.1), live_response(0.8)])
            with contextlib.redirect_stdout(io.StringIO()):
                result = tier1.run_replay(
                    thesis_id="custom-idea",
                    theses_path=theses_path,
                    output_dir=Path(tmp) / "outputs",
                    client=client,
                )

            self.assertEqual(
                client.questions,
                ["Will the custom downside event happen?", "Will the custom upside event happen?"],
            )
            self.assertEqual(result["multi_leg_decision"].verdict, "PROCEED")
            self.assertEqual(result["multi_leg_decision"].weighted_support, 2.0)

    def test_replay_flag_keeps_recorded_behavior_and_never_calls_client(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                result = tier1.run_replay(
                    thesis_id="labor-resilience-jul2026",
                    replay_path=REPLAY_PATH,
                    output_dir=tmp,
                    client=BoomClient(),
                )

            self.assertNotIn(LIVE_MODE_NOTICE, stdout.getvalue())
            self.assertEqual(result["multi_leg_decision"].verdict, "PROCEED")
            self.assertEqual(result["multi_leg_decision"].weighted_support, 3.0)
            self.assertEqual(result["audit_record"]["replay_source"], "examples/recorded_run_2026-07-04.json")
            self.assertTrue(result["audit_record"]["guardrails"]["offline_replay"])
            first_packet = result["multi_leg_decision"].leg_decisions[0].evidence_packet
            self.assertIn("recorded_replay", first_packet.quality_flags)
            self.assertNotIn("live_polybridge", first_packet.quality_flags)

    def test_missing_replay_entry_still_errors_when_replay_flag_given(self) -> None:
        custom_thesis = {
            "thesis_id": "custom-idea",
            "as_of": "2026-07-07",
            "thesis": "Custom idea",
            "instrument": "SPY",
            "direction": "long",
            "notional_usd": 1000,
            "questions": [{"q": "Q?", "supports_when": "NO", "threshold": 0.3}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            theses_path = Path(tmp) / "custom_theses.json"
            theses_path.write_text(json.dumps(custom_thesis), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                tier1.run_replay(
                    thesis_id="custom-idea",
                    replay_path=REPLAY_PATH,
                    theses_path=theses_path,
                    output_dir=tmp,
                )
            self.assertIn("No recorded replay found", str(ctx.exception))


class LiveModeFailureTests(unittest.TestCase):
    def test_timeout_retries_once_then_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([timeout_error()] + list(SUPPORTIVE_LABOR_SCRIPT))
            with contextlib.redirect_stdout(io.StringIO()):
                result = tier1.run_replay(
                    thesis_id="labor-resilience-jul2026",
                    output_dir=tmp,
                    client=client,
                )

            self.assertEqual(len(client.questions), 4)
            self.assertEqual(client.questions[0], client.questions[1])
            self.assertEqual(result["multi_leg_decision"].verdict, "PROCEED")

    def test_double_timeout_fails_leg_as_insufficient_with_zero_weight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([timeout_error(), timeout_error(), live_response(0.2), live_response(0.05)])
            with contextlib.redirect_stdout(io.StringIO()):
                result = tier1.run_replay(
                    thesis_id="labor-resilience-jul2026",
                    output_dir=tmp,
                    client=client,
                )

            self.assertEqual(len(client.questions), 4)
            failed_leg = result["multi_leg_decision"].leg_decisions[0]
            self.assertEqual(failed_leg.classification, "INSUFFICIENT")
            self.assertEqual(failed_leg.weight, 0.0)
            self.assertEqual(failed_leg.weighted_support, 0.0)
            self.assertTrue(failed_leg.insufficient_data)

    def test_non_timeout_error_fails_leg_without_extra_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient(
                [PolyBridgeError("PolyBridge forecast request failed with HTTP 500.")]
                + [live_response(0.2), live_response(0.05)]
            )
            with contextlib.redirect_stdout(io.StringIO()):
                result = tier1.run_replay(
                    thesis_id="labor-resilience-jul2026",
                    output_dir=tmp,
                    client=client,
                )

            self.assertEqual(len(client.questions), 3)
            self.assertEqual(result["multi_leg_decision"].leg_decisions[0].classification, "INSUFFICIENT")


def flagless_markets(count: int) -> list[dict]:
    return [
        {
            "source": "fake_live_market",
            "question": f"Flagless market {index}?",
            "url": "https://example.invalid/markets/flagless",
            "probability": 0.4,
            "relevance": 0.8,
        }
        for index in range(count)
    ]


class LiveEvidenceProfileTests(unittest.TestCase):
    def test_nested_metadata_profile_string_beats_market_count_fallback(self) -> None:
        response = {
            "status": "ok",
            "probability": 0.4,
            "markets_used": flagless_markets(4),
            "metadata": {
                "oracle_port": {
                    "relevance_filter_summary": {"selected_evidence_profile": "proxy_only"}
                }
            },
        }
        record = live_leg_record("Q?", response)

        self.assertEqual(record["evidence_profile"], "proxy_only")

    def test_nested_metadata_profile_dict_is_accepted(self) -> None:
        response = {
            "status": "ok",
            "probability": 0.4,
            "markets_used": flagless_markets(4),
            "metadata": {
                "oracle_port": {
                    "relevance_filter_summary": {
                        "selected_evidence_profile": {"profile": "proxy_only", "reason": "proxy-heavy"}
                    }
                }
            },
        }
        record = live_leg_record("Q?", response)

        self.assertEqual(record["evidence_profile"], "proxy_only")

    def test_valid_top_level_profile_still_wins_over_nested(self) -> None:
        response = {
            "status": "ok",
            "probability": 0.4,
            "markets_used": flagless_markets(4),
            "evidence_profile": {"type": "direct_mixed"},
            "metadata": {
                "oracle_port": {
                    "relevance_filter_summary": {"selected_evidence_profile": "proxy_only"}
                }
            },
        }
        record = live_leg_record("Q?", response)

        self.assertEqual(record["evidence_profile"], "direct_mixed")

    def test_market_count_fallback_when_no_profiles_present(self) -> None:
        flagless = live_leg_record("Q?", {"probability": 0.4, "markets_used": flagless_markets(3)})
        self.assertEqual(flagless["evidence_profile"], "direct_only")

        mixed_markets = flagless_markets(2) + [
            {"source": "fake_live_market", "question": "Proxy?", "probability": 0.4, "is_proxy": True}
        ]
        mixed = live_leg_record("Q?", {"probability": 0.4, "markets_used": mixed_markets})
        self.assertEqual(mixed["evidence_profile"], "direct_mixed")

        no_markets = live_leg_record("Q?", {"probability": 0.4})
        self.assertEqual(no_markets["evidence_profile"], "unspecified")

    def test_proxy_only_profile_from_metadata_gets_half_weight_end_to_end(self) -> None:
        proxy_metadata_response = {
            "status": "ok",
            "probability": 0.05,
            "confidence_interval": {"lower": 0.03, "upper": 0.08},
            "markets_used": flagless_markets(4),
            "metadata": {
                "oracle_port": {
                    "relevance_filter_summary": {"selected_evidence_profile": "proxy_only"}
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient([live_response(0.1), live_response(0.2), proxy_metadata_response])
            with contextlib.redirect_stdout(io.StringIO()):
                result = tier1.run_replay(
                    thesis_id="labor-resilience-jul2026",
                    output_dir=tmp,
                    client=client,
                )

            fed_leg = result["multi_leg_decision"].leg_decisions[2]
            self.assertEqual(fed_leg.evidence_profile, "proxy_only")
            self.assertEqual(fed_leg.weight, 0.5)
            self.assertEqual(result["multi_leg_decision"].direct_evidence_legs, 2)
            self.assertEqual(result["multi_leg_decision"].weighted_support, 2.5)


class MissingRequestsTests(unittest.TestCase):
    def test_client_raises_exact_message_when_requests_missing(self) -> None:
        with patch.dict(sys.modules, {"requests": None}):
            with self.assertRaises(PolyBridgeError) as ctx:
                PolyBridgeClient()
        self.assertEqual(str(ctx.exception), MISSING_REQUESTS_MESSAGE)

    def test_tier1_live_exits_with_exact_missing_requests_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.dict(sys.modules, {"requests": None}):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = tier1.main(["--thesis", "labor-resilience-jul2026", "--output-dir", tmp])

        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue().strip(), MISSING_REQUESTS_MESSAGE)

    def test_tier3_live_exits_with_exact_missing_requests_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.dict(sys.modules, {"requests": None}):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = tier3.main(["--thesis", "labor-resilience-jul2026", "--output-dir", tmp])

        self.assertEqual(code, 1)
        self.assertEqual(stderr.getvalue().strip(), MISSING_REQUESTS_MESSAGE)


if __name__ == "__main__":
    unittest.main()
