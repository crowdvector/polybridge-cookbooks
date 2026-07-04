from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import EvidencePacket, GateDecision, to_jsonable
from .redaction import redact


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def audit_path(path: Path | None, base_dir: Path) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(base_dir.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return f"external-output/{path.name or 'output'}"


def build_audit_record(
    run_id: str,
    scenario_id: str,
    evidence_packet: EvidencePacket,
    gate_decision: GateDecision,
    memo_path: Path,
    paper_preview_path: Path | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    audit_base_dir = base_dir or Path.cwd()
    live_polybridge = bool(evidence_packet.evidence_profile.get("live_polybridge"))
    offline_fixture_mode = bool(evidence_packet.evidence_profile.get("fixture_mode", False))
    record = {
        "schema_version": "audit_record.v1",
        "run_id": run_id,
        "timestamp": utc_now_iso(),
        "scenario_id": scenario_id,
        "evidence_packet": to_jsonable(evidence_packet),
        "gate_decision": to_jsonable(gate_decision),
        "memo_path": audit_path(memo_path, audit_base_dir),
        "paper_preview_path": audit_path(paper_preview_path, audit_base_dir),
        "guardrails": {
            "offline_fixture_mode": offline_fixture_mode,
            "no_live_polybridge_calls": not live_polybridge,
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
        base_dir=base_dir,
    )
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return audit_path, record
