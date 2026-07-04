from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ALLOWED_USE, EvidencePacket, FinancialActionIntent, SourceMarket
from .polybridge import PolyBridgeAuthError, PolyBridgeClient, PolyBridgeError
from .redaction import redact_string


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def first_present(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(value)
    if not text:
        return None
    if text.endswith("%"):
        try:
            return float(text[:-1].strip()) / 100.0
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def normalize_unit_interval(value: Any) -> float | None:
    number = coerce_number(value)
    if number is None:
        return None
    if 1.0 < number <= 100.0:
        number /= 100.0
    return max(0.0, min(1.0, round(number, 6)))


def normalize_interval(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    lower = normalize_unit_interval(first_present(value, ("lower", "low", "min")))
    upper = normalize_unit_interval(first_present(value, ("upper", "high", "max")))
    if lower is None or upper is None:
        return None
    if lower > upper:
        lower, upper = upper, lower
    return {"lower": lower, "upper": upper}


def canonical_sha256(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_intent(fixtures_dir: Path) -> FinancialActionIntent:
    raw = load_json(fixtures_dir / "thesis.json")
    intent = raw.get("intent", {})
    return FinancialActionIntent(
        scenario_id=str(raw["scenario_id"]),
        thesis=str(raw["thesis"]),
        symbol=str(intent["symbol"]),
        exposure_direction=str(intent["exposure_direction"]),
        notional_usd=float(intent["notional_usd"]),
        forecast_question=str(raw["forecast_question"]),
        search_query=str(raw["search_query"]),
        allowed_use=str(raw.get("allowed_use", ALLOWED_USE)),
    )


def normalize_source_market(raw_market: dict[str, Any]) -> SourceMarket:
    source = clean_text(first_present(raw_market, ("source", "platform", "venue", "provider"))) or "unknown"
    question = clean_text(first_present(raw_market, ("question", "title", "name"))) or "Question unavailable"
    url = clean_text(first_present(raw_market, ("platform_url", "platformUrl", "url", "market_url")))
    probability = normalize_unit_interval(first_present(raw_market, ("probability", "yes_probability", "price")))
    relevance = normalize_unit_interval(raw_market.get("relevance"))
    return SourceMarket(
        source=source,
        question=question,
        url=url,
        probability=probability,
        relevance=relevance,
        is_proxy=bool(raw_market.get("is_proxy", False)),
    )


def build_quality_flags(
    forecast_response: dict[str, Any],
    search_response: dict[str, Any],
    probability: float | None,
    confidence: float | None,
    interval: dict[str, float] | None,
    source_markets: tuple[SourceMarket, ...],
    proxy_only: bool,
    fixture_mode: bool = True,
    extra_flags: tuple[str, ...] = tuple(),
) -> tuple[str, ...]:
    flags = {"offline_fixture", "sanitized_fixture"} if fixture_mode else {"live_polybridge"}
    flags.update(extra_flags)
    if forecast_response.get("status") not in (None, "ok"):
        flags.add("api_error")
    if search_response.get("status") not in (None, "ok"):
        flags.add("search_unavailable")
    if probability is None:
        flags.add("missing_probability")
    if confidence is None:
        flags.add("missing_confidence")
    if interval is None:
        flags.add("missing_confidence_interval")
    if not source_markets:
        flags.add("no_source_markets")
    if proxy_only:
        flags.add("proxy_only")
    return tuple(sorted(flags))


def build_evidence_packet(
    intent: FinancialActionIntent,
    forecast_response: dict[str, Any],
    search_response: dict[str, Any],
    created_at: str | None = None,
    fixture_mode: bool = True,
    extra_quality_flags: tuple[str, ...] = tuple(),
) -> EvidencePacket:
    probability = normalize_unit_interval(first_present(forecast_response, ("probability", "forecast", "p")))
    confidence = normalize_unit_interval(first_present(forecast_response, ("confidence", "confidence_score")))
    interval = normalize_interval(
        first_present(forecast_response, ("confidence_interval", "confidenceInterval", "probability_range"))
    )
    raw_markets = forecast_response.get("markets_used")
    source_markets = (
        tuple(normalize_source_market(item) for item in raw_markets if isinstance(item, dict))
        if isinstance(raw_markets, list)
        else tuple()
    )

    raw_profile = forecast_response.get("evidence_profile")
    profile = dict(raw_profile) if isinstance(raw_profile, dict) else {}
    search_results = search_response.get("results")
    search_count = len(search_results) if isinstance(search_results, list) else 0
    search_relevances: list[float] = []
    if isinstance(search_results, list):
        search_relevances = [
            value
            for value in (normalize_unit_interval(item.get("relevance")) for item in search_results if isinstance(item, dict))
            if value is not None
        ]
    proxy_only = bool(profile.get("proxy_only")) or bool(source_markets and all(item.is_proxy for item in source_markets))
    interval_width = None if interval is None else round(interval["upper"] - interval["lower"], 6)

    evidence_profile: dict[str, Any] = {
        "fixture_mode": fixture_mode,
        "live_polybridge": not fixture_mode,
        "forecast_status": forecast_response.get("status", "ok"),
        "search_status": search_response.get("status", "ok"),
        "forecast_evidence_type": profile.get("type", "unspecified"),
        "search_result_count": search_count,
        "search_max_relevance": max(search_relevances) if search_relevances else None,
        "source_market_count": len(source_markets),
        "proxy_only": proxy_only,
        "confidence_interval_width": interval_width,
    }

    raw_bundle = {"forecast_response": forecast_response, "search_response": search_response}
    raw_hash = canonical_sha256(raw_bundle)
    reasoning = clean_text(first_present(forecast_response, ("reasoning_summary", "reasoning", "summary")))
    quality_flags = build_quality_flags(
        forecast_response=forecast_response,
        search_response=search_response,
        probability=probability,
        confidence=confidence,
        interval=interval,
        source_markets=source_markets,
        proxy_only=proxy_only,
        fixture_mode=fixture_mode,
        extra_flags=extra_quality_flags,
    )

    return EvidencePacket(
        packet_id=f"ep_{raw_hash[:16]}",
        created_at=created_at or utc_now_iso(),
        scenario_id=intent.scenario_id,
        question=intent.forecast_question,
        probability=probability,
        confidence=confidence,
        confidence_interval=interval,
        evidence_profile=evidence_profile,
        source_markets=source_markets,
        reasoning_summary=reasoning or "No reasoning summary was present in the offline fixture.",
        quality_flags=quality_flags,
        raw_response_sha256=raw_hash,
        allowed_use=ALLOWED_USE,
    )


def load_offline_evidence(fixtures_dir: Path) -> tuple[FinancialActionIntent, EvidencePacket]:
    intent = load_intent(fixtures_dir)
    forecast_response = load_json(fixtures_dir / "polybridge_forecast.response.json")
    search_response = load_json(fixtures_dir / "polybridge_search.response.json")
    return intent, build_evidence_packet(intent, forecast_response, search_response)


def fetch_live_evidence(intent: FinancialActionIntent, client: PolyBridgeClient) -> EvidencePacket:
    try:
        search_response = client.search(intent.search_query)
    except PolyBridgeAuthError:
        raise
    except PolyBridgeError as exc:
        search_response = {
            "status": "error",
            "error": redact_string(str(exc)),
            "results": [],
        }

    forecast_response = client.forecast(intent.forecast_question)
    return build_evidence_packet(
        intent=intent,
        forecast_response=forecast_response,
        search_response=search_response,
        fixture_mode=False,
    )
