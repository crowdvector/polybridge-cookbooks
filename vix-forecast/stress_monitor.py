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
from matplotlib import patches

API_BASE_URL = "https://api.polybridge.ai"
FORECAST_ENDPOINT = f"{API_BASE_URL}/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 75
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 2.0

HEADLINE = "Will VIX close above 30 in the next 6 weeks?"

DRIVERS = [
    "Will crude oil settle above $90 in June 2026?",
    "Will SPX draw down more than 10% in the next 6 weeks?",
    "Will gold rise more than 10% in the next 6 weeks?",
    "Will the Strait of Hormuz reopen to regular traffic by June 30, 2026?",
]

QUESTIONS = [HEADLINE, *DRIVERS]

QUESTION_LABELS = {
    "Will VIX close above 30 in the next 6 weeks?": "VIX > 30 (6w)",
    "Will crude oil settle above $90 in June 2026?": "Crude > $90 (Jun 2026)",
    "Will SPX draw down more than 10% in the next 6 weeks?": "SPX drawdown > 10% (6w)",
    "Will gold rise more than 10% in the next 6 weeks?": "Gold +10% (6w)",
    "Will the Strait of Hormuz reopen to regular traffic by June 30, 2026?": "Hormuz reopens (Jun 30, 2026)",
}


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


def short_label(question: str) -> str:
    return QUESTION_LABELS.get(question, textwrap.shorten(question, width=42, placeholder="..."))


def format_percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    rounded = round(float(value), 1)
    if rounded.is_integer():
        return f"{int(rounded)}%"
    return f"{rounded:.1f}%"


def extract_range_text(item: dict[str, Any]) -> str | None:
    interval = item.get("confidence_interval")
    if isinstance(interval, dict):
        lower = interval.get("lower")
        upper = interval.get("upper")
        if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
            return f"Range {format_percent(lower * 100)} to {format_percent(upper * 100)}"

    probability_range = item.get("probability_range")
    if isinstance(probability_range, dict):
        lower = probability_range.get("low")
        upper = probability_range.get("high")
        if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
            return f"Range {format_percent(lower * 100)} to {format_percent(upper * 100)}"

    return None


def extract_confidence_text(item: dict[str, Any]) -> str | None:
    confidence = item.get("confidence")
    if isinstance(confidence, (int, float)):
        return f"Confidence {format_percent(confidence * 100)}"
    text = clean_text(confidence)
    if text:
        return f"Confidence {text}"
    return None


def load_snapshot(snapshot_path: Path) -> dict[str, Any]:
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def editorial_items(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in snapshot.get("questions", []):
        items.append(
            {
                "label": short_label(item.get("question", "Question unavailable")),
                "question": item.get("question", "Question unavailable"),
                "probability_percent": float(item.get("probability_percent") or 0.0),
                "range_text": extract_range_text(item),
                "confidence_text": extract_confidence_text(item),
                "source_market_count": int(item.get("source_market_count") or 0),
            }
        )
    return items


def render_chart(snapshot: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items = editorial_items(snapshot)

    background = "#07111d"
    surface = "#0d1929"
    surface_alt = "#102136"
    border = "#1e344c"
    primary_text = "#f7fbff"
    secondary_text = "#9db4cc"
    tertiary_text = "#6f89a3"
    accent_colors = ["#70d6ff", "#47b8ff", "#f5b23c", "#f6d24f", "#5dd0b2"]

    fig = plt.figure(figsize=(15, 8.5), dpi=120, facecolor=background)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Background glow accents for a more editorial hero treatment.
    for center, radius, color, alpha in [
        ((0.91, 0.89), 0.22, "#123861", 0.35),
        ((0.12, 0.08), 0.20, "#153550", 0.28),
    ]:
        ax.add_patch(patches.Circle(center, radius, color=color, alpha=alpha, lw=0))

    ax.text(
        0.06,
        0.93,
        "Live market snapshot",
        color=tertiary_text,
        fontsize=11,
        fontweight="bold",
        va="center",
    )
    ax.text(
        0.06,
        0.885,
        "PolyBridge Market Stress Monitor",
        color=primary_text,
        fontsize=28,
        fontweight="bold",
        va="center",
    )
    ax.text(
        0.06,
        0.845,
        "Market-implied probabilities from prediction markets.",
        color=secondary_text,
        fontsize=13,
        va="center",
    )

    pill = patches.FancyBboxPatch(
        (0.83, 0.905),
        0.11,
        0.038,
        boxstyle="round,pad=0.008,rounding_size=0.02",
        facecolor="#13273d",
        edgecolor=border,
        linewidth=1.0,
    )
    ax.add_patch(pill)
    ax.text(0.885, 0.924, "5 live questions", color=secondary_text, fontsize=10, ha="center", va="center")

    card_left = 0.05
    card_width = 0.90
    card_height = 0.115
    card_gap = 0.018
    start_y = 0.69

    for index, item in enumerate(items):
        y = start_y - index * (card_height + card_gap)
        accent = accent_colors[index % len(accent_colors)]
        face = surface if index % 2 == 0 else surface_alt

        card = patches.FancyBboxPatch(
            (card_left, y),
            card_width,
            card_height,
            boxstyle="round,pad=0.012,rounding_size=0.026",
            facecolor=face,
            edgecolor=border,
            linewidth=1.15,
        )
        ax.add_patch(card)

        ax.add_patch(
            patches.FancyBboxPatch(
                (card_left + 0.012, y + 0.018),
                0.008,
                card_height - 0.036,
                boxstyle="round,pad=0.0,rounding_size=0.01",
                facecolor=accent,
                edgecolor=accent,
                linewidth=0,
            )
        )

        ax.text(
            card_left + 0.036,
            y + 0.072,
            item["label"],
            color=primary_text,
            fontsize=15,
            fontweight="bold",
            va="center",
        )

        range_text = item["range_text"] or item["confidence_text"] or "Range unavailable"
        ax.text(
            card_left + 0.036,
            y + 0.038,
            range_text,
            color=secondary_text,
            fontsize=11,
            va="center",
        )

        percent_x = card_left + 0.62
        ax.text(
            percent_x,
            y + 0.065,
            format_percent(item["probability_percent"]),
            color=primary_text,
            fontsize=28,
            fontweight="bold",
            ha="left",
            va="center",
        )

        count_text = f"{item['source_market_count']} source market"
        if item["source_market_count"] != 1:
            count_text += "s"
        count_box = patches.FancyBboxPatch(
            (card_left + 0.77, y + 0.047),
            0.14,
            0.036,
            boxstyle="round,pad=0.008,rounding_size=0.018",
            facecolor="#12263b",
            edgecolor=border,
            linewidth=1.0,
        )
        ax.add_patch(count_box)
        ax.text(
            card_left + 0.84,
            y + 0.065,
            count_text,
            color=secondary_text,
            fontsize=10,
            ha="center",
            va="center",
        )

        bar_left = card_left + 0.62
        bar_bottom = y + 0.024
        bar_width = 0.29
        bar_height = 0.010
        ax.add_patch(
            patches.FancyBboxPatch(
                (bar_left, bar_bottom),
                bar_width,
                bar_height,
                boxstyle="round,pad=0.0,rounding_size=0.006",
                facecolor="#17304a",
                edgecolor="#17304a",
                linewidth=0,
            )
        )
        probability_fraction = max(0.012, min(1.0, item["probability_percent"] / 100.0)) if item["probability_percent"] > 0 else 0
        ax.add_patch(
            patches.FancyBboxPatch(
                (bar_left, bar_bottom),
                bar_width * probability_fraction,
                bar_height,
                boxstyle="round,pad=0.0,rounding_size=0.006",
                facecolor=accent,
                edgecolor=accent,
                linewidth=0,
            )
        )

    footer_text = f"Snapshot {snapshot.get('generated_at', 'unknown')} · Source: PolyBridge Forecast"
    ax.text(0.06, 0.07, footer_text, color=secondary_text, fontsize=10.5, va="center")
    ax.text(0.94, 0.07, "Prediction-market implied view", color=tertiary_text, fontsize=10, ha="right", va="center")

    fig.savefig(output_path, dpi=120, facecolor=background, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    return output_path


def render_alt_chart(snapshot: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items = editorial_items(snapshot)
    labels = [item["label"] for item in items]
    values = [max(0.0, min(100.0, item["probability_percent"])) for item in items]
    counts = [item["source_market_count"] for item in items]
    ranges = [item["range_text"] or item["confidence_text"] or "Range unavailable" for item in items]

    background = "#07111d"
    rail = "#193047"
    accent_colors = ["#70d6ff", "#47b8ff", "#f5b23c", "#f6d24f", "#5dd0b2"]
    primary_text = "#f7fbff"
    secondary_text = "#9db4cc"
    grid = "#284764"

    fig, ax = plt.subplots(figsize=(15, 8), dpi=120, facecolor=background)
    ax.set_facecolor(background)

    y_positions = list(range(len(items)))
    ax.barh(y_positions, [100.0] * len(items), color=rail, height=0.72)
    bars = ax.barh(y_positions, values, color=accent_colors[: len(items)], height=0.72)

    ax.set_xlim(0, 100)
    ax.set_ylim(-0.75, len(items) - 0.25)
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, color=primary_text, fontsize=15, fontweight="bold")
    ax.invert_yaxis()

    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], color=secondary_text, fontsize=12)
    ax.grid(axis="x", color=grid, linewidth=0.9, alpha=0.85)
    ax.tick_params(axis="y", length=0)

    for spine in ax.spines.values():
        spine.set_visible(False)

    for bar, value, count, range_text in zip(bars, values, counts, ranges):
        y_center = bar.get_y() + (bar.get_height() / 2.0)
        label_x = value + 1.6
        label_color = primary_text
        label_align = "left"
        if value >= 84.0:
            label_x = value - 1.8
            label_color = background
            label_align = "right"
        ax.text(
            label_x,
            y_center - 0.11,
            format_percent(value),
            va="center",
            ha=label_align,
            color=label_color,
            fontsize=20,
            fontweight="bold",
        )
        ax.text(
            100.0,
            y_center + 0.13,
            f"{range_text}  ·  {count} source markets",
            va="center",
            ha="right",
            color=secondary_text,
            fontsize=10.5,
        )

    fig.text(0.08, 0.94, "PolyBridge Market Stress Monitor", color=primary_text, fontsize=28, fontweight="bold")
    fig.text(
        0.08,
        0.905,
        "Market-implied probabilities from prediction markets.",
        color=secondary_text,
        fontsize=13,
    )
    fig.text(
        0.92,
        0.08,
        f"Snapshot {snapshot.get('generated_at', 'unknown')}",
        color=secondary_text,
        fontsize=10.5,
        ha="right",
    )

    plt.tight_layout(rect=(0.06, 0.12, 0.98, 0.88))
    fig.savefig(output_path, dpi=120, facecolor=background, bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    return output_path


def write_snapshot(snapshot: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return output_path


def print_summary(snapshot: dict[str, Any]) -> None:
    print("Market-implied snapshot from PolyBridge Forecast.")
    for item in snapshot.get("questions", []):
        probability = item.get("probability_percent")
        probability_text = f"{probability:.2f}%" if isinstance(probability, (int, float)) else "n/a"
        print(f"{probability_text:>8} | {item.get('source_market_count', 0):>2} markets | {item.get('question')}")


def render_snapshot_assets(
    snapshot_path: Path,
    chart_path: Path,
    alt_chart_path: Path | None = None,
) -> tuple[Path, Path | None, dict[str, Any]]:
    snapshot = load_snapshot(snapshot_path)
    main_chart = render_chart(snapshot, chart_path)
    alt_chart = render_alt_chart(snapshot, alt_chart_path) if alt_chart_path else None
    return main_chart, alt_chart, snapshot


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
