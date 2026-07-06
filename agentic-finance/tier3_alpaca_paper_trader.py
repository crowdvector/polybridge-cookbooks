#!/usr/bin/env python3
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
    AlpacaPaperAuthError,
    AlpacaPaperConfig,
    AlpacaPaperError,
    read_alpaca_paper_config_from_env,
    submit_paper_order,
)
from agentic_finance.models import to_jsonable
from agentic_finance.multileg import run_multileg_replay_workflow
from agentic_finance.redaction import redact


def default_base_dir() -> Path:
    return Path(__file__).resolve().parent


def default_theses_path(base_dir: Path) -> Path:
    return base_dir / "examples" / "sample_theses.json"


def default_replay_path(base_dir: Path) -> Path:
    return base_dir / "examples" / "recorded_run_2026-07-04.json"


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(to_jsonable(data)), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def parse_symbol_allowlist(value: str | None) -> tuple[str, ...]:
    if value is None:
        return DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST
    symbols = tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())
    if not symbols:
        raise AlpacaPaperError("Guarded paper submission requires at least one allowlisted symbol.")
    return symbols


def run_preview_or_submit(
    *,
    thesis_id: str,
    replay_path: str | Path | None = None,
    theses_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    submit: bool = False,
    config: AlpacaPaperConfig | None = None,
    session: Any | None = None,
    confirm_paper_trading: bool = False,
    confirm_not_financial_advice: bool = False,
    confirm_human_approval: bool = False,
    max_notional_usd: float = DEFAULT_PAPER_SUBMISSION_NOTIONAL_CAP_USD,
    symbol_allowlist: tuple[str, ...] = DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    base = base_dir or default_base_dir()
    output = Path(output_dir) if output_dir is not None else base / "outputs"
    result = run_multileg_replay_workflow(
        thesis_id=thesis_id,
        theses_path=Path(theses_path) if theses_path is not None else default_theses_path(base),
        replay_path=Path(replay_path) if replay_path is not None else default_replay_path(base),
        base_dir=base,
        output_dir=output,
        create_preview=True,
    )
    decision = result["multi_leg_decision"]
    preview = result.get("paper_preview")
    if not submit:
        return {"mode": "preview_only", **result}
    if not decision.cleared_for_paper_preview or preview is None:
        raise AlpacaPaperError("Evidence Gate did not clear; guarded paper submission is blocked.")

    paper_config = config or read_alpaca_paper_config_from_env()
    submission_result = submit_paper_order(
        preview,
        paper_config,
        gate_decision=result["gate_decision"],
        confirm_paper_trading=confirm_paper_trading,
        confirm_not_financial_advice=confirm_not_financial_advice,
        confirm_human_approval=confirm_human_approval,
        max_notional_usd=max_notional_usd,
        symbol_allowlist=symbol_allowlist,
        session=session,
    )
    result_path = write_json(output / "alpaca-paper-submission-result.json", submission_result)
    audit_path, audit_record = append_paper_submission_audit_record(
        base_dir=base,
        output_dir=output,
        run_id=result["run_id"],
        scenario_id=result["thesis"].thesis_id,
        paper_preview_path=result["paths"].get("paper_preview"),
        order_result_path=result_path,
        submission_result=submission_result,
    )
    paths = dict(result["paths"])
    paths["paper_submission_result"] = result_path
    paths["audit_log"] = audit_path
    return {
        "mode": "paper_submission",
        **result,
        "submission_result": submission_result,
        "submission_audit_record": audit_record,
        "paths": paths,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tier 3 guarded Alpaca paper workflow for Agentic Finance")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preview-only",
        action="store_true",
        help="Create a local paper preview after the multi-leg gate clears. This is the default.",
    )
    mode.add_argument(
        "--submit-paper-order",
        action="store_true",
        help="Submit a guarded paper order only after all explicit safety checks pass.",
    )
    parser.add_argument("--thesis", required=True, help="Thesis ID from examples/sample_theses.json.")
    parser.add_argument("--replay", type=Path, default=None, help="Recorded replay fixture path.")
    parser.add_argument("--theses", type=Path, default=None, help="Thesis config JSON path.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional runtime output directory.")
    parser.add_argument("--confirm-paper-trading", action="store_true", help="Confirm simulated paper trading only.")
    parser.add_argument(
        "--confirm-not-financial-advice",
        action="store_true",
        help="Confirm this demo output is not financial advice.",
    )
    parser.add_argument(
        "--confirm-human-approval",
        action="store_true",
        help="Confirm explicit human approval for the guarded paper submission.",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_preview_or_submit(
            thesis_id=args.thesis,
            replay_path=args.replay,
            theses_path=args.theses,
            output_dir=args.output_dir,
            submit=args.submit_paper_order,
            confirm_paper_trading=args.confirm_paper_trading,
            confirm_not_financial_advice=args.confirm_not_financial_advice,
            confirm_human_approval=args.confirm_human_approval,
            max_notional_usd=args.max_notional_usd,
            symbol_allowlist=parse_symbol_allowlist(args.symbol_allowlist),
        )
    except AlpacaPaperAuthError as exc:
        print(f"Alpaca paper authentication failed: {redact(str(exc))}", file=sys.stderr)
        return 1
    except AlpacaPaperError as exc:
        print(f"Alpaca paper workflow failed: {redact(str(exc))}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Tier 3 workflow failed: {redact(str(exc))}", file=sys.stderr)
        return 1

    decision = result["multi_leg_decision"]
    print(f"Verdict: {decision.verdict}")
    print(f"Weighted support: {decision.weighted_support:.1f}")
    print(result["memo_markdown"].strip())
    preview = result.get("paper_preview")
    if preview is not None:
        print(f"paper_preview: {preview.side.upper()} {preview.symbol} {preview.notional_usd:.2f} notional")
    if result["mode"] == "paper_submission":
        print(f"paper_submission_status: {result['submission_result']['status']}")
    for label, path in result["paths"].items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
