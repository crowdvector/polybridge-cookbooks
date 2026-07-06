from __future__ import annotations

from datetime import datetime, timezone

from .models import ALLOWED_USE, DecisionMemo, EvidencePacket, FinancialActionIntent, GateDecision

DISCLAIMER = (
    "This memo is research/demo software output, not financial advice. It does not place orders, "
    "does not support real-money execution, and permits only paper-preview review by a human."
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1%}"


def generate_decision_memo(
    intent: FinancialActionIntent,
    packet: EvidencePacket,
    decision: GateDecision,
    created_at: str | None = None,
) -> DecisionMemo:
    source_lines = []
    for market in packet.source_markets:
        proxy = "proxy" if market.is_proxy else "direct"
        probability = format_percent(market.probability)
        url = f" ({market.url})" if market.url else ""
        source_lines.append(f"- {market.source}: {market.question}{url}; probability {probability}; {proxy}.")
    if not source_lines:
        source_lines.append("- No source markets were available in the normalized evidence packet.")

    interval = packet.confidence_interval or {}
    interval_text = "n/a"
    if {"lower", "upper"} <= set(interval):
        interval_text = f"{format_percent(interval['lower'])} to {format_percent(interval['upper'])}"

    reasons = "\n".join(f"- {reason}" for reason in decision.reasons)
    quality_flags = ", ".join(packet.quality_flags) if packet.quality_flags else "none"

    markdown = f"""# Agentic Finance Evidence Gate Memo

## Thesis
{intent.thesis}

## Forecast Question
{packet.question}

## Evidence Summary
- Probability: {format_percent(packet.probability)}
- Confidence: {format_percent(packet.confidence)}
- Confidence interval: {interval_text}
- Evidence profile: {packet.evidence_profile.get("forecast_evidence_type", "unspecified")}
- Quality flags: {quality_flags}

## Gate Decision
`{decision.decision}`

## Reasons
{reasons}

## Source Markets
{chr(10).join(source_lines)}

## Allowed Use
`{ALLOWED_USE}`

## Next Step
{decision.next_step}

## Disclaimer
{DISCLAIMER}
"""

    return DecisionMemo(
        memo_id=f"memo_{packet.packet_id.removeprefix('ep_')}",
        created_at=created_at or utc_now_iso(),
        scenario_id=intent.scenario_id,
        markdown=markdown,
        allowed_use=ALLOWED_USE,
    )
