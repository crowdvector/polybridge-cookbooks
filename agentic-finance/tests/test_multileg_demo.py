from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tier1_evidence_gate as tier1
from agentic_finance.multileg import (
    ThesisConfig,
    ThesisLeg,
    classify_leg,
    evaluate_thesis,
    load_recorded_run,
    load_theses,
)


BASE_DIR = Path(__file__).resolve().parents[1]
THESES_PATH = BASE_DIR / "examples" / "sample_theses.json"
REPLAY_PATH = BASE_DIR / "examples" / "recorded_run_2026-07-04.json"


class MultiLegDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.theses = load_theses(THESES_PATH)
        self.replay = load_recorded_run(REPLAY_PATH)

    def test_only_labor_resilience_thesis_is_shipped(self) -> None:
        self.assertEqual(tuple(self.theses), ("labor-resilience-jul2026",))

    def test_labor_resilience_replay_proceeds(self) -> None:
        decision = evaluate_thesis(self.theses["labor-resilience-jul2026"], self.replay)

        self.assertEqual(decision.verdict, "PROCEED")
        self.assertEqual(decision.weighted_support, 3.0)
        self.assertEqual(decision.direct_evidence_legs, 3)
        self.assertEqual(decision.full_weight_contradictions, ())
        self.assertEqual([leg.classification for leg in decision.leg_decisions], ["SUPPORTS", "SUPPORTS", "SUPPORTS"])

    def test_confidence_scalar_is_ignored(self) -> None:
        changed_replay = copy.deepcopy(self.replay)
        for leg in changed_replay["theses"]["labor-resilience-jul2026"]["legs"]:
            leg["confidence"] = 0.01

        original = evaluate_thesis(self.theses["labor-resilience-jul2026"], self.replay)
        changed = evaluate_thesis(self.theses["labor-resilience-jul2026"], changed_replay)

        self.assertEqual(changed.verdict, original.verdict)
        self.assertEqual(
            [leg.classification for leg in changed.leg_decisions],
            [leg.classification for leg in original.leg_decisions],
        )

    def test_thresholds_are_read_from_thesis_config(self) -> None:
        thesis = self.theses["labor-resilience-jul2026"]
        first_leg = thesis.questions[0]
        tightened = replace(first_leg, threshold=0.1)
        recorded_leg = self.replay["theses"][thesis.thesis_id]["legs"][0]

        original_decision = classify_leg(thesis, first_leg, recorded_leg)
        tightened_decision = classify_leg(thesis, tightened, recorded_leg)

        self.assertEqual(original_decision.classification, "SUPPORTS")
        self.assertEqual(tightened_decision.classification, "NEUTRAL")

    def test_proxy_only_evidence_gets_half_weight(self) -> None:
        thesis = self.theses["labor-resilience-jul2026"]
        leg = ThesisLeg(
            question="Will the synthetic event resolve yes?",
            supports_when="YES",
            threshold=0.3,
        )
        recorded_leg = {
            "probability": 0.4,
            "interval": [0.34, 0.46],
            "evidence_profile": "proxy_only",
            "source_markets": [{"question": "Synthetic proxy", "probability": 0.4, "is_proxy": True}],
        }

        decision = classify_leg(thesis, leg, recorded_leg)

        self.assertEqual(decision.classification, "SUPPORTS")
        self.assertEqual(decision.weight, 0.5)

    def test_insufficient_or_failed_legs_get_zero_weight(self) -> None:
        thesis = self.theses["labor-resilience-jul2026"]
        leg = thesis.questions[0]
        recorded_leg = copy.deepcopy(self.replay["theses"][thesis.thesis_id]["legs"][0])
        recorded_leg["insufficient_data"] = True

        decision = classify_leg(thesis, leg, recorded_leg)

        self.assertEqual(decision.classification, "INSUFFICIENT")
        self.assertEqual(decision.weight, 0.0)

    def test_synthetic_weak_or_contradictory_evidence_declines(self) -> None:
        thesis = ThesisConfig(
            thesis_id="synthetic-weak-labor",
            as_of="2026-07-04",
            demo=True,
            evergreen=True,
            thesis="Synthetic weak labor thesis",
            instrument="SPY",
            direction="long",
            notional_usd=1000,
            questions=(
                ThesisLeg("Will synthetic jobs remain strong?", "YES", 0.7),
                ThesisLeg("Will synthetic unemployment stay contained?", "YES", 0.7),
                ThesisLeg("Will synthetic policy stay steady?", "YES", 0.7),
            ),
        )
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

        decision = evaluate_thesis(thesis, replay)

        self.assertEqual(decision.verdict, "DECLINE")
        self.assertIn("Will synthetic jobs remain strong?", decision.full_weight_contradictions)

    def test_tier1_replay_writes_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = tier1.run_replay(
                thesis_id="labor-resilience-jul2026",
                replay_path=REPLAY_PATH,
                theses_path=THESES_PATH,
                output_dir=Path(temp_dir),
                base_dir=BASE_DIR,
            )

            paths = result["paths"]
            self.assertTrue(paths["evidence_packet"].exists())
            self.assertTrue(paths["gate_decision"].exists())
            self.assertTrue(paths["decision_memo"].exists())
            self.assertTrue(paths["decisions_log"].exists())

        self.assertEqual(result["multi_leg_decision"].verdict, "PROCEED")


if __name__ == "__main__":
    unittest.main()
