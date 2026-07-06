#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from agentic_finance.multileg import run_multileg_replay_workflow
from agentic_finance.redaction import redact


def default_base_dir() -> Path:
    return Path(__file__).resolve().parent


def default_theses_path(base_dir: Path) -> Path:
    return base_dir / "examples" / "sample_theses.json"


def default_replay_path(base_dir: Path) -> Path:
    return base_dir / "examples" / "recorded_run_2026-07-04.json"


def run_replay(
    *,
    thesis_id: str,
    replay_path: str | Path | None = None,
    theses_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    base = base_dir or default_base_dir()
    replay = Path(replay_path) if replay_path is not None else default_replay_path(base)
    theses = Path(theses_path) if theses_path is not None else default_theses_path(base)
    output = Path(output_dir) if output_dir is not None else None
    return run_multileg_replay_workflow(
        thesis_id=thesis_id,
        theses_path=theses,
        replay_path=replay,
        base_dir=base,
        output_dir=output,
        create_preview=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tier 1 multi-leg Agentic Finance Evidence Gate replay")
    parser.add_argument("--thesis", required=True, help="Thesis ID from examples/sample_theses.json.")
    parser.add_argument("--replay", type=Path, default=None, help="Recorded replay fixture path.")
    parser.add_argument("--theses", type=Path, default=None, help="Thesis config JSON path.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional runtime output directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_replay(
            thesis_id=args.thesis,
            replay_path=args.replay,
            theses_path=args.theses,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        print(f"Tier 1 replay failed: {redact(str(exc))}", file=sys.stderr)
        return 1

    decision = result["multi_leg_decision"]
    print(f"Verdict: {decision.verdict}")
    print(f"Weighted support: {decision.weighted_support:.1f}")
    print(f"Direct-evidence legs: {decision.direct_evidence_legs}")
    print(result["memo_markdown"].strip())
    for label, path in result["paths"].items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
