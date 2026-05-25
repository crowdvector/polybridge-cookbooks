#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import textwrap
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import matplotlib
import requests

matplotlib.use("Agg")

import matplotlib.pyplot as plt

API_BASE_URL = "https://api.polybridge.ai"
FORECAST_ENDPOINT = f"{API_BASE_URL}/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 75
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 2.0

QUESTIONS = [
    "Will VIX close above 30 in the next 42 days?",
    "Will crude oil settle above $90 in June 2026?",
    "Will SPX draw down more than 10% in the next 42 days?",
    "Will gold rise more than 10% in the next 42 days?",
    "Will the Strait of Hormuz reopen to regular traffic by June 30, 2026?",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def first_present(data: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
    return round(number, 6)


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

        api_key = clean_text(getpass("Paste POLYBRIDGE_API_KEY: "))
        if api_key:
            return api_key
    raise RuntimeError(
        "POLYBRIDGE_API_KEY is not set. Export it before running the script, "
        "or allow the notebook flow to prompt for it with getpass()."
    )


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
            time.sleep(min(20.0, BACKOFF_BASE_SECONDS * (2 ** attempt)))
            continue

        if response.status_code in {429, 503}:
            if attempt >= max_retries:
                response.raise_for_status()
            wait_seconds = normalize_retry_after(response.headers.get("Retry-After"))
            if wait_seconds is None:
                wait_seconds = min(20.0, BACKOFF_BASE_SECONDS * (2 ** attempt))
            time.sleep(wait_seconds)
            continue

        response.raise_for_status()
        return response.json()

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
        market["source"] = source

    probability = normalize_unit_interval(
        first_present(raw_market, ["probability", "yes_probability", "yesProbability", "price"])
    )
    if probability is not None:
        market["probability"] = probability

    question = clean_text(
        first_present(raw_market, ["question", "title", "name", "market_question", "marketTitle"])
    )
    if question:
        market["question"] = question

    url = clean_text(first_present(raw_market, ["platform_url", "platformUrl", "url", "market_url", "marketUrl"]))
    if url:
        market["url"] = url

    return market


def sanitize_forecast(question: str, payload: dict[str, Any]) -> dict[str, Any]:
    probability = normalize_unit_interval(first_present(payload, ["probability", "forecast", "p"]))
    raw_confidence = first_present(payload, ["confidence", "confidence_score", "confidenceScore"])
    numeric_confidence = normalize_unit_interval(raw_confidence)
    confidence: Any | None = numeric_confidence if numeric_confidence is not None else clean_text(raw_confidence)
    confidence_interval, probability_range = extract_interval_fields(payload)

    raw_markets = payload.get("markets_used")
    markets = (
        [
            market
            for market in (sanitize_market(item) for item in raw_markets if isinstance(item, dict))
            if market
        ]
        if isinstance(raw_markets, list)
        else []
    )

    result: dict[str, Any] = {
        "question": question,
        "probability": probability,
        "probability_percent": round(probability * 100.0, 2) if probability is not None else None,
        "confidence": confidence,
        "source_market_count": len(markets),
        "source_markets": markets,
    }

    if confidence_interval is not None:
        result["confidence_interval"] = confidence_interval
    if probability_range is not None:
        result["probability_range"] = probability_range

    reasoning = clean_text(first_present(payload, ["reasoning", "summary", "explanation"]))
    if reasoning:
        result["reasoning"] = reasoning

    return result


def build_snapshot(questions: list[str], prompt_for_key: bool = False) -> dict[str, Any]:
    api_key = load_api_key(prompt_if_missing=prompt_for_key)
    snapshot = {
        "generated_at": utc_now_iso(),
        "api_base_url": API_BASE_URL,
        "forecast_endpoint": FORECAST_ENDPOINT,
        "questions": [],
    }

    with requests.Session() as session:
        for question in questions:
            payload = forecast_question(session=session, api_key=api_key, question=question)
            snapshot["questions"].append(sanitize_forecast(question, payload))

    return snapshot


def render_chart(snapshot: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items = snapshot.get("questions", [])
    labels = [textwrap.fill(item.get("question", "Question unavailable"), width=34) for item in items]
    values = [max(0.0, min(100.0, float(item.get("probability_percent") or 0.0))) for item in items]
    counts = [item.get("source_market_count", 0) for item in items]

    background = "#08111f"
    rail = "#1b2b40"
    accent_colors = ["#5ecbff", "#70d6ff", "#f6ae2d", "#f4d35e", "#6dd3b6"]
    primary_text = "#f5f8ff"
    secondary_text = "#9fb3c8"
    grid = "#27415d"

    fig, ax = plt.subplots(figsize=(15, 9), facecolor=background)
    ax.set_facecolor(background)

    y_positions = list(range(len(items)))
    ax.barh(y_positions, [100.0] * len(items), color=rail, height=0.62)
    bars = ax.barh(y_positions, values, color=accent_colors[: len(items)], height=0.62)

    ax.set_xlim(0, 100)
    ax.set_ylim(-0.75, len(items) - 0.25)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, color=primary_text, fontsize=12)
    ax.invert_yaxis()

    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], color=secondary_text, fontsize=11)
    ax.grid(axis="x", color=grid, linewidth=0.8, alpha=0.8)
    ax.tick_params(axis="y", length=0)

    for spine in ax.spines.values():
        spine.set_visible(False)

    for bar, value, count in zip(bars, values, counts):
        y_center = bar.get_y() + (bar.get_height() / 2.0)
        label_x = value + 1.2
        label_color = primary_text
        label_align = "left"
        if value >= 88.0:
            label_x = value - 1.4
            label_color = background
            label_align = "right"
        ax.text(
            label_x,
            y_center - 0.06,
            f"{value:.1f}%",
            va="center",
            ha=label_align,
            color=label_color,
            fontsize=13,
            fontweight="bold",
        )
        ax.text(
            99.0,
            y_center + 0.17,
            f"{count} source markets",
            va="center",
            ha="right",
            color=secondary_text,
            fontsize=10,
        )

    fig.text(0.08, 0.94, "PolyBridge Market Stress Monitor", color=primary_text, fontsize=26, fontweight="bold")
    fig.text(
        0.08,
        0.905,
        "Live market-implied probabilities from prediction markets. Not financial advice.",
        color=secondary_text,
        fontsize=12,
    )
    fig.text(
        0.92,
        0.075,
        f"Snapshot: {snapshot.get('generated_at', 'unknown')}",
        color=secondary_text,
        fontsize=10,
        ha="right",
    )

    plt.tight_layout(rect=(0.06, 0.12, 0.98, 0.88))
    fig.savefig(output_path, dpi=200, facecolor=background, bbox_inches="tight")
    plt.close(fig)
    return output_path


def write_snapshot(snapshot: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return output_path


def print_summary(snapshot: dict[str, Any]) -> None:
    print("Market-implied snapshot from PolyBridge Forecast. Not financial advice.")
    for item in snapshot.get("questions", []):
        probability = item.get("probability_percent")
        probability_text = f"{probability:.2f}%" if isinstance(probability, (int, float)) else "n/a"
        print(f"{probability_text:>8} | {item.get('source_market_count', 0):>2} markets | {item.get('question')}")


def run_once(output_dir: Path | None = None, prompt_for_key: bool = False) -> tuple[Path, Path, dict[str, Any]]:
    base_dir = Path(__file__).resolve().parent
    assets_dir = output_dir or (base_dir / "assets")
    snapshot = build_snapshot(QUESTIONS, prompt_for_key=prompt_for_key)
    snapshot_path = write_snapshot(snapshot, assets_dir / "snapshot.json")
    chart_path = render_chart(snapshot, assets_dir / "market-stress-monitor.png")
    return snapshot_path, chart_path, snapshot


def main() -> int:
    snapshot_path, chart_path, snapshot = run_once()
    print_summary(snapshot)
    print(f"Wrote {snapshot_path}")
    print(f"Wrote {chart_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
