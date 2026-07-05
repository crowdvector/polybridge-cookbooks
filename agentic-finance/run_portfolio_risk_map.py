from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from agentic_finance.audit import append_portfolio_audit_record
from agentic_finance.gate import apply_gate
from agentic_finance.models import to_jsonable
from agentic_finance.polybridge import PolyBridgeClient, PolyBridgeError
from agentic_finance.portfolio import (
    PortfolioRiskItem,
    build_portfolio_risk_map,
    fetch_live_portfolio_evidence,
    generate_portfolio_risk_memo,
    load_offline_portfolio_evidence,
    map_holdings_to_exposures,
    parse_holdings_csv,
    risk_band,
)
from agentic_finance.redaction import redact

PORTFOLIO_RISK_MAP_FILENAME = "portfolio-" + "risk" + "-map.json"
PORTFOLIO_RISK_MEMO_FILENAME = "portfolio-" + "risk" + "-memo.md"


def default_base_dir() -> Path:
    return Path(__file__).resolve().parent


def resolve_input_path(path: Path, base_dir: Path) -> Path:
    if path.is_absolute():
        return path
    if path.exists():
        return path.resolve()
    return (base_dir / path).resolve()


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_data = redact(to_jsonable(data))
    path.write_text(json.dumps(safe_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text) + "\n", encoding="utf-8")
    return path


def run_portfolio_risk_map_workflow(
    holdings_path: Path,
    base_dir: Path | None = None,
    fixtures_dir: Path | None = None,
    output_dir: Path | None = None,
    live_polybridge: bool = False,
    client: PolyBridgeClient | None = None,
) -> dict[str, Any]:
    base_dir = base_dir or default_base_dir()
    fixtures_dir = fixtures_dir or (base_dir / "fixtures" / "portfolio")
    output_dir = output_dir or (base_dir / "outputs")
    resolved_holdings = resolve_input_path(holdings_path, base_dir)

    holdings = parse_holdings_csv(resolved_holdings)
    exposures = map_holdings_to_exposures(holdings)
    polybridge_client = client or PolyBridgeClient() if live_polybridge else None

    risk_items: list[PortfolioRiskItem] = []
    for exposure in exposures:
        if live_polybridge:
            if polybridge_client is None:
                raise PolyBridgeError("Live PolyBridge client was not initialized.")
            packet = fetch_live_portfolio_evidence(exposure, polybridge_client)
        else:
            packet = load_offline_portfolio_evidence(exposure, fixtures_dir)
        decision = apply_gate(packet)
        risk_items.append(
            PortfolioRiskItem(
                exposure=exposure,
                evidence_packet=packet,
                gate_decision=decision,
                risk_band=risk_band(packet, decision),
            )
        )

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    risk_item_tuple = tuple(risk_items)
    risk_map = build_portfolio_risk_map(
        run_id=run_id,
        holdings=holdings,
        exposures=exposures,
        risk_items=risk_item_tuple,
    )
    memo = generate_portfolio_risk_memo(holdings, exposures, risk_item_tuple, risk_map)

    paths: dict[str, Path] = {
        "portfolio_risk_map": write_json(output_dir / PORTFOLIO_RISK_MAP_FILENAME, risk_map),
        "portfolio_risk_memo": write_text(output_dir / PORTFOLIO_RISK_MEMO_FILENAME, memo),
    }
    audit_path, audit_record = append_portfolio_audit_record(
        base_dir=base_dir,
        output_dir=output_dir,
        run_id=run_id,
        holdings_source=resolved_holdings,
        exposures=exposures,
        evidence_packets=tuple(item.evidence_packet for item in risk_item_tuple),
        gate_decisions=tuple(item.gate_decision for item in risk_item_tuple),
        risk_map_path=paths["portfolio_risk_map"],
        memo_path=paths["portfolio_risk_memo"],
    )
    paths["audit_log"] = audit_path

    return {
        "run_id": run_id,
        "holdings": holdings,
        "exposures": exposures,
        "risk_items": risk_item_tuple,
        "risk_map": risk_map,
        "memo": memo,
        "audit_record": audit_record,
        "paths": paths,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Portfolio Event-Risk Map cookbook tier")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Run the fixture-backed workflow. This is the default.")
    mode.add_argument(
        "--live-polybridge",
        action="store_true",
        help="Run live PolyBridge Search/Forecast evidence fetches. Read-only and optional.",
    )
    parser.add_argument("--holdings", type=Path, required=True, help="Path to a local holdings CSV.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional runtime output directory.")
    parser.add_argument("--fixtures-dir", type=Path, default=None, help="Optional portfolio fixture directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = run_portfolio_risk_map_workflow(
            holdings_path=args.holdings,
            fixtures_dir=args.fixtures_dir,
            output_dir=args.output_dir,
            live_polybridge=args.live_polybridge,
        )
    except (PolyBridgeError, ValueError, OSError) as exc:
        print(f"Portfolio event-risk map failed: {redact(str(exc))}", file=sys.stderr)
        return 1

    if args.live_polybridge and any(
        item.gate_decision.decision == "blocked_api_error" for item in result["risk_items"]
    ):
        print("PolyBridge live evidence fetch failed or was incomplete for one or more exposures.", file=sys.stderr)
        exit_code = 1
    else:
        exit_code = 0

    for label, path in result["paths"].items():
        print(f"{label}: {path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
