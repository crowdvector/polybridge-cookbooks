from __future__ import annotations

from .models import EvidencePacket, GateConfig, GateDecision, to_jsonable

NEUTRAL_LOW = 0.45
NEUTRAL_HIGH = 0.55
FETCH_FAILURE_FLAGS = {
    "api_error",
    "forecast_error",
    "search_error",
    "search_unavailable",
    "evidence_fetch_error",
}


def interval_width(packet: EvidencePacket) -> float | None:
    if packet.confidence_interval is None:
        return None
    return round(packet.confidence_interval["upper"] - packet.confidence_interval["lower"], 6)


def source_market_count(packet: EvidencePacket) -> int:
    return len(packet.source_markets)


def fetch_failure_flags(packet: EvidencePacket) -> tuple[str, ...]:
    return tuple(flag for flag in packet.quality_flags if flag in FETCH_FAILURE_FLAGS)


def apply_gate(packet: EvidencePacket, config: GateConfig | None = None) -> GateDecision:
    config = config or GateConfig()
    reasons: list[str] = []

    failures = fetch_failure_flags(packet)
    if failures:
        return GateDecision(
            decision="blocked_api_error",
            cleared_for_paper_preview=False,
            reasons=(f"The evidence fetch recorded failure flag(s): {', '.join(failures)}.",),
            next_step="Stop before any broker-format object and inspect the evidence source.",
            config_snapshot=to_jsonable(config),
        )

    if packet.probability is None:
        reasons.append("No normalized forecast probability is available.")
    if packet.confidence is None:
        reasons.append("No normalized confidence score is available.")
    width = interval_width(packet)
    if width is None:
        reasons.append("No usable confidence interval is available.")
    if source_market_count(packet) < config.min_source_markets:
        reasons.append(
            f"Only {source_market_count(packet)} source market(s) were available; "
            f"{config.min_source_markets} required."
        )
    if reasons:
        return GateDecision(
            decision="blocked_insufficient_evidence",
            cleared_for_paper_preview=False,
            reasons=tuple(reasons),
            next_step="Create a memo only after stronger evidence is available.",
            config_snapshot=to_jsonable(config),
        )

    weak_reasons: list[str] = []
    if packet.confidence is not None and packet.confidence < config.min_confidence:
        weak_reasons.append(
            f"Confidence {packet.confidence:.2f} is below the {config.min_confidence:.2f} threshold."
        )
    if width is not None and width > config.max_interval_width:
        weak_reasons.append(
            f"Confidence interval width {width:.2f} is above the {config.max_interval_width:.2f} limit."
        )
    if packet.evidence_profile.get("proxy_only") and not config.allow_proxy_only:
        weak_reasons.append("Evidence is proxy-only and the gate requires at least one direct source.")
    if weak_reasons:
        return GateDecision(
            decision="blocked_weak_evidence",
            cleared_for_paper_preview=False,
            reasons=tuple(weak_reasons),
            next_step="Keep the scenario in memo form until evidence quality improves.",
            config_snapshot=to_jsonable(config),
        )

    if packet.probability is not None and NEUTRAL_LOW <= packet.probability <= NEUTRAL_HIGH:
        return GateDecision(
            decision="watchlist_only",
            cleared_for_paper_preview=False,
            reasons=("Forecast probability sits in the neutral watchlist band.",),
            next_step="Track the scenario and refresh evidence before creating any broker-format object.",
            config_snapshot=to_jsonable(config),
        )

    if packet.evidence_profile.get("memo_only"):
        return GateDecision(
            decision="memo_only",
            cleared_for_paper_preview=False,
            reasons=("Evidence is marked for memo-only handling by the normalized profile.",),
            next_step="Write the decision memo without creating a paper-preview object.",
            config_snapshot=to_jsonable(config),
        )

    return GateDecision(
        decision="cleared_for_paper_preview",
        cleared_for_paper_preview=True,
        reasons=(
            "Evidence meets the configured confidence, interval, and source-market thresholds.",
            "The result permits only a local paper-preview object for human review.",
        ),
        next_step="Create a paper-preview object for explicit human review.",
        config_snapshot=to_jsonable(config),
    )
