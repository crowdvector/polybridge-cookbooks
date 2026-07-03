from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import EvidencePacket, GateDecision, to_jsonable
from .redaction import redact


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_audit_record(
    run_id: str,
    scenario_id: str,
    evidence_packet: EvidencePacket,
    gate_decision: GateDecision,
    memo_path: Path,
    paper_preview_path: Path | None = None,
) -> dict[str, Any]:
    record = {
        "schema_version": "audit_record.v1",
        "run_id": run_id,
        "timestamp": utc_now_iso(),
        "scenario_id": scenario_id,
        "evidence_packet": to_jsonable(evidence_packet),
        "gate_decision": to_jsonable(gate_decision),
        "memo_path": str(memo_path),
        "paper_preview_path": str(paper_preview_path) if paper_preview_path else None,
        "guardrails": {
            "offline_fixture_mode": True,
            "no_live_polybridge_calls": True,
            "no_live_broker_calls": True,
            "no_broker_submission": True,
            "paper_preview_only": True,
            "secrets_redacted": True,
        },
    }
    return redact(record)


def append_audit_record(
    base_dir: Path,
    run_id: str,
    scenario_id: str,
    evidence_packet: EvidencePacket,
    gate_decision: GateDecision,
    memo_path: Path,
    paper_preview_path: Path | None = None,
    output_dir: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    runtime_dir = output_dir or (base_dir / "outputs")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    audit_path = runtime_dir / "audit-log.jsonl"
    record = build_audit_record(
        run_id=run_id,
        scenario_id=scenario_id,
        evidence_packet=evidence_packet,
        gate_decision=gate_decision,
        memo_path=memo_path,
        paper_preview_path=paper_preview_path,
    )
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return audit_path, record
