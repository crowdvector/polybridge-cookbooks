from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any

ALLOWED_USE = "research_only_not_financial_advice"


@dataclass(frozen=True)
class FinancialActionIntent:
    scenario_id: str
    thesis: str
    symbol: str
    exposure_direction: str
    notional_usd: float
    forecast_question: str
    search_query: str
    schema_version: str = "financial_action_intent.v1"
    allowed_use: str = ALLOWED_USE


@dataclass(frozen=True)
class SourceMarket:
    source: str
    question: str
    url: str | None = None
    probability: float | None = None
    relevance: float | None = None
    is_proxy: bool = False
    schema_version: str = "source_market.v1"


@dataclass(frozen=True)
class EvidencePacket:
    packet_id: str
    created_at: str
    scenario_id: str
    question: str
    probability: float | None
    confidence: float | None
    confidence_interval: dict[str, float] | None
    evidence_profile: dict[str, Any]
    source_markets: tuple[SourceMarket, ...]
    reasoning_summary: str
    quality_flags: tuple[str, ...]
    raw_response_sha256: str
    schema_version: str = "evidence_packet.v1"
    allowed_use: str = ALLOWED_USE


@dataclass(frozen=True)
class GateConfig:
    min_confidence: float = 0.55
    max_interval_width: float = 0.35
    min_source_markets: int = 1
    allow_proxy_only: bool = False
    schema_version: str = "gate_config.v1"
    allowed_use: str = ALLOWED_USE


@dataclass(frozen=True)
class GateDecision:
    decision: str
    cleared_for_paper_preview: bool
    reasons: tuple[str, ...]
    next_step: str
    config_snapshot: dict[str, Any]
    schema_version: str = "gate_decision.v1"
    allowed_use: str = ALLOWED_USE


@dataclass(frozen=True)
class DecisionMemo:
    memo_id: str
    created_at: str
    scenario_id: str
    markdown: str
    schema_version: str = "decision_memo.v1"
    allowed_use: str = ALLOWED_USE


@dataclass(frozen=True)
class PaperOrderPreview:
    symbol: str
    side: str
    notional_usd: float
    created_at: str
    broker: str = "alpaca"
    mode: str = "paper_preview_only"
    human_approval_required: bool = True
    submit_supported: bool = False
    schema_version: str = "paper_order_preview.v1"
    allowed_use: str = ALLOWED_USE


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value
