from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .audit import audit_path
from .models import ALLOWED_USE, FinancialActionIntent, to_jsonable
from .redaction import redact


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class BrokerOrder:
    thesis_id: str
    symbol: str
    side: str
    notional: str
    schema_version: str = "broker_order.v1"
    allowed_use: str = ALLOWED_USE


class Broker(Protocol):
    def preview(self, order: BrokerOrder) -> dict[str, Any]:
        ...

    def submit(self, order: BrokerOrder) -> dict[str, Any]:
        ...


def side_for_intent(intent: FinancialActionIntent) -> str:
    mapping = {
        "increase_long_exposure": "buy",
        "decrease_long_exposure": "sell",
        "reduce_exposure": "sell",
    }
    try:
        return mapping[intent.exposure_direction]
    except KeyError as exc:
        raise ValueError(f"Unsupported exposure direction for paper order: {intent.exposure_direction}") from exc


def order_from_intent(intent: FinancialActionIntent) -> BrokerOrder:
    return BrokerOrder(
        thesis_id=intent.scenario_id,
        symbol=intent.symbol.strip().upper(),
        side=side_for_intent(intent),
        notional=f"{float(intent.notional_usd):.2f}",
    )


def write_jsonl(path: Path, record: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact(record), sort_keys=True) + "\n")
    return path


class SimBroker:
    broker_name = "SimBroker"

    def __init__(self, output_dir: Path, now: str | None = None) -> None:
        self.output_dir = output_dir
        self.now = now

    def preview(self, order: BrokerOrder) -> dict[str, Any]:
        return {
            "schema_version": "sim_broker_preview.v1",
            "broker": "sim",
            "broker_name": self.broker_name,
            "mode": "simulated_paper_preview",
            "thesis_id": order.thesis_id,
            "symbol": order.symbol,
            "side": order.side,
            "notional": order.notional,
            "allowed_use": ALLOWED_USE,
            "no_api_keys_required": True,
            "no_brokerage_account_required": True,
            "no_network_calls": True,
            "no_live_trading": True,
            "human_confirmation_required": True,
        }

    def submit(self, order: BrokerOrder) -> dict[str, Any]:
        timestamp = self.now or utc_now_iso()
        record = {
            "schema_version": "simulated_paper_fill.v1",
            "thesis_id": order.thesis_id,
            "symbol": order.symbol,
            "side": order.side,
            "notional": order.notional,
            "timestamp": timestamp,
            "broker": "sim",
            "simulated_order_id": f"sim_{uuid.uuid4().hex[:12]}",
            "allowed_use": ALLOWED_USE,
            "no_live_trading": True,
        }
        write_jsonl(self.output_dir / "paper_portfolio.jsonl", record)
        return record


def build_sim_broker_audit_record(
    *,
    base_dir: Path,
    run_id: str,
    thesis_id: str,
    order: BrokerOrder,
    preview: dict[str, Any],
    event: str,
    paper_portfolio_path: Path | None = None,
    simulated_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return redact(
        {
            "schema_version": "sim_broker_audit_record.v1",
            "run_id": run_id,
            "timestamp": utc_now_iso(),
            "tier": "sim_broker_paper_trade",
            "scenario_id": thesis_id,
            "broker": "sim",
            "event": event,
            "order": to_jsonable(order),
            "preview": preview,
            "paper_portfolio_path": audit_path(paper_portfolio_path, base_dir),
            "simulated_result": simulated_result,
            "guardrails": {
                "no_brokerage_account_required": True,
                "no_api_keys_required": True,
                "no_network_calls": True,
                "no_live_trading": True,
                "human_confirmation_required": True,
                "secrets_redacted": True,
            },
            "allowed_use": ALLOWED_USE,
        }
    )
