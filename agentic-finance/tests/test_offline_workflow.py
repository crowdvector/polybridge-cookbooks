from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentic_finance.cli import run_offline_workflow


BASE_DIR = Path(__file__).resolve().parents[1]


class OfflineWorkflowTests(unittest.TestCase):
    def test_offline_workflow_creates_expected_files_and_valid_audit_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            result = run_offline_workflow(base_dir=BASE_DIR, output_dir=output_dir)

            paths = result["paths"]
            self.assertTrue(paths["evidence_packet"].exists())
            self.assertTrue(paths["decision_memo"].exists())
            self.assertTrue(paths["audit_log"].exists())
            self.assertTrue(paths["paper_preview"].exists())

            evidence = json.loads(paths["evidence_packet"].read_text(encoding="utf-8"))
            self.assertEqual(evidence["allowed_use"], "research_only_not_financial_advice")

            lines = paths["audit_log"].read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            audit = json.loads(lines[0])
            self.assertEqual(audit["schema_version"], "audit_record.v1")
            self.assertTrue(audit["guardrails"]["no_live_polybridge_calls"])
            self.assertTrue(audit["guardrails"]["no_broker_submission"])


if __name__ == "__main__":
    unittest.main()
