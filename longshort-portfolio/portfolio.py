#!/usr/bin/env python3
"""Long-short portfolio from PolyBridge Forecast price-threshold probabilities.

Usage:
    python3 portfolio.py
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

API_URL = "https://api.polybridge.ai/v1/forecast"
TIMEOUT = 75
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 2.0

HORIZON = "July 31, 2026"
BUDGET_USD = 50_000
MAX_POS = 0.40
KELLY = 0.50
CEILING = 1.5
ROUNDING_INCREMENT_USD = 100

UNIVERSE = {
    "BTC": 74_000,
    "SPX": 7_580,
    "OP": 0.12,
    "BERA": 0.38,
    "WTI": 87.00,
}

FACTORS = [0.60, 0.85, 1.15, 1.50]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    return max(0.0, min(1.0, round(number, 6)))


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


def load_api_key(prompt_if_missing: bool = False) -> str | None:
    api_key = clean_text(os.getenv("POLYBRIDGE_API_KEY"))
    if api_key:
        return api_key
    if prompt_if_missing:
        from getpass import getpass

        return clean_text(getpass("POLYBRIDGE_API_KEY for advanced workflows (press Enter to skip): "))
    return None


def raise_auth_error(response: requests.Response, api_key: str | None) -> None:
    if api_key:
        raise RuntimeError(
            f"PolyBridge Forecast authentication failed with HTTP {response.status_code}. "
            "The configured POLYBRIDGE_API_KEY was rejected; remove it to use anonymous "
            "limits or set a valid key."
        )
    raise RuntimeError(
        f"PolyBridge Forecast anonymous request was rejected with HTTP {response.status_code}. "
        "Retry without adding Authorization, or set a valid configured key."
    )


def thresholds_for(spot: float) -> list[float]:
    raw = [spot * factor for factor in FACTORS]
    if spot >= 1000:
        return [round(value, -2) for value in raw]
    if spot >= 10:
        return [float(round(value)) for value in raw]
    return [round(value, 2) for value in raw]


def format_price(value: float) -> str:
    if value >= 1000:
        return f"${value:,.0f}"
    if value >= 10:
        return f"${value:,.0f}"
    return f"${value:.2f}"


def forecast(session: requests.Session, api_key: str | None, question: str) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"question": question}
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = session.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= MAX_RETRIES:
                raise
            time.sleep(min(20.0, BACKOFF_BASE_SECONDS * (2**attempt)))
            continue

        if response.status_code in {429, 503}:
            if attempt >= MAX_RETRIES:
                response.raise_for_status()
            wait_seconds = normalize_retry_after(response.headers.get("Retry-After"))
            if wait_seconds is None:
                wait_seconds = min(20.0, BACKOFF_BASE_SECONDS * (2**attempt))
            time.sleep(wait_seconds)
            continue

        if response.status_code in {401, 403}:
            raise_auth_error(response, api_key)

        response.raise_for_status()
        return response.json()

    raise RuntimeError(f"Forecast request failed for question: {question}") from last_error


def source_count(payload: dict[str, Any]) -> int | str:
    markets_used = payload.get("markets_used")
    if isinstance(markets_used, list):
        return len(markets_used)
    return payload.get("source_market_count", "?")


def confidence_interval(payload: dict[str, Any]) -> Any:
    return payload.get("confidence_interval") or payload.get("confidenceInterval")


def fetch_survival_curve(
    session: requests.Session,
    api_key: str | None,
    asset: str,
    thresholds: list[float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for threshold in thresholds:
        question = f"Will {asset} exceed {format_price(threshold)} on {HORIZON}?"
        result = forecast(session, api_key, question)
        probability = normalize_unit_interval(result.get("probability"))
        count = source_count(result)
        print(f"  {question:<70} {format_probability(probability):>7}  ({count} sources)")
        row: dict[str, Any] = {
            "threshold": threshold,
            "question": question,
            "raw_probability": probability,
            "source_count": count,
        }
        interval = confidence_interval(result)
        if interval is not None:
            row["confidence_interval"] = interval
        rows.append(row)
    return rows


def clip_monotonic(rows: list[dict[str, Any]]) -> bool:
    changed = False
    previous: float | None = None
    for row in rows:
        probability = row.get("raw_probability")
        if probability is None:
            clipped = 0.0
        else:
            clipped = float(probability)
        if previous is not None and clipped > previous:
            clipped = previous
            changed = True
        row["clipped_probability"] = round(clipped, 6)
        previous = clipped
    return changed


def implied_distribution(thresholds: list[float], survival: list[float]) -> list[dict[str, float]]:
    bands: list[dict[str, float]] = []
    below_probability = 1.0 - survival[0]
    if below_probability > 1e-9:
        bands.append(
            {
                "lower": 0.0,
                "upper": thresholds[0],
                "midpoint": thresholds[0] / 2.0,
                "probability": below_probability,
            }
        )

    for index in range(len(thresholds) - 1):
        probability = survival[index] - survival[index + 1]
        if probability > 1e-9:
            bands.append(
                {
                    "lower": thresholds[index],
                    "upper": thresholds[index + 1],
                    "midpoint": (thresholds[index] + thresholds[index + 1]) / 2.0,
                    "probability": probability,
                }
            )

    if survival[-1] > 1e-9:
        ceiling = thresholds[-1] * CEILING
        bands.append(
            {
                "lower": thresholds[-1],
                "upper": ceiling,
                "midpoint": (thresholds[-1] + ceiling) / 2.0,
                "probability": survival[-1],
            }
        )

    return bands


def expected_return_and_vol(bands: list[dict[str, float]], spot: float) -> tuple[float, float, float]:
    expected_price = sum(row["midpoint"] * row["probability"] for row in bands)
    expected_price_sq = sum((row["midpoint"] ** 2) * row["probability"] for row in bands)
    variance = max(0.0, expected_price_sq - expected_price**2)
    return expected_price, (expected_price - spot) / spot, math.sqrt(variance) / spot


def signed_direction(value: float) -> str:
    if value > 0:
        return "LONG"
    if value < 0:
        return "SHORT"
    return "FLAT"


def round_notional(value: float) -> int:
    return int(round(value / ROUNDING_INCREMENT_USD) * ROUNDING_INCREMENT_USD)


def size_portfolio(results: dict[str, dict[str, Any]]) -> dict[str, int]:
    cap = MAX_POS * BUDGET_USD
    signed = {}
    for asset, data in results.items():
        expected_return = data["expected_return"]
        implied_vol = data["implied_vol"]
        weight = (KELLY * expected_return / (implied_vol**2)) if implied_vol > 1e-9 else 0.0
        signed[asset] = max(-cap, min(cap, weight * BUDGET_USD))

    gross = sum(abs(value) for value in signed.values())
    if gross > BUDGET_USD:
        scale = BUDGET_USD / gross
        signed = {asset: value * scale for asset, value in signed.items()}

    rounded = {asset: round_notional(value) for asset, value in signed.items()}
    rounded_gross = sum(abs(value) for value in rounded.values())
    if rounded_gross > BUDGET_USD:
        scale = BUDGET_USD / rounded_gross
        rounded = {asset: round_notional(value * scale) for asset, value in rounded.items()}

    return rounded


def format_probability(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.0%}"


def format_percent(value: float) -> str:
    return f"{value:+.2%}"


def asset_result(asset: str, spot: float, rows: list[dict[str, Any]]) -> dict[str, Any]:
    thresholds = [row["threshold"] for row in rows]
    survival = [float(row["clipped_probability"]) for row in rows]
    bands = implied_distribution(thresholds, survival)
    expected_price, expected_return, implied_vol = expected_return_and_vol(bands, spot)
    return {
        "asset": asset,
        "spot": spot,
        "thresholds": thresholds,
        "survival": rows,
        "distribution_bands": bands,
        "expected_price": expected_price,
        "expected_return": expected_return,
        "implied_vol": implied_vol,
    }


def build_survival_asset(generated_at: str, results: dict[str, dict[str, Any]], clipped_assets: list[str]) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "horizon": HORIZON,
        "budget_usd": BUDGET_USD,
        "max_single_position_usd": int(MAX_POS * BUDGET_USD),
        "kelly_fraction": KELLY,
        "threshold_factors": FACTORS,
        "universe": UNIVERSE,
        "clipped_assets": clipped_assets,
        "assets": [
            {
                "asset": asset,
                "spot": data["spot"],
                "thresholds": [
                    {
                        "threshold": row["threshold"],
                        "question": row["question"],
                        "raw_probability": row["raw_probability"],
                        "clipped_probability": row["clipped_probability"],
                        "source_count": row["source_count"],
                        **({"confidence_interval": row["confidence_interval"]} if "confidence_interval" in row else {}),
                    }
                    for row in data["survival"]
                ],
            }
            for asset, data in results.items()
        ],
    }


def build_sizing_asset(generated_at: str, results: dict[str, dict[str, Any]], positions: dict[str, int]) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "horizon": HORIZON,
        "budget_usd": BUDGET_USD,
        "max_single_position_usd": int(MAX_POS * BUDGET_USD),
        "kelly_fraction": KELLY,
        "gross_notional_usd": sum(abs(value) for value in positions.values()),
        "universe": UNIVERSE,
        "positions": [
            {
                "asset": asset,
                "direction": signed_direction(positions[asset]),
                "expected_price": round(results[asset]["expected_price"], 6),
                "expected_return": round(results[asset]["expected_return"], 6),
                "implied_vol": round(results[asset]["implied_vol"], 6),
                "signed_notional_usd": positions[asset],
                "notional_usd": abs(positions[asset]),
            }
            for asset in results
        ],
    }


def build_orders(generated_at: str, positions: dict[str, int]) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "horizon": HORIZON,
        "venue": "Hyperliquid",
        "instrument": "1x_perp",
        "orders": [
            {
                "asset": asset,
                "direction": signed_direction(notional),
                "notional_usd": abs(notional),
            }
            for asset, notional in positions.items()
        ],
    }


def write_json(path: Path, data: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def print_sizing_table(results: dict[str, dict[str, Any]], positions: dict[str, int]) -> None:
    print(f"\n{'Asset':<6} {'Dir':<6} {'E[r]':>8} {'Vol':>8} {'Notional':>12}")
    print("-" * 46)
    for asset, data in results.items():
        notional = positions[asset]
        print(
            f"{asset:<6} {signed_direction(notional):<6} "
            f"{format_percent(data['expected_return']):>8} "
            f"{data['implied_vol']:>7.2%} ${abs(notional):>10,}"
        )
    gross = sum(abs(value) for value in positions.values())
    print(f"\nGross: ${gross:,} / ${BUDGET_USD:,}")


def run_once(output_dir: Path | None = None, prompt_for_key: bool = False) -> tuple[dict[str, Path], dict[str, Any]]:
    api_key = load_api_key(prompt_if_missing=prompt_for_key)
    generated_at = utc_now_iso()
    results: dict[str, dict[str, Any]] = {}
    clipped_assets: list[str] = []

    print(f"Horizon: {HORIZON}")
    print(f"Budget:  ${BUDGET_USD:,}\n")
    print("Survival probabilities")

    with requests.Session() as session:
        for asset, spot in UNIVERSE.items():
            print(f"\n{asset} (spot {format_price(spot)})")
            thresholds = thresholds_for(spot)
            rows = fetch_survival_curve(session, api_key, asset, thresholds)
            if clip_monotonic(rows):
                clipped_assets.append(asset)
                print(f"  warning: clipped non-monotonic survival probabilities for {asset}")
            results[asset] = asset_result(asset, spot, rows)

    positions = size_portfolio(results)
    print_sizing_table(results, positions)

    survival_asset = build_survival_asset(generated_at, results, clipped_assets)
    sizing_asset = build_sizing_asset(generated_at, results, positions)
    orders = build_orders(generated_at, positions)

    print("\nHyperliquid 1x perp order instructions")
    print(json.dumps(orders, indent=2))

    base_dir = Path(__file__).resolve().parent
    assets_dir = output_dir or (base_dir / "assets")
    paths = {
        "survival_probabilities": write_json(assets_dir / "survival-probabilities.json", survival_asset),
        "sizing_table": write_json(assets_dir / "sizing-table.json", sizing_asset),
        "order_instructions": write_json(assets_dir / "order-instructions.json", orders),
    }
    return paths, {"survival": survival_asset, "sizing": sizing_asset, "orders": orders}


def main() -> int:
    run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
