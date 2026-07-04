from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from .audit import append_audit_record
from .brokers.alpaca import create_paper_order_preview
from .evidence import fetch_live_evidence, load_intent, load_offline_evidence
from .gate import apply_gate
from .memo import generate_decision_memo
from .models import to_jsonable
from .polybridge import PolyBridgeClient, PolyBridgeError
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
    intent, packet = load_offline_evidence(fixtures_dir)
    return run_evidence_workflow(intent=intent, packet=packet, base_dir=base_dir, output_dir=output_dir)


def run_live_polybridge_workflow(
    base_dir: Path | None = None,
    fixtures_dir: Path | None = None,
    output_dir: Path | None = None,
    client: PolyBridgeClient | None = None,
) -> dict[str, Any]:
    base_dir = base_dir or default_base_dir()
    fixtures_dir = fixtures_dir or (base_dir / "fixtures")
    intent = load_intent(fixtures_dir)
    packet = fetch_live_evidence(intent, client or PolyBridgeClient())
    return run_evidence_workflow(intent=intent, packet=packet, base_dir=base_dir, output_dir=output_dir)


def run_evidence_workflow(
    intent: Any,
    packet: Any,
    base_dir: Path,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir = output_dir or (base_dir / "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = f"run_{uuid.uuid4().hex[:12]}"
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Run the fixture-backed workflow. This is the default.")
    mode.add_argument(
        "--live-polybridge",
        action="store_true",
        help="Run live PolyBridge Search/Forecast evidence fetches. Read-only and optional.",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional runtime output directory.")
    parser.add_argument("--fixtures-dir", type=Path, default=None, help="Optional fixture directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.live_polybridge:
            result = run_live_polybridge_workflow(fixtures_dir=args.fixtures_dir, output_dir=args.output_dir)
        else:
            result = run_offline_workflow(fixtures_dir=args.fixtures_dir, output_dir=args.output_dir)
    except PolyBridgeError as exc:
        print(f"PolyBridge live evidence fetch failed: {redact(str(exc))}", file=sys.stderr)
        return 1

    decision = result["gate_decision"]
    exit_code = 0
    if args.live_polybridge and decision.decision == "blocked_api_error":
        print("PolyBridge live evidence fetch failed or was incomplete; see output artifacts.", file=sys.stderr)
        exit_code = 1

    print(f"Decision: {decision.decision}")
    print(f"Paper preview allowed: {decision.cleared_for_paper_preview}")
    for label, path in result["paths"].items():
        print(f"{label}: {path}")
    return exit_code
