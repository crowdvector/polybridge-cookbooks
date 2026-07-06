#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from agentic_finance.audit import append_paper_submission_audit_record
from agentic_finance.broker import (
    SimBroker,
    build_sim_broker_audit_record,
    order_from_intent,
)
from agentic_finance.brokers.alpaca import (
    DEFAULT_PAPER_SUBMISSION_NOTIONAL_CAP_USD,
    DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST,
    AlpacaPaperAuthError,
    AlpacaPaperConfig,
    AlpacaPaperError,
    create_paper_order_preview,
    read_alpaca_paper_config_from_env,
    submit_paper_order,
)
from agentic_finance.models import to_jsonable
from agentic_finance.multileg import append_jsonl, run_multileg_replay_workflow
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


def format_notional(notional: str) -> str:
    value = float(notional)
    if value.is_integer():
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def run_alpaca_paper_path(
    *,
    workflow: dict[str, Any],
    output_dir: Path,
    base_dir: Path,
    config: AlpacaPaperConfig | None = None,
    session: Any | None = None,
    submit_paper: bool,
    confirm_paper_trading: bool,
    confirm_not_financial_advice: bool,
    confirm_human_approval: bool,
    max_notional_usd: float,
    symbol_allowlist: tuple[str, ...],
) -> dict[str, Any]:
    decision = workflow["multi_leg_decision"]
    if not decision.cleared_for_paper_preview:
        return {"mode": "decline", "broker": "alpaca", **workflow}
    if not submit_paper:
        raise AlpacaPaperError(
            "The optional Alpaca paper adapter requires --submit-paper-order, paper credentials, "
            "and all confirmation flags. Use the default SimBroker path for account-free replay."
        )

    preview = create_paper_order_preview(workflow["intent"], workflow["gate_decision"])
    preview_path = write_json(output_dir / "alpaca-order-preview.json", preview)
    paper_config = config or read_alpaca_paper_config_from_env()
    submission_result = submit_paper_order(
        preview,
        paper_config,
        gate_decision=workflow["gate_decision"],
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
        scenario_id=workflow["thesis"].thesis_id,
        paper_preview_path=preview_path,
        order_result_path=result_path,
        submission_result=submission_result,
    )
    paths = dict(workflow["paths"])
    paths["paper_preview"] = preview_path
    paths["paper_submission_result"] = result_path
    paths["audit_log"] = audit_path
    return {
        "mode": "alpaca_paper_submission",
        "broker": "alpaca",
        **workflow,
        "paper_preview": preview,
        "submission_result": submission_result,
        "submission_audit_record": audit_record,
        "paths": paths,
    }


def run_paper_trader(
    *,
    thesis_id: str,
    replay_path: str | Path | None = None,
    theses_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    broker_name: str = "sim",
    confirmation: str | None = None,
    input_fn: Callable[[str], str] = input,
    confirmation_fn: Callable[[dict[str, Any], dict[str, Any]], str] | None = None,
    config: AlpacaPaperConfig | None = None,
    session: Any | None = None,
    submit_paper_order: bool = False,
    confirm_paper_trading: bool = False,
    confirm_not_financial_advice: bool = False,
    confirm_human_approval: bool = False,
    max_notional_usd: float = DEFAULT_PAPER_SUBMISSION_NOTIONAL_CAP_USD,
    symbol_allowlist: tuple[str, ...] = DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    base = base_dir or default_base_dir()
    output = Path(output_dir) if output_dir is not None else base / "outputs"
    workflow = run_multileg_replay_workflow(
        thesis_id=thesis_id,
        theses_path=Path(theses_path) if theses_path is not None else default_theses_path(base),
        replay_path=Path(replay_path) if replay_path is not None else default_replay_path(base),
        base_dir=base,
        output_dir=output,
        create_preview=False,
    )
    decision = workflow["multi_leg_decision"]
    broker_key = broker_name.strip().lower()
    if broker_key == "alpaca":
        return run_alpaca_paper_path(
            workflow=workflow,
            output_dir=output,
            base_dir=base,
            config=config,
            session=session,
            submit_paper=submit_paper_order,
            confirm_paper_trading=confirm_paper_trading,
            confirm_not_financial_advice=confirm_not_financial_advice,
            confirm_human_approval=confirm_human_approval,
            max_notional_usd=max_notional_usd,
            symbol_allowlist=symbol_allowlist,
        )
    if broker_key != "sim":
        raise ValueError(f"Unsupported broker: {broker_name}")
    if not decision.cleared_for_paper_preview:
        return {"mode": "decline", "broker": "sim", "broker_event": "skipped_decline", **workflow}

    broker = SimBroker(output)
    order = order_from_intent(workflow["intent"])
    preview = broker.preview(order)
    preview_path = write_json(output / "paper-order-preview.json", preview)
    paths = dict(workflow["paths"])
    paths["paper_order_preview"] = preview_path

    if confirmation is not None:
        answer = confirmation
    elif confirmation_fn is not None:
        answer = confirmation_fn(workflow, preview)
    else:
        answer = input_fn("Confirm simulated paper trade? y/N ")
    if answer.strip().lower() != "y":
        audit_record = build_sim_broker_audit_record(
            base_dir=base,
            run_id=workflow["run_id"],
            thesis_id=workflow["thesis"].thesis_id,
            order=order,
            preview=preview,
            event="human_declined",
        )
        paths["decisions_log"] = append_jsonl(output / "decisions.jsonl", audit_record)
        return {
            "mode": "sim_broker",
            "broker": "sim",
            "broker_event": "human_declined",
            **workflow,
            "broker_order": order,
            "broker_preview": preview,
            "broker_result": None,
            "broker_audit_record": audit_record,
            "paths": paths,
        }

    simulated_result = broker.submit(order)
    result_path = write_json(output / "simbroker-order-result.json", simulated_result)
    paper_portfolio_path = output / "paper_portfolio.jsonl"
    audit_record = build_sim_broker_audit_record(
        base_dir=base,
        run_id=workflow["run_id"],
        thesis_id=workflow["thesis"].thesis_id,
        order=order,
        preview=preview,
        event="simulated_fill_recorded",
        paper_portfolio_path=paper_portfolio_path,
        simulated_result=simulated_result,
    )
    paths["simulated_order_result"] = result_path
    paths["paper_portfolio"] = paper_portfolio_path
    paths["decisions_log"] = append_jsonl(output / "decisions.jsonl", audit_record)
    return {
        "mode": "sim_broker",
        "broker": "sim",
        "broker_event": "simulated_fill_recorded",
        **workflow,
        "broker_order": order,
        "broker_preview": preview,
        "broker_result": simulated_result,
        "broker_audit_record": audit_record,
        "paths": paths,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tier 3 paper trader for the Agentic Finance replay demo")
    parser.add_argument("--thesis", required=True, help="Thesis ID from examples/sample_theses.json.")
    parser.add_argument("--replay", type=Path, default=None, help="Recorded replay fixture path.")
    parser.add_argument("--theses", type=Path, default=None, help="Thesis config JSON path.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional runtime output directory.")
    parser.add_argument("--broker", choices=("sim", "alpaca"), default="sim", help="Paper broker adapter.")
    parser.add_argument(
        "--submit-paper-order",
        action="store_true",
        help="For --broker alpaca only: submit a guarded paper order after all checks pass.",
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
        help="Confirm explicit human approval for guarded Alpaca paper submission.",
    )
    parser.add_argument(
        "--max-notional-usd",
        type=float,
        default=DEFAULT_PAPER_SUBMISSION_NOTIONAL_CAP_USD,
        help="Maximum Alpaca paper order notional for the guarded optional path.",
    )
    parser.add_argument(
        "--symbol-allowlist",
        default=",".join(DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST),
        help="Comma-separated symbols allowed for guarded Alpaca paper submission.",
    )
    return parser


def print_sim_preview(preview: dict[str, Any]) -> None:
    print()
    print("PAPER ORDER PREVIEW")
    print("BROKER: SimBroker")
    print(f"SYMBOL: {preview['symbol']}")
    print(f"SIDE: {preview['side'].upper()}")
    print(f"NOTIONAL: {format_notional(preview['notional'])}")


def prompt_for_sim_confirmation(workflow: dict[str, Any], preview: dict[str, Any]) -> str:
    decision = workflow["multi_leg_decision"]
    print(f"VERDICT: {decision.verdict}")
    print(workflow["memo_markdown"].strip())
    print_sim_preview(preview)
    return input("Confirm simulated paper trade? y/N ")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_paper_trader(
            thesis_id=args.thesis,
            replay_path=args.replay,
            theses_path=args.theses,
            output_dir=args.output_dir,
            broker_name=args.broker,
            submit_paper_order=args.submit_paper_order,
            confirm_paper_trading=args.confirm_paper_trading,
            confirm_not_financial_advice=args.confirm_not_financial_advice,
            confirm_human_approval=args.confirm_human_approval,
            max_notional_usd=args.max_notional_usd,
            symbol_allowlist=parse_symbol_allowlist(args.symbol_allowlist),
            confirmation_fn=prompt_for_sim_confirmation,
        )
    except AlpacaPaperAuthError as exc:
        print(f"Alpaca paper authentication failed: {redact(str(exc))}", file=sys.stderr)
        return 1
    except AlpacaPaperError as exc:
        print(f"Alpaca paper workflow failed: {redact(str(exc))}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Tier 3 paper trader failed: {redact(str(exc))}", file=sys.stderr)
        return 1

    decision = result["multi_leg_decision"]
    if result["broker"] == "sim" and not decision.cleared_for_paper_preview:
        print(f"VERDICT: {decision.verdict}")
        print(result["memo_markdown"].strip())
    if result["broker"] == "sim" and decision.cleared_for_paper_preview:
        if result["broker_event"] == "human_declined":
            print()
            print("human_declined")
            print(f"audit_log: {result['paths']['decisions_log']}")
        elif result["broker_event"] == "simulated_fill_recorded":
            print()
            print(f"simulated_order_id: {result['broker_result']['simulated_order_id']}")
            print(f"paper_portfolio: {result['paths']['paper_portfolio']}")
            print(f"audit_log: {result['paths']['decisions_log']}")
    elif result["broker"] == "alpaca":
        print(f"VERDICT: {decision.verdict}")
        print(result["memo_markdown"].strip())
    if result["broker"] == "alpaca" and result["mode"] == "alpaca_paper_submission":
        print(f"paper_submission_status: {result['submission_result']['status']}")
        print(f"paper_submission_result: {result['paths']['paper_submission_result']}")
        print(f"audit_log: {result['paths']['audit_log']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
