from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from agentic_finance.brokers.alpaca import (
    AlpacaPaperAuthError,
    AlpacaPaperClient,
    AlpacaPaperError,
    read_alpaca_paper_config_from_env,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optional Alpaca paper validation for Agentic Finance")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--preview-only",
        action="store_true",
        help="Run offline Evidence Gate and write a local paper preview without Alpaca credentials.",
    )
    mode.add_argument(
        "--validate-paper-account",
        action="store_true",
        help="Validate Alpaca paper credentials with GET /v2/account only.",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional runtime output directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.preview_only:
            result = run_preview_only(output_dir=args.output_dir)
        else:
            result = run_validate_paper_account(output_dir=args.output_dir)
    except AlpacaPaperAuthError as exc:
        print(f"Alpaca paper authentication failed: {redact(str(exc))}", file=sys.stderr)
        return 1
    except AlpacaPaperError as exc:
        print(f"Alpaca paper validation failed: {redact(str(exc))}", file=sys.stderr)
        return 1

    for label, path in result["paths"].items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
