from __future__ import annotations

import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentic_finance.brokers.alpaca import create_paper_order_preview
from agentic_finance.evidence import load_offline_evidence
from agentic_finance.gate import apply_gate


BASE_DIR = Path(__file__).resolve().parents[1]


class AlpacaPreviewTests(unittest.TestCase):
    def test_preview_requires_cleared_gate(self) -> None:
        intent, packet = load_offline_evidence(BASE_DIR / "fixtures")
        blocked_packet = replace(packet, confidence=0.1)
        blocked_decision = apply_gate(blocked_packet)

        with self.assertRaises(ValueError):
            create_paper_order_preview(intent, blocked_decision)

    def test_preview_is_paper_only_and_requires_human_approval(self) -> None:
        intent, packet = load_offline_evidence(BASE_DIR / "fixtures")
        decision = apply_gate(packet)

        preview = create_paper_order_preview(intent, decision)

        self.assertEqual(preview.broker, "alpaca")
        self.assertEqual(preview.mode, "paper_preview_only")
        self.assertFalse(preview.submit_supported)
        self.assertTrue(preview.human_approval_required)
        self.assertEqual(preview.allowed_use, "research_only_not_financial_advice")


if __name__ == "__main__":
    unittest.main()
