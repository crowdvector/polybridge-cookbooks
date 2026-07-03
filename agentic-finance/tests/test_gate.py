from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentic_finance.evidence import load_offline_evidence
from agentic_finance.gate import apply_gate


BASE_DIR = Path(__file__).resolve().parents[1]


class GateTests(unittest.TestCase):
    def test_gate_clears_strong_fixture(self) -> None:
        _, packet = load_offline_evidence(BASE_DIR / "fixtures")

        decision = apply_gate(packet)

        self.assertEqual(decision.decision, "cleared_for_paper_preview")
        self.assertTrue(decision.cleared_for_paper_preview)

    def test_gate_blocks_weak_evidence(self) -> None:
        _, packet = load_offline_evidence(BASE_DIR / "fixtures")
        weak_packet = replace(packet, confidence=0.25)

        decision = apply_gate(weak_packet)

        self.assertEqual(decision.decision, "blocked_weak_evidence")
        self.assertFalse(decision.cleared_for_paper_preview)

    def test_gate_blocks_missing_evidence(self) -> None:
        _, packet = load_offline_evidence(BASE_DIR / "fixtures")
        missing_packet = replace(packet, probability=None, source_markets=tuple())

        decision = apply_gate(missing_packet)

        self.assertEqual(decision.decision, "blocked_insufficient_evidence")
        self.assertFalse(decision.cleared_for_paper_preview)

    def test_gate_blocks_search_unavailable(self) -> None:
        _, packet = load_offline_evidence(BASE_DIR / "fixtures")
        search_error_packet = replace(packet, quality_flags=(*packet.quality_flags, "search_unavailable"))

        decision = apply_gate(search_error_packet)

        self.assertEqual(decision.decision, "blocked_api_error")
        self.assertFalse(decision.cleared_for_paper_preview)


if __name__ == "__main__":
    unittest.main()
