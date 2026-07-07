from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import audit_path
from .evidence import (
    canonical_sha256,
    first_present,
    normalize_interval,
    normalize_source_market,
    normalize_unit_interval,
)
from .models import (
    ALLOWED_USE,
    EvidencePacket,
    FinancialActionIntent,
    GateDecision,
    SourceMarket,
    to_jsonable,
)
from .redaction import redact


MARGIN = 0.15
MIN_WEIGHTED_SUPPORT = 2.0
DIRECT_EVIDENCE_PROFILES = {"direct_only", "direct_mixed"}
PROXY_ONLY_PROFILE = "proxy_only"
KNOWN_EVIDENCE_PROFILES = DIRECT_EVIDENCE_PROFILES | {PROXY_ONLY_PROFILE}
LIVE_MODE_NOTICE = "Live mode: asking PolyBridge fresh. 30 to 50 seconds per question."


@dataclass(frozen=True)
class ThesisLeg:
    question: str
    supports_when: str
    threshold: float


@dataclass(frozen=True)
class ThesisConfig:
    thesis_id: str
    as_of: str
    demo: bool
    evergreen: bool
    thesis: str
    instrument: str
    direction: str
    notional_usd: float
    questions: tuple[ThesisLeg, ...]
    note: str | None = None
    schema_version: str = "multi_leg_thesis.v1"
    allowed_use: str = ALLOWED_USE


@dataclass(frozen=True)
class LegDecision:
    question: str
    supports_when: str
    threshold: float
    probability: float | None
    interval: dict[str, float] | None
    evidence_profile: str
    classification: str
    weight: float
    weighted_support: float
    direct_evidence: bool
    full_weight_contradiction: bool
    insufficient_data: bool
    failure: bool
    reasoning_summary: str
    evidence_packet: EvidencePacket
    schema_version: str = "multi_leg_decision.v1"
    allowed_use: str = ALLOWED_USE


@dataclass(frozen=True)
class MultiLegDecision:
    thesis_id: str
    thesis: str
    instrument: str
    direction: str
    notional_usd: float
    verdict: str
    weighted_support: float
    direct_evidence_legs: int
    full_weight_contradictions: tuple[str, ...]
    full_weight_insufficient_legs: tuple[str, ...]
    reasons: tuple[str, ...]
    leg_decisions: tuple[LegDecision, ...]
    margin: float = MARGIN
    min_weighted_support: float = MIN_WEIGHTED_SUPPORT
    schema_version: str = "multi_leg_gate_decision.v1"
    allowed_use: str = ALLOWED_USE

    @property
    def cleared_for_paper_preview(self) -> bool:
        return self.verdict == "PROCEED"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_leg(raw: dict[str, Any]) -> ThesisLeg:
    supports_when = str(raw["supports_when"]).strip().upper()
    if supports_when not in {"YES", "NO"}:
        raise ValueError(f"Unsupported supports_when value: {supports_when}")
    threshold = normalize_unit_interval(raw["threshold"])
    if threshold is None:
        raise ValueError(f"Invalid threshold for question: {raw.get('q')}")
    return ThesisLeg(
        question=str(raw["q"]),
        supports_when=supports_when,
        threshold=threshold,
    )


def parse_thesis(raw: dict[str, Any]) -> ThesisConfig:
    return ThesisConfig(
        thesis_id=str(raw["thesis_id"]),
        as_of=str(raw["as_of"]),
        demo=bool(raw.get("demo", False)),
        evergreen=bool(raw.get("evergreen", False)),
        thesis=str(raw["thesis"]),
        instrument=str(raw["instrument"]).strip().upper(),
        direction=str(raw["direction"]).strip().lower(),
        notional_usd=float(raw["notional_usd"]),
        questions=tuple(parse_leg(item) for item in raw.get("questions", [])),
        note=str(raw["note"]) if raw.get("note") else None,
    )


def load_theses(path: Path) -> dict[str, ThesisConfig]:
    raw = load_json(path)
    if "thesis_id" in raw:
        theses = [raw]
    else:
        theses = raw.get("theses", [])
    if not isinstance(theses, list):
        raise ValueError("sample_theses.json must contain a thesis object or theses list.")
    parsed = {thesis.thesis_id: thesis for thesis in (parse_thesis(item) for item in theses)}
    if not parsed:
        raise ValueError("sample_theses.json did not contain any theses.")
    return parsed


def load_recorded_run(path: Path) -> dict[str, Any]:
    raw = load_json(path)
    if not isinstance(raw.get("theses"), dict):
        raise ValueError("recorded replay must contain a theses object.")
    return raw


def interval_from_list(value: Any) -> dict[str, float] | None:
    if not isinstance(value, list) or len(value) != 2:
        return None
    lower = normalize_unit_interval(value[0])
    upper = normalize_unit_interval(value[1])
    if lower is None or upper is None:
        return None
    if lower > upper:
        lower, upper = upper, lower
    return {"lower": lower, "upper": upper}


def source_market_from_record(raw: dict[str, Any]) -> SourceMarket:
    return SourceMarket(
        source=str(raw.get("source") or "recorded_fixture_market"),
        question=str(raw.get("question") or "Recorded fixture market"),
        url=str(raw["url"]) if raw.get("url") else None,
        probability=normalize_unit_interval(raw.get("probability")),
        relevance=normalize_unit_interval(raw.get("relevance")),
        is_proxy=bool(raw.get("is_proxy", False)),
    )


def base_weight_for_profile(profile: str, insufficient_data: bool, failure: bool) -> float:
    if insufficient_data or failure:
        return 0.0
    if profile in DIRECT_EVIDENCE_PROFILES:
        return 1.0
    if profile == PROXY_ONLY_PROFILE:
        return 0.5
    return 0.0


def classify_probability(
    probability: float | None,
    *,
    supports_when: str,
    threshold: float,
    margin: float = MARGIN,
) -> str:
    if probability is None:
        return "INSUFFICIENT"
    if supports_when == "NO":
        if probability <= threshold:
            return "SUPPORTS"
        if probability >= threshold + margin:
            return "CONTRADICTS"
        return "NEUTRAL"
    if probability >= threshold:
        return "SUPPORTS"
    if probability <= threshold - margin:
        return "CONTRADICTS"
    return "NEUTRAL"


def build_leg_evidence_packet(
    thesis: ThesisConfig,
    leg: ThesisLeg,
    recorded_leg: dict[str, Any],
    *,
    created_at: str | None = None,
) -> EvidencePacket:
    probability = normalize_unit_interval(recorded_leg.get("probability"))
    interval = interval_from_list(recorded_leg.get("interval"))
    profile = str(recorded_leg.get("evidence_profile") or "unspecified")
    source_markets = tuple(
        source_market_from_record(item)
        for item in recorded_leg.get("source_markets", [])
        if isinstance(item, dict)
    )
    failure = bool(recorded_leg.get("failed", False))
    insufficient = bool(recorded_leg.get("insufficient_data", False))
    selected_direct_missing = bool(recorded_leg.get("selected_direct_evidence_missing", False))
    live = bool(recorded_leg.get("live_polybridge", False))
    quality_flags = ["live_polybridge"] if live else ["offline_fixture", "sanitized_fixture", "recorded_replay"]
    if failure:
        quality_flags.append("forecast_error")
    if insufficient:
        quality_flags.append("insufficient_data")
    if selected_direct_missing:
        quality_flags.append("selected_direct_evidence_missing")
    if profile == PROXY_ONLY_PROFILE:
        quality_flags.append("proxy_only")

    packet_source = {
        "thesis_id": thesis.thesis_id,
        "question": leg.question,
        "probability": probability,
        "interval": interval,
        "profile": profile,
        "source_markets": [to_jsonable(market) for market in source_markets],
    }
    raw_hash = canonical_sha256(packet_source)
    return EvidencePacket(
        packet_id=f"ep_{raw_hash[:16]}",
        created_at=created_at or utc_now_iso(),
        scenario_id=thesis.thesis_id,
        question=leg.question,
        probability=probability,
        confidence=normalize_unit_interval(recorded_leg.get("confidence")),
        confidence_interval=interval,
        evidence_profile={
            "fixture_mode": not live,
            "live_polybridge": live,
            "recorded_replay": not live,
            "forecast_status": "error" if failure else "ok",
            "search_status": "ok",
            "forecast_evidence_type": profile,
            "source_market_count": len(source_markets),
            "direct_market_count": int(recorded_leg.get("direct_market_count", 0) or 0),
            "proxy_market_count": int(recorded_leg.get("proxy_market_count", 0) or 0),
            "proxy_only": profile == PROXY_ONLY_PROFILE,
            "selected_direct_evidence_missing": selected_direct_missing,
            "search_relevance_use": "metadata_only",
            "probability_source": "forecast_only",
        },
        source_markets=source_markets,
        reasoning_summary=str(recorded_leg.get("reasoning_summary") or "Recorded replay fixture."),
        quality_flags=tuple(sorted(set(quality_flags))),
        raw_response_sha256=raw_hash,
    )


def classify_leg(thesis: ThesisConfig, leg: ThesisLeg, recorded_leg: dict[str, Any]) -> LegDecision:
    packet = build_leg_evidence_packet(thesis, leg, recorded_leg)
    profile = str(packet.evidence_profile.get("forecast_evidence_type") or "unspecified")
    failure = any(flag.endswith("error") for flag in packet.quality_flags)
    insufficient = "insufficient_data" in packet.quality_flags or packet.probability is None
    weight = base_weight_for_profile(profile, insufficient, failure)
    classification = "INSUFFICIENT" if insufficient or failure else classify_probability(
        packet.probability,
        supports_when=leg.supports_when,
        threshold=leg.threshold,
    )
    weighted_support = weight if classification == "SUPPORTS" else 0.0
    direct_evidence = profile in DIRECT_EVIDENCE_PROFILES and not insufficient and not failure
    full_weight_contradiction = weight == 1.0 and classification == "CONTRADICTS"
    full_weight_insufficient = profile in DIRECT_EVIDENCE_PROFILES and (insufficient or failure)
    return LegDecision(
        question=leg.question,
        supports_when=leg.supports_when,
        threshold=leg.threshold,
        probability=packet.probability,
        interval=packet.confidence_interval,
        evidence_profile=profile,
        classification=classification,
        weight=weight,
        weighted_support=weighted_support,
        direct_evidence=direct_evidence,
        full_weight_contradiction=full_weight_contradiction,
        insufficient_data=full_weight_insufficient or insufficient,
        failure=failure,
        reasoning_summary=packet.reasoning_summary,
        evidence_packet=packet,
    )


def evaluate_thesis(thesis: ThesisConfig, recorded_run: dict[str, Any]) -> MultiLegDecision:
    thesis_replay = recorded_run["theses"].get(thesis.thesis_id)
    if not isinstance(thesis_replay, dict):
        raise ValueError(f"No recorded replay found for thesis {thesis.thesis_id}.")
    recorded_legs = thesis_replay.get("legs", [])
    if len(recorded_legs) != len(thesis.questions):
        raise ValueError(f"Replay leg count does not match thesis {thesis.thesis_id}.")

    leg_decisions = tuple(
        classify_leg(thesis, leg, recorded_leg)
        for leg, recorded_leg in zip(thesis.questions, recorded_legs)
    )
    weighted_support = round(sum(item.weighted_support for item in leg_decisions), 6)
    direct_evidence_legs = sum(1 for item in leg_decisions if item.direct_evidence)
    full_weight_contradictions = tuple(
        item.question for item in leg_decisions if item.full_weight_contradiction
    )
    full_weight_insufficient_legs = tuple(
        item.question
        for item in leg_decisions
        if item.insufficient_data and item.evidence_profile in DIRECT_EVIDENCE_PROFILES
    )

    reasons: list[str] = []
    if weighted_support < MIN_WEIGHTED_SUPPORT:
        reasons.append(f"Weighted support {weighted_support:.1f} < {MIN_WEIGHTED_SUPPORT:.1f}.")
    if full_weight_contradictions:
        reasons.append("Full-weight contradiction(s): " + "; ".join(full_weight_contradictions) + ".")
    if direct_evidence_legs < 2:
        reasons.append(f"Only {direct_evidence_legs} direct-evidence leg(s); at least 2 required.")
    if full_weight_insufficient_legs:
        reasons.append(
            "Full-weight insufficient/failed leg(s): " + "; ".join(full_weight_insufficient_legs) + "."
        )

    verdict = "DECLINE" if reasons else "PROCEED"
    if verdict == "PROCEED":
        reasons.append("Weighted support, direct-evidence count, and contradiction checks passed.")

    return MultiLegDecision(
        thesis_id=thesis.thesis_id,
        thesis=thesis.thesis,
        instrument=thesis.instrument,
        direction=thesis.direction,
        notional_usd=thesis.notional_usd,
        verdict=verdict,
        weighted_support=weighted_support,
        direct_evidence_legs=direct_evidence_legs,
        full_weight_contradictions=full_weight_contradictions,
        full_weight_insufficient_legs=full_weight_insufficient_legs,
        reasons=tuple(reasons),
        leg_decisions=leg_decisions,
    )


def intent_from_thesis(thesis: ThesisConfig) -> FinancialActionIntent:
    direction_map = {"long": "increase_long_exposure", "short": "decrease_long_exposure"}
    exposure_direction = direction_map.get(thesis.direction)
    if exposure_direction is None:
        raise ValueError(f"Unsupported thesis direction: {thesis.direction}")
    question_text = " | ".join(leg.question for leg in thesis.questions)
    return FinancialActionIntent(
        scenario_id=thesis.thesis_id,
        thesis=thesis.thesis,
        symbol=thesis.instrument,
        exposure_direction=exposure_direction,
        notional_usd=thesis.notional_usd,
        forecast_question=question_text,
        search_query=f"{thesis.thesis} prediction market evidence",
    )


def gate_decision_from_multileg(decision: MultiLegDecision) -> GateDecision:
    return GateDecision(
        decision=decision.verdict,
        cleared_for_paper_preview=decision.cleared_for_paper_preview,
        reasons=decision.reasons,
        next_step=(
            "Create a local paper-preview object for explicit human review."
            if decision.cleared_for_paper_preview
            else "Write memo and audit only; do not create a paper-preview object."
        ),
        config_snapshot={
            "schema_version": "multi_leg_gate_config.v1",
            "margin": MARGIN,
            "min_weighted_support": MIN_WEIGHTED_SUPPORT,
            "required_direct_evidence_legs": 2,
            "block_full_weight_contradiction": True,
            "block_full_weight_insufficient_data": True,
            "uses_confidence_scalar": False,
            "allowed_use": ALLOWED_USE,
        },
    )


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value < 0.01 and value > 0:
        return "<1%"
    return f"{value:.0%}"


def build_multileg_memo(thesis: ThesisConfig, decision: MultiLegDecision) -> str:
    leg_lines = []
    for leg in decision.leg_decisions:
        leg_lines.append(
            "- "
            f"{leg.question} -> probability {format_percent(leg.probability)}, "
            f"threshold {leg.threshold:.0%} when `{leg.supports_when}`, "
            f"profile `{leg.evidence_profile}`, classification `{leg.classification}`, "
            f"weight {leg.weight:.1f}."
        )
    reasons = "\n".join(f"- {reason}" for reason in decision.reasons)
    return f"""# Market Foresight Evidence Gate Memo

## Thesis
{thesis.thesis}

## Scenario
- Thesis ID: `{thesis.thesis_id}`
- As of: `{thesis.as_of}`
- Instrument: `{thesis.instrument}`
- Direction: `{thesis.direction}`
- Notional: `${thesis.notional_usd:,.2f}`

## Verdict
`{decision.verdict}`

## Gate Summary
- Weighted support: {decision.weighted_support:.1f}
- Direct-evidence legs: {decision.direct_evidence_legs}
- Full-weight contradictions: {len(decision.full_weight_contradictions)}
- Confidence scalar used by gate: no

## Leg Classifications
{chr(10).join(leg_lines)}

## Reasons
{reasons}
## Allowed Use
`{ALLOWED_USE}`

## Disclaimer
This memo is research/demo software output, not financial advice. It does not place real trades,
does not support real-money execution, and permits only a local simulated paper-trade review by
a human when the gate says `PROCEED`.
"""


def build_multileg_risk_map(thesis: ThesisConfig, decision: MultiLegDecision, live: bool = False) -> dict[str, Any]:
    if live:
        guardrails = {
            "offline_replay": False,
            "live_polybridge_evidence": True,
            "read_only_evidence": True,
            "no_live_broker_calls": True,
            "no_live_trading_path": True,
            "simulated_paper_only": True,
            "secrets_redacted": True,
        }
    else:
        guardrails = {
            "offline_replay": True,
            "no_network_calls": True,
            "no_live_broker_calls": True,
            "no_live_trading_path": True,
            "simulated_paper_only": True,
            "secrets_redacted": True,
        }
    return {
        "schema_version": "multi_leg_evidence_gate_result.v1",
        "allowed_use": ALLOWED_USE,
        "thesis_id": thesis.thesis_id,
        "thesis": thesis.thesis,
        "as_of": thesis.as_of,
        "instrument": thesis.instrument,
        "direction": thesis.direction,
        "notional_usd": thesis.notional_usd,
        "verdict": decision.verdict,
        "weighted_support": decision.weighted_support,
        "direct_evidence_legs": decision.direct_evidence_legs,
        "full_weight_contradictions": list(decision.full_weight_contradictions),
        "reasons": list(decision.reasons),
        "methodology": {
            "margin": MARGIN,
            "min_weighted_support": MIN_WEIGHTED_SUPPORT,
            "probability_source": "forecast_only",
            "search_relevance_use": "metadata_only",
            "confidence_scalar_used": False,
            "threshold_source": "thesis_config",
        },
        "leg_decisions": [to_jsonable(item) for item in decision.leg_decisions],
        "guardrails": guardrails,
    }


def build_multileg_audit_record(
    *,
    base_dir: Path,
    run_id: str,
    thesis: ThesisConfig,
    replay_path: Path | None = None,
    decision: MultiLegDecision,
    output_paths: dict[str, Path],
    paper_preview: dict[str, Any] | None,
    live: bool = False,
) -> dict[str, Any]:
    if live:
        guardrails = {
            "offline_replay": False,
            "live_polybridge_evidence": True,
            "read_only_evidence": True,
            "no_live_broker_calls": True,
            "no_live_trading": True,
            "simulated_paper_requires_gate_proceed": True,
            "human_approval_required_before_simulated_fill": True,
            "secrets_redacted": True,
        }
    else:
        guardrails = {
            "offline_replay": True,
            "no_network_calls": True,
            "no_live_broker_calls": True,
            "no_live_trading": True,
            "simulated_paper_requires_gate_proceed": True,
            "human_approval_required_before_simulated_fill": True,
            "secrets_redacted": True,
        }
    return redact(
        {
            "schema_version": "multi_leg_decision_audit_record.v1",
            "run_id": run_id,
            "timestamp": utc_now_iso(),
            "tier": "multi_leg_evidence_gate",
            "scenario_id": thesis.thesis_id,
            "replay_source": "live_polybridge" if live else audit_path(replay_path, base_dir),
            "verdict": decision.verdict,
            "weighted_support": decision.weighted_support,
            "direct_evidence_legs": decision.direct_evidence_legs,
            "leg_decisions": [to_jsonable(item) for item in decision.leg_decisions],
            "paper_preview": to_jsonable(paper_preview) if paper_preview else None,
            "output_paths": {label: audit_path(path, base_dir) for label, path in output_paths.items()},
            "guardrails": guardrails,
        }
    )


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(to_jsonable(data)), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(redact(text)).rstrip() + "\n", encoding="utf-8")
    return path


def append_jsonl(path: Path, record: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact(record), sort_keys=True) + "\n")
    return path


def run_multileg_replay_workflow(
    *,
    thesis_id: str,
    theses_path: Path,
    replay_path: Path,
    base_dir: Path,
    output_dir: Path | None = None,
    create_preview: bool = True,
) -> dict[str, Any]:
    output_dir = output_dir or (base_dir / "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    theses = load_theses(theses_path)
    if thesis_id not in theses:
        raise ValueError(f"Unknown thesis ID: {thesis_id}")
    thesis = theses[thesis_id]
    recorded_run = load_recorded_run(replay_path)
    decision = evaluate_thesis(thesis, recorded_run)
    gate_decision = gate_decision_from_multileg(decision)
    memo = build_multileg_memo(thesis, decision)
    result = build_multileg_risk_map(thesis, decision)
    run_id = f"run_{uuid.uuid4().hex[:12]}"

    paths = {
        "evidence_packet": write_json(
            output_dir / "evidence-packet.json",
            {"schema_version": "multi_leg_evidence_packets.v1", "evidence_packets": [item.evidence_packet for item in decision.leg_decisions]},
        ),
        "gate_decision": write_json(output_dir / "gate-decision.json", gate_decision),
        "decision_result": write_json(output_dir / "decision-result.json", result),
        "decision_memo": write_text(output_dir / "decision-memo.md", memo),
    }

    paper_preview = None

    audit_record = build_multileg_audit_record(
        base_dir=base_dir,
        run_id=run_id,
        thesis=thesis,
        replay_path=replay_path,
        decision=decision,
        output_paths=paths,
        paper_preview=paper_preview,
    )
    paths["decisions_log"] = append_jsonl(output_dir / "decisions.jsonl", audit_record)

    return {
        "run_id": run_id,
        "thesis": thesis,
        "intent": intent_from_thesis(thesis),
        "multi_leg_decision": decision,
        "gate_decision": gate_decision,
        "memo_markdown": memo,
        "paper_preview": paper_preview,
        "audit_record": audit_record,
        "paths": paths,
    }


def _looks_like_timeout(exc: Exception) -> bool:
    text = str(exc).lower()
    if "timed out" in text or "timeout" in text:
        return True
    cause = getattr(exc, "__cause__", None)
    return cause is not None and "timeout" in type(cause).__name__.lower()


def fetch_live_forecast(client: Any, question: str) -> dict[str, Any]:
    from .polybridge import PolyBridgeError

    try:
        return client.forecast(question)
    except PolyBridgeError as exc:
        if _looks_like_timeout(exc):
            return client.forecast(question)
        raise


def extract_profile_value(value: Any) -> str | None:
    if isinstance(value, str):
        candidate = value.strip().lower()
    elif isinstance(value, dict):
        candidate = str(first_present(value, ("profile", "type", "name")) or "").strip().lower()
    else:
        return None
    return candidate if candidate in KNOWN_EVIDENCE_PROFILES else None


def nested_metadata_profile(response: dict[str, Any]) -> str | None:
    node: Any = response.get("metadata")
    for key in ("oracle_port", "relevance_filter_summary", "selected_evidence_profile"):
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return extract_profile_value(node)


def live_leg_record(question: str, response: dict[str, Any]) -> dict[str, Any]:
    probability = normalize_unit_interval(first_present(response, ("probability", "forecast", "p")))
    interval = normalize_interval(
        first_present(response, ("confidence_interval", "confidenceInterval", "probability_range"))
    )
    raw_markets = response.get("markets_used")
    markets = (
        [normalize_source_market(item) for item in raw_markets if isinstance(item, dict)]
        if isinstance(raw_markets, list)
        else []
    )
    direct_count = sum(1 for market in markets if not market.is_proxy)
    proxy_count = len(markets) - direct_count

    profile = extract_profile_value(response.get("evidence_profile"))
    if profile is None:
        profile = nested_metadata_profile(response)
    if profile is None:
        if not markets:
            profile = "unspecified"
        elif direct_count == 0:
            profile = PROXY_ONLY_PROFILE
        elif proxy_count == 0:
            profile = "direct_only"
        else:
            profile = "direct_mixed"

    reasoning = first_present(response, ("reasoning_summary", "reasoning", "summary"))
    return {
        "question": question,
        "live_polybridge": True,
        "probability": probability,
        "confidence": first_present(response, ("confidence", "confidence_score")),
        "interval": [interval["lower"], interval["upper"]] if interval else None,
        "evidence_profile": profile,
        "direct_market_count": direct_count,
        "proxy_market_count": proxy_count,
        "source_markets": [to_jsonable(market) for market in markets],
        "reasoning_summary": str(reasoning) if reasoning else "Live PolyBridge forecast.",
        "insufficient_data": probability is None,
    }


def failed_live_leg(question: str, error_text: str) -> dict[str, Any]:
    return {
        "question": question,
        "live_polybridge": True,
        "failed": True,
        "insufficient_data": True,
        "probability": None,
        "evidence_profile": "unspecified",
        "source_markets": [],
        "reasoning_summary": f"Live PolyBridge forecast failed: {redact(error_text)}",
    }


def fetch_live_legs(thesis: ThesisConfig, client: Any) -> list[dict[str, Any]]:
    from .polybridge import PolyBridgeAuthError, PolyBridgeError

    legs: list[dict[str, Any]] = []
    for leg in thesis.questions:
        try:
            response = fetch_live_forecast(client, leg.question)
        except PolyBridgeAuthError:
            raise
        except PolyBridgeError as exc:
            legs.append(failed_live_leg(leg.question, str(exc)))
            continue
        legs.append(live_leg_record(leg.question, response))
    return legs


def run_multileg_live_workflow(
    *,
    thesis_id: str,
    theses_path: Path,
    base_dir: Path,
    output_dir: Path | None = None,
    create_preview: bool = True,
    client: Any | None = None,
) -> dict[str, Any]:
    output_dir = output_dir or (base_dir / "outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    theses = load_theses(theses_path)
    if thesis_id not in theses:
        raise ValueError(f"Unknown thesis ID: {thesis_id}")
    thesis = theses[thesis_id]

    if client is None:
        from .polybridge import PolyBridgeClient

        client = PolyBridgeClient()

    recorded_run = {"theses": {thesis_id: {"legs": fetch_live_legs(thesis, client)}}}
    decision = evaluate_thesis(thesis, recorded_run)
    gate_decision = gate_decision_from_multileg(decision)
    memo = build_multileg_memo(thesis, decision)
    result = build_multileg_risk_map(thesis, decision, live=True)
    run_id = f"run_{uuid.uuid4().hex[:12]}"

    paths = {
        "evidence_packet": write_json(
            output_dir / "evidence-packet.json",
            {"schema_version": "multi_leg_evidence_packets.v1", "evidence_packets": [item.evidence_packet for item in decision.leg_decisions]},
        ),
        "gate_decision": write_json(output_dir / "gate-decision.json", gate_decision),
        "decision_result": write_json(output_dir / "decision-result.json", result),
        "decision_memo": write_text(output_dir / "decision-memo.md", memo),
    }

    paper_preview = None

    audit_record = build_multileg_audit_record(
        base_dir=base_dir,
        run_id=run_id,
        thesis=thesis,
        decision=decision,
        output_paths=paths,
        paper_preview=paper_preview,
        live=True,
    )
    paths["decisions_log"] = append_jsonl(output_dir / "decisions.jsonl", audit_record)

    return {
        "run_id": run_id,
        "thesis": thesis,
        "intent": intent_from_thesis(thesis),
        "multi_leg_decision": decision,
        "gate_decision": gate_decision,
        "memo_markdown": memo,
        "paper_preview": paper_preview,
        "audit_record": audit_record,
        "paths": paths,
    }
