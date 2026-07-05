from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agentic_finance.audit import append_paper_submission_audit_record
from agentic_finance.brokers.alpaca import (
    DEFAULT_PAPER_SUBMISSION_NOTIONAL_CAP_USD,
    DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST,
    AlpacaPaperConfig,
    AlpacaPaperAuthError,
    AlpacaPaperClient,
    AlpacaPaperError,
    read_alpaca_paper_config_from_env,
    submit_paper_order,
)
from agentic_finance.cli import run_offline_workflow
from agentic_finance.models import to_jsonable
from agentic_finance.redaction import redact


def default_base_dir() -> Path:
    return Path(__file__).resolve().parent


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(to_jsonable(data)), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_preview_only(
    base_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    base_dir = base_dir or default_base_dir()
    result = run_offline_workflow(base_dir=base_dir, output_dir=output_dir)
    return {
        "mode": "preview_only",
        "result": result,
        "paths": result["paths"],
    }


def run_validate_paper_account(
    base_dir: Path | None = None,
    output_dir: Path | None = None,
    client: AlpacaPaperClient | None = None,
) -> dict[str, Any]:
    base_dir = base_dir or default_base_dir()
    output_dir = output_dir or (base_dir / "outputs")
    paper_client = client or AlpacaPaperClient(read_alpaca_paper_config_from_env())
    account_check = paper_client.get_account_metadata()
    path = write_json(output_dir / "alpaca-paper-account-check.json", account_check)
    return {
        "mode": "paper_account_validation",
        "account_check": account_check,
        "paths": {"paper_account_check": path},
    }


def parse_symbol_allowlist(value: str | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST
    symbols = tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())
    if not symbols:
        raise AlpacaPaperError("Guarded paper submission requires at least one allowlisted symbol.")
    return symbols


def run_submit_paper_order(
    *,
    base_dir: Path | None = None,
    output_dir: Path | None = None,
    config: AlpacaPaperConfig | None = None,
    session: Any | None = None,
    confirm_paper_trading: bool,
    confirm_not_financial_advice: bool,
    confirm_human_approval: bool,
    max_notional_usd: float = DEFAULT_PAPER_SUBMISSION_NOTIONAL_CAP_USD,
    symbol_allowlist: tuple[str, ...] = DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST,
) -> dict[str, Any]:
    base_dir = base_dir or default_base_dir()
    output_dir = output_dir or (base_dir / "outputs")
    workflow = run_offline_workflow(base_dir=base_dir, output_dir=output_dir)
    gate_decision = workflow["gate_decision"]
    preview = workflow.get("paper_preview")
    if not gate_decision.cleared_for_paper_preview or preview is None:
        raise AlpacaPaperError("Evidence Gate did not clear; guarded paper submission is blocked.")

    paper_config = config or read_alpaca_paper_config_from_env()
    submission_result = submit_paper_order(
        preview,
        paper_config,
        gate_decision=gate_decision,
        confirm_paper_trading=confirm_paper_trading,
        confirm_not_financial_advice=confirm_not_financial_advice,
        confirm_human_approval=confirm_human_approval,
        max_notional_usd=max_notional_usd,
        symbol_allowlist=symbol_allowlist,
        session=session,
    )
    result_path = write_json(output_dir / "alpaca-paper-submission-result.json", submission_result)
    audit_path, audit_record = append_paper_submission_audit_record(
        base_dir=base_dir,
        output_dir=output_dir,
        run_id=workflow["run_id"],
        scenario_id=workflow["intent"].scenario_id,
        paper_preview_path=workflow["paths"].get("paper_preview"),
        order_result_path=result_path,
        submission_result=submission_result,
    )
    paths = dict(workflow["paths"])
    paths["paper_submission_result"] = result_path
    paths["audit_log"] = audit_path
    return {
        "mode": "paper_submission",
        "result": workflow,
        "submission_result": submission_result,
        "audit_record": audit_record,
        "paths": paths,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optional Alpaca paper validation for Agentic Finance")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preview-only",
        action="store_true",
        help="Run offline Evidence Gate and write a local paper preview without Alpaca credentials. This is the default.",
    )
    mode.add_argument(
        "--validate-paper-account",
        action="store_true",
        help="Validate Alpaca paper credentials with GET /v2/account only.",
    )
    mode.add_argument(
        "--submit-paper-order",
        action="store_true",
        help="Submit a guarded Alpaca paper order only after all confirmation flags and safety checks pass.",
    )
    parser.add_argument("--confirm-paper-trading", action="store_true", help="Confirm simulated paper trading only.")
    parser.add_argument(
        "--confirm-not-financial-advice",
        action="store_true",
        help="Confirm this demo output is not financial advice.",
    )
    parser.add_argument(
        "--confirm-human-approval",
        action="store_true",
        help="Confirm explicit human approval for the paper submission.",
    )
    parser.add_argument(
        "--max-notional-usd",
        type=float,
        default=DEFAULT_PAPER_SUBMISSION_NOTIONAL_CAP_USD,
        help="Maximum paper order notional for the guarded demo path.",
    )
    parser.add_argument(
        "--symbol-allowlist",
        default=",".join(DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST),
        help="Comma-separated symbols allowed for guarded paper submission.",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional runtime output directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.validate_paper_account:
            result = run_validate_paper_account(output_dir=args.output_dir)
        elif args.submit_paper_order:
            result = run_submit_paper_order(
                output_dir=args.output_dir,
                confirm_paper_trading=args.confirm_paper_trading,
                confirm_not_financial_advice=args.confirm_not_financial_advice,
                confirm_human_approval=args.confirm_human_approval,
                max_notional_usd=args.max_notional_usd,
                symbol_allowlist=parse_symbol_allowlist(args.symbol_allowlist),
            )
        else:
            result = run_preview_only(output_dir=args.output_dir)
    except AlpacaPaperAuthError as exc:
        print(f"Alpaca paper authentication failed: {redact(str(exc))}", file=sys.stderr)
        return 1
    except AlpacaPaperError as exc:
        print(f"Alpaca paper validation failed: {redact(str(exc))}", file=sys.stderr)
        return 1

    if result["mode"] == "paper_submission":
        submission_result = result["submission_result"]
        print(f"paper_submission_status: {submission_result['status']}")
        print(f"paper_submission_result: {result['paths']['paper_submission_result']}")
        print(f"audit_log: {result['paths']['audit_log']}")
    else:
        for label, path in result["paths"].items():
            print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
