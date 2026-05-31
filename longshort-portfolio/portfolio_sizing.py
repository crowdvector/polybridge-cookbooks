#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

API_BASE_URL = "https://api.polybridge.ai"
FORECAST_ENDPOINT = f"{API_BASE_URL}/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 75
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 2.0
TOTAL_NOTIONAL_USD = 50_000
MAX_SINGLE_POSITION_USD = 20_000
ROUNDING_INCREMENT_USD = 500

QUESTIONS = [
    "Will there be meaningful US crypto regulatory reform by Q2 2027?",
    "Will the Fed cut rates before September 2026?",
    "Will the US enter a recession by end of 2026?",
    "Will the Strait of Hormuz reopen to regular traffic by June 30, 2026?",
    "Will WTI crude oil exceed $90 in June 2026?",
]

QUESTION_LABELS = {
    QUESTIONS[0]: "US crypto reform by Q2 2027",
    QUESTIONS[1]: "Fed cut before Sep 2026",
    QUESTIONS[2]: "US recession by end 2026",
    QUESTIONS[3]: "Hormuz reopens by Jun 30, 2026",
    QUESTIONS[4]: "WTI above $90 in Jun 2026",
}

THESIS_BY_ASSET = {
    "BTC": "Fixed supply, maximum decentralisation, actual PMF.",
    "SPX": "AI tailwind remains structural, but macro downside still matters.",
    "OP": "Declining sequencer revenue, ongoing token unlocks, fading narrative.",
    "BERA": "High token supply, no clear PMF, founder conviction signals low.",
    "WTI": "Geopolitics are highly uncertain, so conviction stays conditional.",
}

POSITION_CAPS_USD = {
    "BTC": 18_000,
    "SPX": 12_000,
    "OP": 10_000,
    "BERA": 8_000,
    "WTI": 2_000,
}

THESIS_CONVICTION = {
    "BTC": 0.85,
    "SPX": 0.68,
    "OP": 0.72,
    "BERA": 0.69,
    "WTI": 0.50,
}


class ForecastShapeError(RuntimeError):
    def __init__(self, question: str, shape: dict[str, Any]):
        super().__init__(question)
        self.question = question
        self.shape = shape


@dataclass(frozen=True)
class WorkflowPaths:
    macro_snapshot: Path
    position_table: Path
    order_instructions: Path
    research_brief: Path
    agent_session: Path
    portfolio_summary_png: Path | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "macro_snapshot": str(self.macro_snapshot),
            "position_table": str(self.position_table),
            "order_instructions": str(self.order_instructions),
            "research_brief": str(self.research_brief),
            "agent_session": str(self.agent_session),
            "portfolio_summary_png": str(self.portfolio_summary_png) if self.portfolio_summary_png else None,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def first_present(data: dict[str, Any], keys: list[str]) -> Any:
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
    return round(clamp(number), 6)


def normalize_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    seconds = coerce_number(value)
    if seconds is not None:
        return max(0.0, seconds)
    try:
        retry_time = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    delta = (retry_time - datetime.now(retry_time.tzinfo or timezone.utc)).total_seconds()
    return max(0.0, delta)


def load_api_key(prompt_if_missing: bool = False) -> str:
    api_key = clean_text(os.getenv("POLYBRIDGE_API_KEY"))
    if api_key:
        return api_key
    if prompt_if_missing:
        from getpass import getpass

        entered = clean_text(getpass("Paste POLYBRIDGE_API_KEY: "))
        if entered:
            return entered
    raise RuntimeError(
        "POLYBRIDGE_API_KEY is not set. Export it before running the script, "
        "or allow notebook mode to prompt for it with getpass()."
    )


def summarize_shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            "type": "object",
            "keys": sorted(value.keys()),
        }
    if isinstance(value, list):
        summary: dict[str, Any] = {
            "type": "array",
            "length": len(value),
        }
        first_object = next((item for item in value if isinstance(item, dict)), None)
        if first_object is not None:
            summary["first_object_keys"] = sorted(first_object.keys())
        return summary
    if value is None:
        return None
    return type(value).__name__


def sanitized_response_shape(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return {key: summarize_shape(value) for key, value in payload.items()}
    return {"root_type": type(payload).__name__}


def forecast_question(
    session: requests.Session,
    api_key: str,
    question: str,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    max_retries: int = MAX_RETRIES,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"question": question}
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            response = session.post(
                FORECAST_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
        except requests.exceptions.RequestException as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            time.sleep(min(20.0, BACKOFF_BASE_SECONDS * (2**attempt)))
            continue

        if response.status_code in {429, 503}:
            if attempt >= max_retries:
                response.raise_for_status()
            wait_seconds = normalize_retry_after(response.headers.get("Retry-After"))
            if wait_seconds is None:
                wait_seconds = min(20.0, BACKOFF_BASE_SECONDS * (2**attempt))
            time.sleep(wait_seconds)
            continue

        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Non-JSON response returned for question: {question}") from exc

    raise RuntimeError(f"Forecast request failed for question: {question}") from last_error


def extract_interval_fields(payload: dict[str, Any]) -> tuple[Any | None, Any | None]:
    confidence_interval = first_present(payload, ["confidence_interval", "confidenceInterval"])
    probability_range = first_present(payload, ["probability_range", "probabilityRange"])
    if probability_range is None:
        low = normalize_unit_interval(
            first_present(payload, ["probability_low", "probabilityLow", "lower_bound", "lowerBound"])
        )
        high = normalize_unit_interval(
            first_present(payload, ["probability_high", "probabilityHigh", "upper_bound", "upperBound"])
        )
        if low is not None or high is not None:
            probability_range = {"low": low, "high": high}
    return confidence_interval, probability_range


def sanitize_market(raw_market: dict[str, Any]) -> dict[str, Any]:
    market: dict[str, Any] = {}

    label = clean_text(first_present(raw_market, ["label", "role"]))
    if label:
        market["label"] = label

    source = clean_text(first_present(raw_market, ["source", "platform", "venue", "exchange", "provider"]))
    if source:
        market["source_platform"] = source

    probability = normalize_unit_interval(
        first_present(raw_market, ["probability", "yes_probability", "yesProbability", "price"])
    )
    if probability is not None:
        market["probability"] = probability

    question = clean_text(
        first_present(raw_market, ["question", "title", "name", "market_question", "marketTitle"])
    )
    if question:
        market["question_title"] = question

    url = clean_text(first_present(raw_market, ["platform_url", "platformUrl", "url", "market_url", "marketUrl"]))
    if url:
        market["url"] = url

    return market


def sanitize_forecast(question: str, payload: dict[str, Any]) -> dict[str, Any]:
    probability = normalize_unit_interval(first_present(payload, ["probability", "forecast", "p"]))
    if probability is None:
        raise ForecastShapeError(question, sanitized_response_shape(payload))

    raw_confidence = first_present(payload, ["confidence", "confidence_score", "confidenceScore"])
    numeric_confidence = normalize_unit_interval(raw_confidence)
    confidence: Any | None = numeric_confidence if numeric_confidence is not None else clean_text(raw_confidence)
    confidence_interval, probability_range = extract_interval_fields(payload)

    raw_markets = payload.get("markets_used")
    source_markets = (
        [
            market
            for market in (sanitize_market(item) for item in raw_markets if isinstance(item, dict))
            if market
        ]
        if isinstance(raw_markets, list)
        else []
    )

    explicit_count = coerce_number(first_present(payload, ["source_market_count", "markets_used_count", "market_count"]))
    source_market_count = int(explicit_count) if explicit_count is not None else len(source_markets)

    result: dict[str, Any] = {
        "question": question,
        "probability": probability,
        "probability_percent": round(probability * 100.0, 2),
        "confidence": confidence,
        "source_market_count": source_market_count,
        "source_markets": source_markets,
    }

    if confidence_interval is not None:
        result["confidence_interval"] = confidence_interval
    if probability_range is not None:
        result["probability_range"] = probability_range

    reasoning = clean_text(first_present(payload, ["reasoning", "summary", "explanation"]))
    if reasoning:
        result["reasoning"] = reasoning

    return result


def build_macro_snapshot(prompt_for_key: bool = False) -> dict[str, Any]:
    api_key = load_api_key(prompt_if_missing=prompt_for_key)
    snapshot = {
        "generated_at": utc_now_iso(),
        "api_base_url": API_BASE_URL,
        "forecast_endpoint": FORECAST_ENDPOINT,
        "question_count": len(QUESTIONS),
        "questions": [],
    }

    with requests.Session() as session:
        for question in QUESTIONS:
            payload = forecast_question(session=session, api_key=api_key, question=question)
            snapshot["questions"].append(sanitize_forecast(question, payload))

    return snapshot


def format_percent(value: float | None) -> str:
    if value is None:
        return "n/a"
    percent = round(value * 100.0, 1)
    if percent.is_integer():
        return f"{int(percent)}%"
    return f"{percent:.1f}%"


def format_usd(value: int | float) -> str:
    return f"${value:,.0f}"


def question_lookup(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["question"]: item for item in snapshot["questions"]}


def probability_for(snapshot: dict[str, Any], question: str) -> float:
    return float(question_lookup(snapshot)[question]["probability"])


def round_notional(value: float, cap: int) -> int:
    rounded = int(round(value / ROUNDING_INCREMENT_USD) * ROUNDING_INCREMENT_USD)
    return max(0, min(cap, rounded))


def combine_signal(thesis_conviction: float, macro_support: float, cap: int) -> int:
    raw = cap * math.sqrt(clamp(thesis_conviction) * clamp(macro_support))
    return round_notional(raw, cap)


def extract_range_text(item: dict[str, Any]) -> str | None:
    interval = item.get("confidence_interval")
    if isinstance(interval, dict):
        lower = normalize_unit_interval(interval.get("lower"))
        upper = normalize_unit_interval(interval.get("upper"))
        if lower is not None and upper is not None:
            return f"{format_percent(lower)} to {format_percent(upper)}"

    probability_range = item.get("probability_range")
    if isinstance(probability_range, dict):
        lower = normalize_unit_interval(probability_range.get("low"))
        upper = normalize_unit_interval(probability_range.get("high"))
        if lower is not None and upper is not None:
            return f"{format_percent(lower)} to {format_percent(upper)}"
    return None


def macro_support_scores(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    p_crypto = probability_for(snapshot, QUESTIONS[0])
    p_fed_cut = probability_for(snapshot, QUESTIONS[1])
    p_recession = probability_for(snapshot, QUESTIONS[2])
    p_hormuz_open = probability_for(snapshot, QUESTIONS[3])
    p_wti90 = probability_for(snapshot, QUESTIONS[4])

    btc_support = clamp(0.50 * p_crypto + 0.20 * p_fed_cut + 0.20 * (1.0 - p_recession) + 0.10 * p_hormuz_open)
    spx_support = clamp(0.40 * p_fed_cut + 0.35 * (1.0 - p_recession) + 0.15 * p_hormuz_open + 0.10 * (1.0 - p_wti90))
    op_short_support = clamp(0.40 * (1.0 - p_crypto) + 0.25 * p_recession + 0.20 * (1.0 - p_fed_cut) + 0.15 * p_wti90)
    bera_short_support = clamp(0.45 * (1.0 - p_crypto) + 0.25 * p_recession + 0.15 * (1.0 - p_fed_cut) + 0.15 * p_wti90)

    wti_bull_support = clamp(0.55 * p_wti90 + 0.45 * (1.0 - p_hormuz_open))
    wti_bear_support = clamp(0.55 * (1.0 - p_wti90) + 0.45 * p_hormuz_open)
    wti_support_gap = abs(wti_bull_support - wti_bear_support)

    if wti_support_gap < 0.12 or max(wti_bull_support, wti_bear_support) < 0.60:
        wti_direction = "FLAT"
        wti_support = 0.0
    elif wti_bull_support > wti_bear_support:
        wti_direction = "LONG"
        wti_support = wti_bull_support
    else:
        wti_direction = "SHORT"
        wti_support = wti_bear_support

    return {
        "BTC": {"direction": "LONG", "macro_support": btc_support},
        "SPX": {"direction": "LONG", "macro_support": spx_support},
        "OP": {"direction": "SHORT", "macro_support": op_short_support},
        "BERA": {"direction": "SHORT", "macro_support": bera_short_support},
        "WTI": {
            "direction": wti_direction,
            "macro_support": wti_support,
            "bull_support": wti_bull_support,
            "bear_support": wti_bear_support,
            "support_gap": wti_support_gap,
        },
    }


def macro_evidence_lines(asset: str, snapshot: dict[str, Any], support: dict[str, dict[str, Any]]) -> list[str]:
    p_crypto = probability_for(snapshot, QUESTIONS[0])
    p_fed_cut = probability_for(snapshot, QUESTIONS[1])
    p_recession = probability_for(snapshot, QUESTIONS[2])
    p_hormuz_open = probability_for(snapshot, QUESTIONS[3])
    p_wti90 = probability_for(snapshot, QUESTIONS[4])

    if asset == "BTC":
        return [
            f"Crypto reform is priced at {format_percent(p_crypto)}, which is the main macro tailwind for BTC.",
            f"Fed cuts are only priced at {format_percent(p_fed_cut)}, so this BTC long leans more on the policy backdrop than on a near-term liquidity easing impulse.",
        ]
    if asset == "SPX":
        return [
            f"Recession is only priced at {format_percent(p_recession)}, which keeps the SPX long viable even though the market does not expect early Fed easing.",
            f"Hormuz reopening at {format_percent(p_hormuz_open)} and WTI > $90 at {format_percent(p_wti90)} shape the energy shock risk around SPX.",
        ]
    if asset == "OP":
        return [
            f"Crypto reform is priced at {format_percent(p_crypto)}; higher reform odds weaken the short, lower reform odds strengthen it.",
            f"Fed cuts are only priced at {format_percent(p_fed_cut)}, which limits any easy-money tailwind for alt beta and keeps the OP short thesis intact.",
        ]
    if asset == "BERA":
        return [
            f"BERA short conviction depends heavily on crypto reform at {format_percent(p_crypto)} because a strong policy tailwind can squeeze weaker alts.",
            f"Low Fed cut odds at {format_percent(p_fed_cut)} mean this short is not fighting a strong easing narrative, even though recession risk itself is only {format_percent(p_recession)}.",
        ]
    return [
        f"WTI > $90 is priced at {format_percent(p_wti90)} while Hormuz reopening is priced at {format_percent(p_hormuz_open)}.",
        f"Bull support is {format_percent(support['WTI']['bull_support'])} and bear support is {format_percent(support['WTI']['bear_support'])}, so the oil signal is handled conservatively.",
    ]


def rationale_for_position(asset: str, direction: str, notional_usd: int, macro_support: float) -> str:
    cap = POSITION_CAPS_USD[asset]
    conviction = THESIS_CONVICTION[asset]
    if direction == "FLAT":
        return (
            "Left flat because the oil signal is mixed relative to the cautious thesis, so the workflow does not force a position."
        )
    return (
        f"Sized at {format_usd(notional_usd)} from a {format_percent(conviction)} fixed thesis conviction, "
        f"a {format_percent(macro_support)} macro support score, and a {format_usd(cap)} asset cap."
    )


def build_position_table(snapshot: dict[str, Any]) -> dict[str, Any]:
    support = macro_support_scores(snapshot)
    positions: list[dict[str, Any]] = []

    for asset in ["BTC", "SPX", "OP", "BERA", "WTI"]:
        direction = str(support[asset]["direction"])
        macro_support = float(support[asset]["macro_support"])
        if direction == "FLAT":
            notional_usd = 0
        else:
            notional_usd = combine_signal(
                thesis_conviction=THESIS_CONVICTION[asset],
                macro_support=macro_support,
                cap=POSITION_CAPS_USD[asset],
            )

        positions.append(
            {
                "asset": asset,
                "direction": direction,
                "notional_usd": notional_usd,
                "percent_of_total_notional": round((notional_usd / TOTAL_NOTIONAL_USD) * 100.0, 2),
                "thesis": THESIS_BY_ASSET[asset],
                "macro_evidence": macro_evidence_lines(asset, snapshot, support),
                "rationale": rationale_for_position(asset, direction, notional_usd, macro_support),
            }
        )

    total_absolute_notional = sum(abs(position["notional_usd"]) for position in positions)
    max_position_notional = max(abs(position["notional_usd"]) for position in positions)

    return {
        "generated_at": snapshot["generated_at"],
        "total_notional_usd": TOTAL_NOTIONAL_USD,
        "methodology_note": (
            "Constrained scoring rule. Each asset starts with a thesis conviction and macro support score "
            "derived from the five live PolyBridge probabilities. Final USD notionals use square-root scaling, "
            "asset caps, a $50,000 gross notional budget, and rounding to the nearest $500."
        ),
        "positions": positions,
        "validation": {
            "total_absolute_notional_usd": total_absolute_notional,
            "total_absolute_notional_within_limit": total_absolute_notional <= TOTAL_NOTIONAL_USD,
            "max_single_position_limit_usd": MAX_SINGLE_POSITION_USD,
            "max_single_position_within_limit": max_position_notional <= MAX_SINGLE_POSITION_USD,
        },
    }


def build_order_instructions(position_table: dict[str, Any]) -> dict[str, Any]:
    orders: list[dict[str, Any]] = []

    for position in position_table["positions"]:
        direction = position["direction"]
        notional_usd = int(position["notional_usd"])

        orders.append(
            {
                "asset": position["asset"],
                "direction": direction,
                "notional_usd": notional_usd,
                "target_notional_usd": notional_usd,
                "units": "not provided",
            }
        )

    return {
        "generated_at": position_table["generated_at"],
        "orders": orders,
    }


def classify_macro_read(snapshot: dict[str, Any]) -> list[str]:
    p_crypto = probability_for(snapshot, QUESTIONS[0])
    p_fed_cut = probability_for(snapshot, QUESTIONS[1])
    p_recession = probability_for(snapshot, QUESTIONS[2])
    p_hormuz_open = probability_for(snapshot, QUESTIONS[3])
    p_wti90 = probability_for(snapshot, QUESTIONS[4])

    liquidity_read = (
        f"Fed cuts are priced at {format_percent(p_fed_cut)} and recession is priced at {format_percent(p_recession)}. "
        "That reads more like a steady-growth base case than an imminent easing cycle or a hard macro slowdown."
    )
    crypto_read = (
        f"Meaningful US crypto reform is priced at {format_percent(p_crypto)}. "
        "That supports keeping BTC as the highest-conviction long, but it also limits how large the alt shorts should get if policy turns more constructive."
    )
    energy_read = (
        f"Hormuz reopening sits at {format_percent(p_hormuz_open)} and WTI > $90 sits at {format_percent(p_wti90)}. "
        "The oil complex is not one-way enough to force a large WTI expression in the portfolio."
    )
    return [liquidity_read, crypto_read, energy_read]


def thesis_challenges(snapshot: dict[str, Any], position_table: dict[str, Any]) -> list[str]:
    p_crypto = probability_for(snapshot, QUESTIONS[0])
    p_fed_cut = probability_for(snapshot, QUESTIONS[1])
    p_recession = probability_for(snapshot, QUESTIONS[2])
    p_hormuz_open = probability_for(snapshot, QUESTIONS[3])
    p_wti90 = probability_for(snapshot, QUESTIONS[4])
    positions = {item["asset"]: item for item in position_table["positions"]}

    challenges: list[str] = []

    if p_crypto >= 0.55:
        challenges.append(
            f"Crypto reform at {format_percent(p_crypto)} argues against running the OP and BERA shorts at maximum size because a policy tailwind can lift weaker tokens as well as BTC."
        )
    if p_recession >= 0.45:
        challenges.append(
            f"Recession at {format_percent(p_recession)} challenges the lean-long SPX thesis and is the main reason the SPX notional stays capped."
        )
    if p_fed_cut >= 0.55 and positions["SPX"]["notional_usd"] < 10_000:
        challenges.append(
            f"Fed cuts at {format_percent(p_fed_cut)} do help broad beta, but the sizing rule still discounts that support because recession and energy risks remain live."
        )
    if abs((1.0 - p_hormuz_open) - p_wti90) < 0.12:
        challenges.append(
            f"WTI is held flat because Hormuz and oil signals are too close together ({format_percent(p_hormuz_open)} reopen vs {format_percent(p_wti90)} above $90) to justify a directional commodity trade."
        )

    if not challenges:
        challenges.append("No thesis challenge cleared the configured threshold, but this remains a market-implied snapshot rather than a recommendation.")

    return challenges


def markdown_position_table(position_table: dict[str, Any]) -> str:
    rows = [
        "| Asset | Direction | Notional USD | % of Total | Rationale |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for position in position_table["positions"]:
        rows.append(
            "| {asset} | {direction} | {notional} | {percent:.2f}% | {rationale} |".format(
                asset=position["asset"],
                direction=position["direction"],
                notional=format_usd(position["notional_usd"]),
                percent=position["percent_of_total_notional"],
                rationale=position["rationale"],
            )
        )
    return "\n".join(rows)


def markdown_forecast_table(snapshot: dict[str, Any]) -> str:
    rows = [
        "| Question | Probability | Source Markets | Range |",
        "| --- | ---: | ---: | --- |",
    ]
    for item in snapshot["questions"]:
        rows.append(
            "| {question} | {prob} | {count} | {range_text} |".format(
                question=item["question"],
                prob=f"{item['probability_percent']:.2f}%",
                count=item["source_market_count"],
                range_text=extract_range_text(item) or "n/a",
            )
        )
    return "\n".join(rows)


def order_summary_lines(order_instructions: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for order in order_instructions["orders"]:
        if order["direction"] == "FLAT":
            lines.append(f"- `{order['asset']}` stays flat with no generated order.")
        else:
            lines.append(
                f"- `{order['asset']}` order instruction: {order['direction']} {format_usd(order['notional_usd'])} notional."
            )
    return lines


def wti_rationale(position_table: dict[str, Any]) -> str:
    position = next(item for item in position_table["positions"] if item["asset"] == "WTI")
    if position["direction"] == "FLAT":
        return "WTI is excluded from the active book because the oil and shipping signals are mixed, so the constrained scoring rule preserves a flat stance."
    return (
        f"WTI is included as a {position['direction']} position because the oil signal cleared the ambiguity threshold. "
        f"The size stays small at {format_usd(position['notional_usd'])} because the base thesis on WTI is explicitly uncertain."
    )


def build_research_brief(snapshot: dict[str, Any], position_table: dict[str, Any], order_instructions: dict[str, Any]) -> str:
    macro_lines = classify_macro_read(snapshot)
    challenges = thesis_challenges(snapshot, position_table)
    orders = order_summary_lines(order_instructions)

    sections = [
        "# Long/Short Portfolio Research Brief",
        "",
        "## Live Macro Snapshot",
        "",
        markdown_forecast_table(snapshot),
        "",
        "## Macro Read",
        "",
        *[f"- {line}" for line in macro_lines],
        "",
        "## Thesis Challenges",
        "",
        *[f"- {line}" for line in challenges],
        "",
        "## Sized Position Table",
        "",
        markdown_position_table(position_table),
        "",
        "## WTI Include/Exclude Rationale",
        "",
        wti_rationale(position_table),
        "",
        "## Order Instructions",
        "",
        *orders,
    ]
    return "\n".join(sections).strip() + "\n"


def build_prompt_text() -> str:
    return """You have access to the PolyBridge MCP tool.

My directional thesis:
- Short BERA: high token supply, no clear PMF, founder conviction signals low
- Short OP: declining sequencer revenue, ongoing token unlocks, fading narrative
- Long BTC: fixed supply, maximum decentralisation, actual PMF
- Uncertain WTI: geopolitics highly uncertain, need data before sizing
- Lean long SPX: AI tailwind structural but macro risks real

Use PolyBridge Forecast on exactly these five questions:
1. Will there be meaningful US crypto regulatory reform by Q2 2027?
2. Will the Fed cut rates before September 2026?
3. Will the US enter a recession by end of 2026?
4. Will the Strait of Hormuz reopen to regular traffic by June 30, 2026?
5. Will WTI crude oil exceed $90 in June 2026?

Portfolio constraints:
- Total notional budget: $50,000
- Notional USD sizing only
- Total absolute notional must stay less than or equal to $50,000
- No single position may exceed 40% of total notional
- WTI may be FLAT if the signal is mixed

Output format:
1. Macro read from the five PolyBridge results
2. Thesis challenges where market evidence argues against my view
3. Sized position table for BTC, SPX, OP, BERA, and WTI
4. Order instructions JSON
""".strip()


def build_agent_session(snapshot: dict[str, Any], position_table: dict[str, Any], order_instructions: dict[str, Any]) -> str:
    macro_lines = classify_macro_read(snapshot)
    challenges = thesis_challenges(snapshot, position_table)
    order_lines = order_summary_lines(order_instructions)

    forecast_lines: list[str] = []
    for index, item in enumerate(snapshot["questions"], start=1):
        forecast_lines.extend(
            [
                f"{index}. **{item['question']}**",
                f"   - Probability: {item['probability_percent']:.2f}%",
                f"   - Source markets: {item['source_market_count']}",
            ]
        )
        range_text = extract_range_text(item)
        if range_text:
            forecast_lines.append(f"   - Range: {range_text}")
        confidence = item.get("confidence")
        if confidence is not None:
            if isinstance(confidence, (int, float)):
                forecast_lines.append(f"   - Confidence: {format_percent(float(confidence))}")
            else:
                forecast_lines.append(f"   - Confidence: {confidence}")
        reasoning = clean_text(item.get("reasoning"))
        if reasoning:
            forecast_lines.append(f"   - Reasoning: {reasoning}")

    sections = [
        "# REST-backed agent-style portfolio workflow",
        "",
        "This file was generated by `portfolio_sizing.py` from live REST Forecast calls. It is not a literal Claude transcript.",
        "",
        "The same prompt lives in the cookbook `PROMPT.md`. A future user can copy it into Claude Desktop with the PolyBridge MCP release installed and reproduce the qualitative workflow there.",
        "",
        "PolyBridge MCP release: https://github.com/crowdvector/polybridge-search-mcp/releases/tag/polybridge-mcp-v0.2.4",
        "",
        "## Prompt",
        "",
        "```text",
        build_prompt_text(),
        "```",
        "",
        "## Forecast Outputs",
        "",
        *forecast_lines,
        "",
        "## Assistant-Style Synthesis",
        "",
        "### Macro Read",
        "",
        *[f"- {line}" for line in macro_lines],
        "",
        "### Thesis Challenges",
        "",
        *[f"- {line}" for line in challenges],
        "",
        "### Position Table",
        "",
        markdown_position_table(position_table),
        "",
        "### Order Instructions",
        "",
        *order_lines,
    ]
    return "\n".join(sections).strip() + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def write_text(path: Path, contents: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    preferred = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for candidate in preferred:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_summary_png(snapshot: dict[str, Any], position_table: dict[str, Any], output_path: Path) -> Path:
    from PIL import Image, ImageDraw

    output_path.parent.mkdir(parents=True, exist_ok=True)

    width, height = 1600, 980
    background = "#071017"
    surface = "#0d1923"
    border = "#1c3242"
    accent = "#f5ae2e"
    blue = "#59b7ff"
    green = "#46d39a"
    red = "#ff7d7d"
    text_primary = "#f6f7f9"
    text_secondary = "#a8b7c5"
    text_muted = "#7c8c9b"

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    title_font = load_font(52, bold=True)
    subtitle_font = load_font(24)
    heading_font = load_font(28, bold=True)
    body_font = load_font(22)
    small_font = load_font(18)
    mono_font = load_font(20)

    draw.rounded_rectangle((38, 34, width - 38, height - 34), radius=26, outline=border, width=2, fill=background)
    draw.ellipse((1170, -40, 1570, 360), fill="#112438")
    draw.ellipse((40, 700, 360, 1020), fill="#102030")

    draw.text((82, 78), "PolyBridge long/short portfolio", fill=accent, font=small_font)
    draw.text((82, 112), "Macro snapshot and constrained portfolio sizing", fill=text_primary, font=title_font)
    draw.text((82, 180), "Five live Forecast probabilities converted into USD notionals.", fill=text_secondary, font=subtitle_font)
    draw.text((82, 222), f"Generated {snapshot['generated_at']} UTC", fill=text_muted, font=small_font)

    left = 82
    top = 290
    card_width = 660
    card_height = 84
    gap = 18

    for index, item in enumerate(snapshot["questions"]):
        y0 = top + index * (card_height + gap)
        draw.rounded_rectangle((left, y0, left + card_width, y0 + card_height), radius=18, fill=surface, outline=border, width=2)
        label = QUESTION_LABELS.get(item["question"], item["question"])
        draw.text((left + 22, y0 + 16), label, fill=text_primary, font=body_font)
        draw.text((left + 22, y0 + 48), f"{item['source_market_count']} source markets", fill=text_muted, font=small_font)

        probability_fraction = clamp(float(item["probability"]))
        bar_left = left + 380
        bar_top = y0 + 46
        bar_width = 220
        draw.rounded_rectangle((bar_left, bar_top, bar_left + bar_width, bar_top + 12), radius=6, fill="#173042")
        draw.rounded_rectangle(
            (bar_left, bar_top, bar_left + int(bar_width * probability_fraction), bar_top + 12),
            radius=6,
            fill=blue,
        )
        draw.text((left + 560, y0 + 18), f"{item['probability_percent']:.1f}%", fill=text_primary, font=heading_font)

    right_left = 790
    draw.rounded_rectangle((right_left, 290, width - 82, 818), radius=22, fill=surface, outline=border, width=2)
    draw.text((right_left + 28, 316), "Portfolio positions", fill=text_primary, font=heading_font)
    draw.text((right_left + 28, 354), "USD notionals capped at $50,000 total absolute notional.", fill=text_secondary, font=small_font)

    row_y = 404
    row_gap = 76
    for position in position_table["positions"]:
        color = text_muted if position["direction"] == "FLAT" else green if position["direction"] == "LONG" else red
        draw.text((right_left + 28, row_y), position["asset"], fill=text_primary, font=body_font)
        draw.text((right_left + 170, row_y), position["direction"], fill=color, font=body_font)
        draw.text((right_left + 330, row_y), format_usd(position["notional_usd"]), fill=text_primary, font=body_font)
        draw.text((right_left + 500, row_y), f"{position['percent_of_total_notional']:.1f}%", fill=text_secondary, font=mono_font)
        draw.text((right_left + 28, row_y + 32), position["rationale"], fill=text_muted, font=small_font)
        row_y += row_gap

    image.save(output_path)
    return output_path


def run_once(output_dir: Path | None = None, prompt_for_key: bool = False) -> tuple[WorkflowPaths, dict[str, Any]]:
    base_dir = Path(__file__).resolve().parent
    assets_dir = output_dir or (base_dir / "assets")
    snapshot = build_macro_snapshot(prompt_for_key=prompt_for_key)
    position_table = build_position_table(snapshot)
    order_instructions = build_order_instructions(position_table)
    research_brief = build_research_brief(snapshot, position_table, order_instructions)
    agent_session = build_agent_session(snapshot, position_table, order_instructions)

    macro_snapshot_path = write_json(assets_dir / "macro-snapshot.json", snapshot)
    position_table_path = write_json(assets_dir / "position-table.json", position_table)
    order_instructions_path = write_json(assets_dir / "order-instructions.json", order_instructions)
    research_brief_path = write_text(assets_dir / "research-brief.md", research_brief)
    agent_session_path = write_text(assets_dir / "agent-session.md", agent_session)
    portfolio_summary_png = render_summary_png(snapshot, position_table, assets_dir / "portfolio-summary.png")

    paths = WorkflowPaths(
        macro_snapshot=macro_snapshot_path,
        position_table=position_table_path,
        order_instructions=order_instructions_path,
        research_brief=research_brief_path,
        agent_session=agent_session_path,
        portfolio_summary_png=portfolio_summary_png,
    )

    bundle = {
        "macro_snapshot": snapshot,
        "position_table": position_table,
        "order_instructions": order_instructions,
        "research_brief": research_brief,
        "agent_session": agent_session,
    }
    return paths, bundle


def main() -> None:
    try:
        paths, bundle = run_once(prompt_for_key=False)
    except ForecastShapeError as exc:
        message = {
            "error": "null-or-missing probability returned by Forecast",
            "question": exc.question,
            "sanitized_response_shape": exc.shape,
        }
        print(json.dumps(message, indent=2))
        raise SystemExit(1)

    print("Completed long/short portfolio sizing.")
    print(json.dumps(paths.as_dict(), indent=2))
    for item in bundle["macro_snapshot"]["questions"]:
        print(
            f"- {QUESTION_LABELS.get(item['question'], item['question'])}: "
            f"{item['probability_percent']:.2f}% from {item['source_market_count']} source markets"
        )


if __name__ == "__main__":
    main()
