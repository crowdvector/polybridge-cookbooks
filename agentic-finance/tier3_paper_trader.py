#!/usr/bin/env python3
from __future__ import annotations

import sys

MIN_PYTHON = (3, 9)
if sys.version_info < MIN_PYTHON:
    sys.stderr.write(
        "This demo needs Python 3.9 or newer. Try python3 --version, install a newer Python, "
        "or run the notebook in Colab.\n"
    )
    raise SystemExit(1)

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from agentic_finance.broker import (
    SimBroker,
    build_sim_broker_audit_record,
    order_from_intent,
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


def format_notional(notional_usd: float) -> str:
    value = float(notional_usd)
    if value.is_integer():
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def leg_summaries(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    decision = workflow["multi_leg_decision"]
    return [
        {
            "question": leg.question,
            "probability": leg.probability,
            "threshold": leg.threshold,
            "supports_when": leg.supports_when,
            "classification": leg.classification,
            "weight": leg.weight,
        }
        for leg in decision.leg_decisions
    ]


def run_paper_trader(
    *,
    thesis_id: str,
    replay_path: str | Path | None = None,
    theses_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    confirmation: str | None = None,
    input_fn: Callable[[str], str] = input,
    confirmation_fn: Callable[[dict[str, Any], dict[str, Any]], str] | None = None,
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
    if not decision.cleared_for_paper_preview:
        return {"mode": "sim_broker", "broker": "sim", "broker_event": "skipped_decline", **workflow}

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
            mode="sim_broker",
            verdict=decision.verdict,
            leg_summaries=leg_summaries(workflow),
            order=order,
            preview=preview,
            human_decision="human_declined",
            output_paths=paths,
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
    paths["simulated_order_result"] = result_path
    paths["paper_portfolio"] = paper_portfolio_path
    audit_record = build_sim_broker_audit_record(
        base_dir=base,
        run_id=workflow["run_id"],
        thesis_id=workflow["thesis"].thesis_id,
        mode="sim_broker",
        verdict=decision.verdict,
        leg_summaries=leg_summaries(workflow),
        order=order,
        preview=preview,
        human_decision="approved",
        paper_portfolio_path=paper_portfolio_path,
        simulated_result=simulated_result,
        output_paths=paths,
    )
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
    parser = argparse.ArgumentParser(
        prog="python3 tier3_paper_trader.py",
        description="Tier 3 SimBroker paper trader for the Agentic Finance replay demo",
    )
    parser.add_argument("--thesis", required=True, help="Thesis ID from examples/sample_theses.json.")
    parser.add_argument("--replay", type=Path, default=None, help="Recorded replay fixture path.")
    parser.add_argument("--theses", type=Path, default=None, help="Thesis config JSON path.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional runtime output directory.")
    return parser


def print_sim_preview(preview: dict[str, Any]) -> None:
    print()
    print("PAPER ORDER PREVIEW")
    print("BROKER: SimBroker")
    print(f"SYMBOL: {preview['symbol']}")
    print(f"SIDE: {preview['side'].upper()}")
    print(f"NOTIONAL: {format_notional(preview['notional_usd'])}")


def prompt_for_sim_confirmation(workflow: dict[str, Any], preview: dict[str, Any]) -> str:
    decision = workflow["multi_leg_decision"]
    print(f"VERDICT: {decision.verdict}")
    print()
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
            confirmation_fn=prompt_for_sim_confirmation,
        )
    except Exception as exc:
        print(f"Tier 3 paper trader failed: {redact(str(exc))}", file=sys.stderr)
        return 1

    decision = result["multi_leg_decision"]
    if not decision.cleared_for_paper_preview:
        print(f"VERDICT: {decision.verdict}")
        print()
        print(result["memo_markdown"].strip())
        print(f"audit_log: {result['paths']['decisions_log']}")
        return 0

    if result["broker_event"] == "human_declined":
        print()
        print("human_declined")
        print(f"audit_log: {result['paths']['decisions_log']}")
    elif result["broker_event"] == "simulated_fill_recorded":
        print()
        print(f"simulated_order_id: {result['broker_result']['order_id']}")
        print(f"paper_portfolio: {result['paths']['paper_portfolio']}")
        print(f"audit_log: {result['paths']['decisions_log']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
