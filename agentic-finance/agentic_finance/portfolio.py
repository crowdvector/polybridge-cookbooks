from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import build_evidence_packet, fetch_live_evidence, load_json, utc_now_iso
from .models import ALLOWED_USE, EvidencePacket, FinancialActionIntent, GateDecision, to_jsonable
from .polybridge import PolyBridgeClient


@dataclass(frozen=True)
class Holding:
    symbol: str
    name: str
    quantity: float
    notional_usd: float
    sector: str
    schema_version: str = "portfolio_holding.v1"


@dataclass(frozen=True)
class PortfolioExposure:
    exposure_id: str
    label: str
    risk_theme: str
    drivers: tuple[str, ...]
    affected_symbols: tuple[str, ...]
    affected_notional_usd: float
    portfolio_weight: float
    forecast_question: str
    search_query: str
    source_rules: tuple[str, ...]
    schema_version: str = "portfolio_exposure.v1"


@dataclass(frozen=True)
class PortfolioRiskItem:
    exposure: PortfolioExposure
    evidence_packet: EvidencePacket
    gate_decision: GateDecision
    risk_band: str
    schema_version: str = "portfolio_risk_item.v1"


@dataclass(frozen=True)
class ExposureRule:
    exposure_id: str
    label: str
    risk_theme: str
    drivers: tuple[str, ...]
    sectors: tuple[str, ...]
    symbols: tuple[str, ...]
    forecast_question: str
    search_query: str


EXPOSURE_RULES: tuple[ExposureRule, ...] = (
    ExposureRule(
        exposure_id="rates",
        label="Rates and inflation sensitivity",
        risk_theme="Policy-rate, inflation, Treasury-volatility, and dollar-rate pressure.",
        drivers=("rates", "inflation", "Fed policy", "Treasury volatility", "dollar/rates"),
        sectors=("broad_equity", "technology", "rates", "gold"),
        symbols=("SPY", "QQQ", "TLT", "GLD"),
        forecast_question="Will US rates or inflation pressure remain elevated over the next 90 days?",
        search_query="US rates inflation Treasury volatility prediction market evidence next 90 days",
    ),
    ExposureRule(
        exposure_id="volatility",
        label="Equity volatility and geopolitical risk",
        risk_theme="Broad equity volatility, tariff/geopolitical risk, and defensive-asset sensitivity.",
        drivers=("volatility", "tariff/geopolitical risk", "geopolitical escalation"),
        sectors=("broad_equity", "technology", "gold"),
        symbols=("SPY", "QQQ", "GLD"),
        forecast_question="Will US equity volatility or geopolitical market stress rise over the next 90 days?",
        search_query="US equity volatility geopolitical market stress prediction market evidence",
    ),
    ExposureRule(
        exposure_id="ai_regulation",
        label="AI regulation and technology policy",
        risk_theme="AI regulation, China/Taiwan, export controls, and rate sensitivity for technology holdings.",
        drivers=("AI regulation", "China/Taiwan", "export controls", "rates"),
        sectors=("technology",),
        symbols=("QQQ", "AAPL", "MSFT", "NVDA"),
        forecast_question="Will AI regulation or export-control risk materially affect large-cap technology over the next 90 days?",
        search_query="AI regulation export controls China Taiwan technology prediction market evidence",
    ),
    ExposureRule(
        exposure_id="energy",
        label="Energy and shipping disruption",
        risk_theme="Oil shock, Middle East escalation, sanctions, and shipping-disruption sensitivity.",
        drivers=("oil shock", "Middle East escalation", "sanctions", "shipping disruption"),
        sectors=("energy",),
        symbols=("XLE",),
        forecast_question="Will oil-shock or shipping-disruption risk remain elevated over the next 90 days?",
        search_query="oil shock Middle East escalation sanctions shipping disruption prediction market evidence",
    ),
)


def parse_holdings_csv(path: Path) -> tuple[Holding, ...]:
    required = {"symbol", "name", "quantity", "notional_usd", "sector"}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(required - fieldnames)
        if missing:
            raise ValueError(f"Holdings CSV is missing required column(s): {', '.join(missing)}")

        holdings: list[Holding] = []
        for line_number, row in enumerate(reader, start=2):
            symbol = (row.get("symbol") or "").strip().upper()
            name = (row.get("name") or "").strip()
            sector = (row.get("sector") or "").strip().lower()
            if not symbol or not name or not sector:
                raise ValueError(f"Holdings CSV row {line_number} has an empty symbol, name, or sector.")
            try:
                quantity = float(row.get("quantity", ""))
                notional_usd = float(row.get("notional_usd", ""))
            except ValueError as exc:
                raise ValueError(f"Holdings CSV row {line_number} has invalid numeric values.") from exc
            if quantity < 0 or notional_usd < 0:
                raise ValueError(f"Holdings CSV row {line_number} must not contain negative values.")
            holdings.append(
                Holding(
                    symbol=symbol,
                    name=name,
                    quantity=quantity,
                    notional_usd=round(notional_usd, 2),
                    sector=sector,
                )
            )
    return tuple(holdings)


def _matches_rule(holding: Holding, rule: ExposureRule) -> bool:
    return holding.symbol in rule.symbols or holding.sector in rule.sectors


def map_holdings_to_exposures(holdings: tuple[Holding, ...]) -> tuple[PortfolioExposure, ...]:
    total_notional = sum(holding.notional_usd for holding in holdings)
    exposures: list[PortfolioExposure] = []
    for rule in EXPOSURE_RULES:
        matched = tuple(holding for holding in holdings if _matches_rule(holding, rule))
        if not matched:
            continue
        affected_notional = round(sum(holding.notional_usd for holding in matched), 2)
        source_rules = tuple(
            f"{holding.symbol}:{holding.sector}" for holding in matched if _matches_rule(holding, rule)
        )
        exposures.append(
            PortfolioExposure(
                exposure_id=rule.exposure_id,
                label=rule.label,
                risk_theme=rule.risk_theme,
                drivers=rule.drivers,
                affected_symbols=tuple(holding.symbol for holding in matched),
                affected_notional_usd=affected_notional,
                portfolio_weight=round(affected_notional / total_notional, 6) if total_notional else 0.0,
                forecast_question=rule.forecast_question,
                search_query=rule.search_query,
                source_rules=source_rules,
            )
        )
    return tuple(exposures)


def exposure_to_intent(exposure: PortfolioExposure) -> FinancialActionIntent:
    symbols = ", ".join(exposure.affected_symbols)
    return FinancialActionIntent(
        scenario_id=f"portfolio_event_risk_{exposure.exposure_id}",
        thesis=(
            f"Read-only portfolio event-risk review for {exposure.label}. "
            f"Affected holdings: {symbols}."
        ),
        symbol="PORTFOLIO",
        exposure_direction="risk_monitoring",
        notional_usd=exposure.affected_notional_usd,
        forecast_question=exposure.forecast_question,
        search_query=exposure.search_query,
        allowed_use=ALLOWED_USE,
    )


def load_offline_portfolio_evidence(exposure: PortfolioExposure, fixtures_dir: Path) -> EvidencePacket:
    intent = exposure_to_intent(exposure)
    forecast_response = load_json(fixtures_dir / f"{exposure.exposure_id}_forecast.response.json")
    search_response = load_json(fixtures_dir / f"{exposure.exposure_id}_search.response.json")
    return build_evidence_packet(intent, forecast_response, search_response)


def fetch_live_portfolio_evidence(exposure: PortfolioExposure, client: PolyBridgeClient) -> EvidencePacket:
    return fetch_live_evidence(exposure_to_intent(exposure), client)


def risk_band(packet: EvidencePacket, decision: GateDecision) -> str:
    if decision.decision.startswith("blocked"):
        return "blocked"
    if packet.probability is None:
        return "unknown"
    if packet.probability >= 0.65:
        return "high_event_risk"
    if packet.probability >= 0.55:
        return "elevated_event_risk"
    if packet.probability <= 0.35:
        return "lower_event_risk"
    return "monitor"


def build_portfolio_risk_map(
    run_id: str,
    holdings: tuple[Holding, ...],
    exposures: tuple[PortfolioExposure, ...],
    risk_items: tuple[PortfolioRiskItem, ...],
    created_at: str | None = None,
) -> dict[str, Any]:
    total_notional = round(sum(holding.notional_usd for holding in holdings), 2)
    return {
        "schema_version": "portfolio_risk_map.v1",
        "run_id": run_id,
        "created_at": created_at or utc_now_iso(),
        "tier": "portfolio_event_risk_map",
        "allowed_use": ALLOWED_USE,
        "portfolio": {
            "holding_count": len(holdings),
            "total_notional_usd": total_notional,
            "symbols": [holding.symbol for holding in holdings],
        },
        "methodology": {
            "mapping": "deterministic_local_rules",
            "adapter_boundary": "EvidencePacket",
            "probability_source": "forecast_only",
            "search_relevance_use": "metadata_only",
            "raw_polybridge_responses_persisted": False,
        },
        "exposures": [to_jsonable(exposure) for exposure in exposures],
        "risk_items": [to_jsonable(item) for item in risk_items],
        "guardrails": {
            "read_only_portfolio_workflow": True,
            "local_holdings_csv": True,
            "no_live_broker_calls": True,
            "no_broker_submission": True,
            "no_real_money_trading_path": True,
        },
    }


def _format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1%}"


def generate_portfolio_risk_memo(
    holdings: tuple[Holding, ...],
    exposures: tuple[PortfolioExposure, ...],
    risk_items: tuple[PortfolioRiskItem, ...],
    risk_map: dict[str, Any],
) -> str:
    total_notional = risk_map["portfolio"]["total_notional_usd"]
    holding_lines = [
        f"- {holding.symbol}: {holding.name}; sector `{holding.sector}`; notional ${holding.notional_usd:,.2f}."
        for holding in holdings
    ]
    if not holding_lines:
        holding_lines.append("- No holdings were provided.")

    exposure_lines = []
    for exposure in exposures:
        exposure_lines.append(
            f"- {exposure.label}: {', '.join(exposure.affected_symbols)}; "
            f"drivers: {', '.join(exposure.drivers)}; "
            f"portfolio weight {_format_percent(exposure.portfolio_weight)}."
        )

    item_lines = []
    for item in risk_items:
        packet = item.evidence_packet
        decision = item.gate_decision
        item_lines.append(
            f"- {item.exposure.label}: probability {_format_percent(packet.probability)}, "
            f"confidence {_format_percent(packet.confidence)}, gate `{decision.decision}`, "
            f"risk band `{item.risk_band}`."
        )

    return f"""# Portfolio Event-Risk Map Memo

## Scope
This read-only memo summarizes event-risk evidence for a local holdings CSV. It is research/demo software output, does not place orders, does not support execution, and does not instruct portfolio changes.

## Portfolio Snapshot
- Holdings: {len(holdings)}
- Total notional: ${total_notional:,.2f}

{chr(10).join(holding_lines)}

## Deterministic Exposure Mapping
{chr(10).join(exposure_lines)}

## Evidence Gate Results
{chr(10).join(item_lines)}

## Methodology
- Holdings are mapped with deterministic local rules.
- Search relevance is retained only as metadata.
- Forecast output is the only probability source.
- Gate logic receives normalized EvidencePackets, not raw PolyBridge responses.

## Guardrails
- Read-only portfolio workflow.
- Local holdings CSV only.
- No broker connection.
- No order submission.
- No real-money execution path.
"""
