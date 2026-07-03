#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

from agentic_finance.cli import main, run_offline_workflow


def run_offline(output_dir: str | Path | None = None) -> dict[str, Any]:
    path = Path(output_dir) if output_dir is not None else None
    return run_offline_workflow(output_dir=path)


if __name__ == "__main__":
    raise SystemExit(main())
