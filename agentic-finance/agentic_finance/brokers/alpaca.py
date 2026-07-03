from __future__ import annotations

from datetime import datetime, timezone

from ..models import ALLOWED_USE, FinancialActionIntent, GateDecision, PaperOrderPreview


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def alpaca_side_for_intent(intent: FinancialActionIntent) -> str:
    mapping = {
        "increase_long_exposure": "buy",
        "decrease_long_exposure": "sell",
        "reduce_exposure": "sell",
    }
    try:
        return mapping[intent.exposure_direction]
    except KeyError as exc:
        raise ValueError(f"Unsupported exposure direction for paper preview: {intent.exposure_direction}") from exc


def create_paper_order_preview(
    intent: FinancialActionIntent,
    gate_decision: GateDecision,
    created_at: str | None = None,
) -> PaperOrderPreview:
    if not gate_decision.cleared_for_paper_preview:
        raise ValueError("Paper order preview requires a cleared evidence gate decision.")
    if intent.notional_usd <= 0:
        raise ValueError("Paper order preview requires a positive notional value.")
    return PaperOrderPreview(
        symbol=intent.symbol,
        side=alpaca_side_for_intent(intent),
        notional_usd=round(float(intent.notional_usd), 2),
        created_at=created_at or utc_now_iso(),
        human_approval_required=True,
        submit_supported=False,
        allowed_use=ALLOWED_USE,
    )
