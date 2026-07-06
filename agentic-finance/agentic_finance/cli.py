from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .multileg import run_multileg_replay_workflow
from .redaction import redact


DEFAULT_THESIS_ID = "labor-resilience-jul2026"


def default_base_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def run_offline_workflow(
    base_dir: Path | None = None,
    fixtures_dir: Path | None = None,
    output_dir: Path | None = None,
    thesis_id: str = DEFAULT_THESIS_ID,
) -> dict[str, Any]:
    base = base_dir or default_base_dir()
    return run_multileg_replay_workflow(
        thesis_id=thesis_id,
        theses_path=base / "examples" / "sample_theses.json",
        replay_path=base / "examples" / "recorded_run_2026-07-04.json",
        base_dir=base,
        output_dir=output_dir,
        create_preview=False,
    )


def run_live_polybridge_workflow(*args: Any, **kwargs: Any) -> dict[str, Any]:
    raise RuntimeError("Use recorded replay mode for this launch demo.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agentic Finance Evidence Gate replay")
    parser.add_argument("--offline", action="store_true", help="Run the recorded replay workflow. This is the default.")
    parser.add_argument("--live-polybridge", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--thesis", default=DEFAULT_THESIS_ID, help="Thesis ID from examples/sample_theses.json.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Optional runtime output directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.live_polybridge:
        print("Recorded replay mode is the supported launch path for this demo.", file=sys.stderr)
        return 1
    try:
        result = run_offline_workflow(output_dir=args.output_dir, thesis_id=args.thesis)
    except Exception as exc:
        print(f"Evidence Gate replay failed: {redact(str(exc))}", file=sys.stderr)
        return 1

    decision = result["multi_leg_decision"]
    print(f"Verdict: {decision.verdict}")
    print(f"Weighted support: {decision.weighted_support:.1f}")
    for label, path in result["paths"].items():
        print(f"{label}: {path}")
    return 0
