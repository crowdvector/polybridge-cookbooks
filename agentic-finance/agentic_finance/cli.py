from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from .audit import append_audit_record
from .brokers.alpaca import create_paper_order_preview
from .evidence import load_offline_evidence
from .gate import apply_gate
from .memo import generate_decision_memo
from .models import to_jsonable
from .redaction import redact


def default_base_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_data = redact(to_jsonable(data))
    path.write_text(json.dumps(safe_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text) + "\n", encoding="utf-8")
    return path


def run_offline_workflow(
    base_dir: Path | None = None,
    fixtures_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    base_dir = base_dir or default_base_dir()
    fixtures_dir = fixtures_dir or (base_dir / "fixtures")
    output_dir = output_dir or (base_dir / "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    intent, packet = load_offline_evidence(fixtures_dir)
    decision = apply_gate(packet)
    memo = generate_decision_memo(intent, packet, decision)

    paths: dict[str, Path] = {
        "evidence_packet": write_json(output_dir / "evidence-packet.json", packet),
        "decision_memo": write_text(output_dir / "decision-memo.md", memo.markdown),
    }

    preview = None
    if decision.cleared_for_paper_preview:
        preview = create_paper_order_preview(intent, decision)
        paths["paper_preview"] = write_json(output_dir / "alpaca-order-preview.json", preview)

    audit_path, audit_record = append_audit_record(
        base_dir=base_dir,
        output_dir=output_dir,
        run_id=run_id,
        scenario_id=intent.scenario_id,
        evidence_packet=packet,
        gate_decision=decision,
        memo_path=paths["decision_memo"],
        paper_preview_path=paths.get("paper_preview"),
    )
    paths["audit_log"] = audit_path

    return {
        "run_id": run_id,
        "intent": intent,
        "evidence_packet": packet,
        "gate_decision": decision,
        "decision_memo": memo,
        "paper_preview": preview,
        "audit_record": audit_record,
        "paths": paths,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline Agentic Finance Evidence Gate cookbook")
    parser.add_argument("--offline", action="store_true", help="Run the fixture-backed workflow. Required in PR 1.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional runtime output directory.")
    parser.add_argument("--fixtures-dir", type=Path, default=None, help="Optional fixture directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.offline:
        parser.error("PR 1 supports only --offline. Live API and broker paths are intentionally absent.")

    result = run_offline_workflow(fixtures_dir=args.fixtures_dir, output_dir=args.output_dir)
    decision = result["gate_decision"]
    print(f"Decision: {decision.decision}")
    print(f"Paper preview allowed: {decision.cleared_for_paper_preview}")
    for label, path in result["paths"].items():
        print(f"{label}: {path}")
    return 0
