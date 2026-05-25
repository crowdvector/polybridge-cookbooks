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

import matplotlib
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from scipy.optimize import minimize

matplotlib.use("Agg")

import matplotlib.pyplot as plt

API_BASE_URL = "https://api.polybridge.ai"
FORECAST_ENDPOINT = f"{API_BASE_URL}/v1/forecast"
REQUEST_TIMEOUT_SECONDS = 75
MAX_RETRIES = 6
BACKOFF_BASE_SECONDS = 2.0
PUBLIC_MIN_INTERVAL_SECONDS = 6.1
ANNUALIZATION_FACTOR = 252

ASSETS = ["SPY", "TLT", "GLD", "XLE", "VIXY"]
SCENARIO_QUESTIONS = {
    "recession": "Will the US enter a recession by end of 2026?",
    "fed_cut": "Will the Fed cut rates before September 2026?",
    "vol_spike": "Will VIX close above 30 in the next 42 days?",
}
CONDITIONAL_QUESTIONS = {
    "recession": {
        "SPY": ("Given a US recession in 2026, will SPY fall more than 25% by the end of 2026?", -0.25),
        "TLT": ("Given a US recession in 2026, will TLT rise more than 10% by the end of 2026?", 0.10),
        "GLD": ("Given a US recession in 2026, will GLD rise more than 10% by the end of 2026?", 0.10),
        "XLE": ("Given a US recession in 2026, will XLE fall more than 20% by the end of 2026?", -0.20),
        "VIXY": ("Given a US recession in 2026, will VIXY rise more than 50% by the end of 2026?", 0.50),
    },
    "fed_cut": {
        "SPY": ("Given a Fed cut before September 2026, will SPY rise more than 8% by the end of 2026?", 0.08),
        "TLT": ("Given a Fed cut before September 2026, will TLT rise more than 8% by the end of 2026?", 0.08),
        "GLD": ("Given a Fed cut before September 2026, will GLD rise more than 5% by the end of 2026?", 0.05),
        "XLE": ("Given a Fed cut before September 2026, will XLE rise more than 5% by the end of 2026?", 0.05),
        "VIXY": ("Given a Fed cut before September 2026, will VIXY fall more than 20% by the end of 2026?", -0.20),
    },
    "vol_spike": {
        "SPY": (
            "Given VIX closes above 30 in the next 42 days, will SPY fall more than 10% over the same 42-day period?",
            -0.10,
        ),
        "TLT": (
            "Given VIX closes above 30 in the next 42 days, will TLT rise more than 5% over the same 42-day period?",
            0.05,
        ),
        "GLD": (
            "Given VIX closes above 30 in the next 42 days, will GLD rise more than 5% over the same 42-day period?",
            0.05,
        ),
        "XLE": (
            "Given VIX closes above 30 in the next 42 days, will XLE fall more than 10% over the same 42-day period?",
            -0.10,
        ),
        "VIXY": (
            "Given VIX closes above 30 in the next 42 days, will VIXY rise more than 80% over the same 42-day period?",
            0.80,
        ),
    },
}

ROOT = Path(__file__).resolve().parent
ASSETS_DIR = ROOT / "assets"
SNAPSHOT_PATH = ASSETS_DIR / "snapshot.json"
SUMMARY_PATH = ASSETS_DIR / "allocation-summary.json"
COVARIANCE_PATH = ASSETS_DIR / "covariance-matrix.csv"
SCENARIO_CHART_PATH = ASSETS_DIR / "scenario-probabilities.png"
IMPLIED_RETURNS_CHART_PATH = ASSETS_DIR / "implied-return-distributions.png"
ALLOCATION_CHART_PATH = ASSETS_DIR / "allocation-output.png"

BACKGROUND = "#06111f"
SURFACE = "#0d1a2c"
SURFACE_ALT = "#12233a"
BORDER = "#1c3550"
TEXT_PRIMARY = "#f6fbff"
TEXT_SECONDARY = "#9fb6cf"
TEXT_MUTED = "#6e87a3"
ACCENT = "#67d6ff"
ACCENT_ALT = "#3fb1ff"
ACCENT_GOLD = "#f5b341"
POSITIVE = "#4fd3b2"
NEGATIVE = "#ff7b72"
ASSET_COLORS = {
    "SPY": "#67d6ff",
    "TLT": "#a88bff",
    "GLD": "#f5b341",
    "XLE": "#ff8c5a",
    "VIXY": "#61d8bf",
}


@dataclass
class WorkflowPaths:
    snapshot: Path
    summary: Path
    covariance_csv: Path
    scenario_chart: Path
    implied_returns_chart: Path
    allocation_chart: Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def log(message: str) -> None:
    print(message, flush=True)


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
        "or use notebook mode so it can prompt via getpass()."
    )


class ForecastClient:
    def __init__(
        self,
        api_key: str,
        min_interval_seconds: float = PUBLIC_MIN_INTERVAL_SECONDS,
        timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        self.api_key = api_key
        self.min_interval_seconds = min_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.next_request_at = 0.0
        self.session = requests.Session()

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "ForecastClient":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _wait_for_slot(self) -> None:
        now = time.monotonic()
        if self.next_request_at > now:
            time.sleep(self.next_request_at - now)

    def _mark_request_complete(self) -> None:
        self.next_request_at = time.monotonic() + self.min_interval_seconds

    def forecast(self, question: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"question": question}
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            log(f"[forecast] {question}")
            self._wait_for_slot()
            try:
                response = self.session.post(
                    FORECAST_ENDPOINT,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except requests.exceptions.RequestException as exc:
                last_error = exc
                self._mark_request_complete()
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Forecast request failed for question: {question}") from exc
                wait_seconds = min(30.0, BACKOFF_BASE_SECONDS * (2**attempt))
                log(f"[retry] request error on '{question}' attempt {attempt + 1}; waiting {wait_seconds:.1f}s")
                time.sleep(wait_seconds)
                continue

            self._mark_request_complete()
            if response.status_code in {429, 503}:
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"Forecast request failed after retries for question: {question} "
                        f"(HTTP {response.status_code})"
                    )
                retry_after_seconds = normalize_retry_after(response.headers.get("Retry-After"))
                backoff_seconds = min(30.0, BACKOFF_BASE_SECONDS * (2**attempt))
                wait_seconds = max(
                    self.min_interval_seconds,
                    backoff_seconds,
                    retry_after_seconds if retry_after_seconds is not None else 0.0,
                )
                log(
                    f"[retry] HTTP {response.status_code} on '{question}' attempt {attempt + 1}; "
                    f"waiting {wait_seconds:.1f}s"
                )
                time.sleep(wait_seconds)
                continue

            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                raise RuntimeError(
                    f"Forecast request failed for question: {question} (HTTP {response.status_code})"
                ) from exc

            try:
                return response.json()
            except ValueError as exc:
                raise RuntimeError(f"Forecast response was not valid JSON for question: {question}") from exc

        raise RuntimeError(f"Forecast request failed for question: {question}") from last_error


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
    if probability is None:
        api_error = clean_text(first_present(payload, ["error", "reasoning", "message"]))
        if api_error:
            raise RuntimeError(
                f"Forecast returned no usable probability for question: {question}. "
                f"API detail: {api_error}"
            )
        raise RuntimeError(f"Forecast response did not contain a usable probability for question: {question}")

    raw_markets = payload.get("markets_used")
    markets = (
        [market for market in (sanitize_market(item) for item in raw_markets if isinstance(item, dict)) if market]
        if isinstance(raw_markets, list)
        else []
    )

    result: dict[str, Any] = {
        "question": question,
        "probability": probability,
        "probability_percent": round(probability * 100.0, 2),
        "source_market_count": len(markets),
        "source_markets": markets,
    }

    reasoning = clean_text(first_present(payload, ["reasoning", "summary", "explanation"]))
    if reasoning:
        result["reasoning"] = reasoning

    confidence = normalize_unit_interval(first_present(payload, ["confidence", "confidence_score", "confidenceScore"]))
    if confidence is not None:
        result["confidence"] = confidence

    return result


def fetch_scenarios(client: ForecastClient) -> dict[str, dict[str, Any]]:
    scenario_details: dict[str, dict[str, Any]] = {}
    for scenario_name, question in SCENARIO_QUESTIONS.items():
        payload = client.forecast(question)
        scenario_details[scenario_name] = sanitize_forecast(question, payload)
        log(
            f"[scenario] {scenario_name} "
            f"{scenario_details[scenario_name]['probability']:.2%} "
            f"({scenario_details[scenario_name]['source_market_count']} source markets)"
        )
    return scenario_details


def fetch_conditionals(client: ForecastClient) -> dict[str, dict[str, dict[str, Any]]]:
    conditional_details: dict[str, dict[str, dict[str, Any]]] = {}
    for scenario_name, asset_map in CONDITIONAL_QUESTIONS.items():
        conditional_details[scenario_name] = {}
        for asset, (question, threshold) in asset_map.items():
            payload = client.forecast(question)
            result = sanitize_forecast(question, payload)
            result["threshold"] = threshold
            conditional_details[scenario_name][asset] = result
            log(
                f"[conditional] {scenario_name}/{asset} "
                f"{result['probability']:.2%} at threshold {threshold:+.0%} "
                f"({result['source_market_count']} source markets)"
            )
    return conditional_details


def download_price_history() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    log("[yfinance] downloading two years of adjusted daily prices")
    try:
        downloaded = yf.download(
            ASSETS,
            period="2y",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception as exc:
        raise RuntimeError(f"Yahoo Finance download failed: {exc}") from exc

    if downloaded is None or downloaded.empty:
        raise RuntimeError("Yahoo Finance download returned no data.")

    if isinstance(downloaded.columns, pd.MultiIndex):
        if "Close" not in downloaded.columns.get_level_values(0):
            raise RuntimeError("Yahoo Finance data did not include adjusted close prices.")
        prices = downloaded["Close"].copy()
    elif "Close" in downloaded.columns:
        prices = downloaded[["Close"]].rename(columns={"Close": ASSETS[0]})
    else:
        raise RuntimeError("Yahoo Finance data did not include a Close column.")

    if not isinstance(prices, pd.DataFrame):
        prices = pd.DataFrame(prices)

    prices = prices.loc[:, [asset for asset in ASSETS if asset in prices.columns]].dropna(how="any")
    missing_assets = [asset for asset in ASSETS if asset not in prices.columns]
    if missing_assets:
        raise RuntimeError(f"Yahoo Finance data is missing assets: {', '.join(missing_assets)}")
    if prices.empty:
        raise RuntimeError("Yahoo Finance prices were empty after aligning assets.")

    returns = prices.pct_change().dropna(how="any")
    if returns.empty:
        raise RuntimeError("Daily returns were empty after computing percentage changes.")

    covariance = returns.cov() * ANNUALIZATION_FACTOR
    metadata = {
        "source": "yfinance",
        "price_field": "Close with auto_adjust=True",
        "assets": ASSETS,
        "annualization_factor": ANNUALIZATION_FACTOR,
        "price_lookback_start": prices.index[0].date().isoformat(),
        "price_lookback_end": prices.index[-1].date().isoformat(),
        "return_lookback_start": returns.index[0].date().isoformat(),
        "return_lookback_end": returns.index[-1].date().isoformat(),
        "price_observation_count": int(len(prices)),
        "return_observation_count": int(len(returns)),
    }
    return prices, returns, covariance, metadata


def scenario_probabilities(scenario_details: dict[str, dict[str, Any]]) -> dict[str, float]:
    return {name: float(item["probability"]) for name, item in scenario_details.items()}


def scenario_source_counts(scenario_details: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {name: int(item["source_market_count"]) for name, item in scenario_details.items()}


def conditional_probabilities(
    conditional_details: dict[str, dict[str, dict[str, Any]]]
) -> dict[str, dict[str, float]]:
    return {
        scenario_name: {asset: float(item["probability"]) for asset, item in asset_map.items()}
        for scenario_name, asset_map in conditional_details.items()
    }


def conditional_source_counts(
    conditional_details: dict[str, dict[str, dict[str, Any]]]
) -> dict[str, dict[str, int]]:
    return {
        scenario_name: {asset: int(item["source_market_count"]) for asset, item in asset_map.items()}
        for scenario_name, asset_map in conditional_details.items()
    }


def thresholds() -> dict[str, dict[str, float]]:
    return {
        scenario_name: {asset: float(threshold) for asset, (_, threshold) in asset_map.items()}
        for scenario_name, asset_map in CONDITIONAL_QUESTIONS.items()
    }


def normalize_scenario_weights(probabilities: dict[str, float]) -> dict[str, float]:
    total = float(sum(probabilities.values()))
    if total <= 0:
        raise RuntimeError("Scenario probabilities summed to zero; cannot normalize weights.")
    return {name: value / total for name, value in probabilities.items()}


def scenario_expected_returns(
    conditional_details: dict[str, dict[str, dict[str, Any]]]
) -> dict[str, dict[str, float]]:
    scenario_views: dict[str, dict[str, float]] = {}
    for scenario_name, asset_map in conditional_details.items():
        scenario_views[scenario_name] = {}
        for asset, item in asset_map.items():
            scenario_views[scenario_name][asset] = float(item["probability"]) * float(item["threshold"])
    return scenario_views


def probability_weighted_expected_returns(
    scenario_weights: dict[str, float],
    scenario_views: dict[str, dict[str, float]],
) -> dict[str, float]:
    expected_returns: dict[str, float] = {}
    for asset in ASSETS:
        expected_returns[asset] = float(
            sum(scenario_weights[scenario_name] * scenario_views[scenario_name][asset] for scenario_name in scenario_weights)
        )
    return expected_returns


def optimize_allocation(expected_returns: dict[str, float], covariance: pd.DataFrame) -> dict[str, Any]:
    mu = np.array([expected_returns[asset] for asset in ASSETS], dtype=float)
    cov = covariance.loc[ASSETS, ASSETS].to_numpy(dtype=float)
    n_assets = len(ASSETS)
    equal_weight = np.repeat(1.0 / n_assets, n_assets)

    def negative_sharpe(weights: np.ndarray) -> float:
        portfolio_variance = float(weights @ cov @ weights)
        portfolio_vol = math.sqrt(max(portfolio_variance, 0.0))
        if portfolio_vol <= 1e-12:
            return 0.0
        return -float(weights @ mu) / portfolio_vol

    result = minimize(
        negative_sharpe,
        equal_weight,
        method="SLSQP",
        bounds=[(0.02, 0.40)] * n_assets,
        constraints=[{"type": "eq", "fun": lambda weights: float(np.sum(weights) - 1.0)}],
        options={"ftol": 1e-9, "maxiter": 500},
    )
    if not result.success:
        raise RuntimeError(f"Portfolio optimization failed: {result.message}")

    optimized_weights = result.x
    equal_weight_return = float(equal_weight @ mu)
    equal_weight_vol = math.sqrt(max(float(equal_weight @ cov @ equal_weight), 0.0))
    optimized_return = float(optimized_weights @ mu)
    optimized_vol = math.sqrt(max(float(optimized_weights @ cov @ optimized_weights), 0.0))

    optimized = {asset: float(weight) for asset, weight in zip(ASSETS, optimized_weights)}
    equal = {asset: float(weight) for asset, weight in zip(ASSETS, equal_weight)}
    tilt = {asset: optimized[asset] - equal[asset] for asset in ASSETS}

    return {
        "optimized_allocation": optimized,
        "equal_weight_baseline": equal,
        "tilt_vs_equal": tilt,
        "expected_portfolio_return": optimized_return,
        "expected_volatility": optimized_vol,
        "equal_weight_expected_return": equal_weight_return,
        "equal_weight_volatility": equal_weight_vol,
        "optimized_sharpe": optimized_return / optimized_vol if optimized_vol else None,
        "equal_weight_sharpe": equal_weight_return / equal_weight_vol if equal_weight_vol else None,
    }


def build_snapshot(prompt_for_key: bool = False) -> tuple[dict[str, Any], pd.DataFrame]:
    api_key = load_api_key(prompt_if_missing=prompt_for_key)
    with ForecastClient(api_key=api_key) as client:
        scenario_details = fetch_scenarios(client)
        conditional_details = fetch_conditionals(client)

    _, _, covariance, covariance_metadata = download_price_history()

    scenario_probs = scenario_probabilities(scenario_details)
    scenario_weights = normalize_scenario_weights(scenario_probs)
    conditional_probs = conditional_probabilities(conditional_details)
    cond_source_counts = conditional_source_counts(conditional_details)
    scenario_views = scenario_expected_returns(conditional_details)
    expected_returns = probability_weighted_expected_returns(scenario_weights, scenario_views)
    optimizer_output = optimize_allocation(expected_returns, covariance)

    snapshot = {
        "generated_at": utc_now_iso(),
        "api_base_url": API_BASE_URL,
        "forecast_endpoint": FORECAST_ENDPOINT,
        "not_financial_advice": True,
        "methodology_note": "Market-implied snapshot using PolyBridge Forecast probabilities and Yahoo Finance covariance data.",
        "request_settings": {
            "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "max_retries": MAX_RETRIES,
            "client_min_interval_seconds": PUBLIC_MIN_INTERVAL_SECONDS,
            "concurrency": 1,
        },
        "assets": ASSETS,
        "scenario_questions": SCENARIO_QUESTIONS,
        "scenario_probabilities": scenario_probs,
        "scenario_source_market_counts": scenario_source_counts(scenario_details),
        "scenario_details": scenario_details,
        "conditional_probabilities": conditional_probs,
        "conditional_source_market_counts": cond_source_counts,
        "conditional_details": conditional_details,
        "thresholds": thresholds(),
        "scenario_normalized_weights": scenario_weights,
        "scenario_conditional_expected_returns": scenario_views,
        "expected_returns_per_asset": expected_returns,
        "expected_portfolio_return": optimizer_output["expected_portfolio_return"],
        "expected_volatility": optimizer_output["expected_volatility"],
        "equal_weight_baseline": optimizer_output["equal_weight_baseline"],
        "optimized_allocation": optimizer_output["optimized_allocation"],
        "tilt_vs_equal": optimizer_output["tilt_vs_equal"],
        "equal_weight_expected_return": optimizer_output["equal_weight_expected_return"],
        "equal_weight_volatility": optimizer_output["equal_weight_volatility"],
        "optimized_sharpe": optimizer_output["optimized_sharpe"],
        "equal_weight_sharpe": optimizer_output["equal_weight_sharpe"],
        "yahoo_finance_lookback": {
            "price_start": covariance_metadata["price_lookback_start"],
            "price_end": covariance_metadata["price_lookback_end"],
            "return_start": covariance_metadata["return_lookback_start"],
            "return_end": covariance_metadata["return_lookback_end"],
        },
        "trading_day_count": covariance_metadata["return_observation_count"],
        "covariance_metadata": covariance_metadata,
    }
    return snapshot, covariance


def format_percent(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.{digits}f}%"


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def write_covariance_csv(covariance: pd.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    covariance.loc[ASSETS, ASSETS].to_csv(output_path, index=True)
    return output_path


def build_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": snapshot["generated_at"],
        "not_financial_advice": True,
        "assets": snapshot["assets"],
        "scenario_probabilities": snapshot["scenario_probabilities"],
        "scenario_normalized_weights": snapshot["scenario_normalized_weights"],
        "expected_returns_per_asset": snapshot["expected_returns_per_asset"],
        "equal_weight_baseline": snapshot["equal_weight_baseline"],
        "optimized_allocation": snapshot["optimized_allocation"],
        "tilt_vs_equal": snapshot["tilt_vs_equal"],
        "expected_portfolio_return": snapshot["expected_portfolio_return"],
        "expected_volatility": snapshot["expected_volatility"],
        "equal_weight_expected_return": snapshot["equal_weight_expected_return"],
        "equal_weight_volatility": snapshot["equal_weight_volatility"],
        "optimized_sharpe": snapshot["optimized_sharpe"],
        "equal_weight_sharpe": snapshot["equal_weight_sharpe"],
        "yahoo_finance_lookback": snapshot["yahoo_finance_lookback"],
        "trading_day_count": snapshot["trading_day_count"],
        "generated_assets": {
            "snapshot": str(SNAPSHOT_PATH.relative_to(ROOT)),
            "summary": str(SUMMARY_PATH.relative_to(ROOT)),
            "covariance_csv": str(COVARIANCE_PATH.relative_to(ROOT)),
            "scenario_chart": str(SCENARIO_CHART_PATH.relative_to(ROOT)),
            "implied_returns_chart": str(IMPLIED_RETURNS_CHART_PATH.relative_to(ROOT)),
            "allocation_chart": str(ALLOCATION_CHART_PATH.relative_to(ROOT)),
        },
    }


def setup_figure(fig: plt.Figure) -> None:
    fig.patch.set_facecolor(BACKGROUND)


def render_scenario_probabilities(snapshot: dict[str, Any], output_path: Path) -> Path:
    probs = snapshot["scenario_probabilities"]
    counts = snapshot["scenario_source_market_counts"]
    labels = ["Recession", "Fed Cut", "Vol Spike"]
    keys = ["recession", "fed_cut", "vol_spike"]
    values = [probs[key] * 100.0 for key in keys]
    source_counts = [counts[key] for key in keys]

    fig, ax = plt.subplots(figsize=(11, 6), dpi=150)
    setup_figure(fig)
    ax.set_facecolor(SURFACE)
    bars = ax.bar(labels, values, color=[ACCENT, ACCENT_ALT, ACCENT_GOLD], width=0.6)

    for spine in ax.spines.values():
        spine.set_color(BORDER)
    ax.grid(axis="y", color=BORDER, alpha=0.4, linewidth=0.8)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=11)
    ax.set_ylim(0, max(100.0, max(values) + 15.0))
    ax.set_ylabel("Probability", color=TEXT_SECONDARY, fontsize=11)
    ax.set_title("PolyBridge Scenario Probabilities", color=TEXT_PRIMARY, fontsize=18, pad=18, loc="left")
    ax.text(
        0.0,
        1.03,
        f"Live snapshot {snapshot['generated_at']} UTC • market-implied, not financial advice",
        transform=ax.transAxes,
        color=TEXT_MUTED,
        fontsize=10,
    )

    for bar, value, source_count in zip(bars, values, source_counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            value + 2.0,
            f"{value:.1f}%\n{source_count} source markets",
            ha="center",
            va="bottom",
            color=TEXT_PRIMARY,
            fontsize=10,
            fontweight="bold",
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_implied_return_distributions(snapshot: dict[str, Any], output_path: Path) -> Path:
    conditional_details = snapshot["conditional_details"]
    scenario_weights = snapshot["scenario_normalized_weights"]
    scenario_views = snapshot["scenario_conditional_expected_returns"]
    scenario_names = [
        ("recession", "Recession"),
        ("fed_cut", "Fed Cut"),
        ("vol_spike", "Vol Spike"),
    ]

    max_threshold_percent = max(
        abs(details["threshold"]) * 100.0
        for scenario in conditional_details.values()
        for details in scenario.values()
    )

    x_padding = max(14.0, max_threshold_percent * 0.22)
    outer_label_offset = max(2.0, max_threshold_percent * 0.035)
    inner_label_offset = max(3.0, max_threshold_percent * 0.05)

    fig, axes = plt.subplots(3, 1, figsize=(15.5, 13.8), dpi=150, sharex=True)
    setup_figure(fig)

    for ax, (scenario_key, scenario_label) in zip(axes, scenario_names):
        ax.set_facecolor(SURFACE)
        ax.axvline(0, color=BORDER, linewidth=1.2)
        ax.grid(axis="x", color=BORDER, alpha=0.35, linewidth=0.8)
        ax.set_yticks(range(len(ASSETS)))
        ax.set_yticklabels(ASSETS, color=TEXT_SECONDARY, fontsize=11)
        ax.tick_params(axis="x", colors=TEXT_SECONDARY, labelsize=10)
        ax.tick_params(axis="y", length=0)
        for spine in ax.spines.values():
            spine.set_color(BORDER)

        for row, asset in enumerate(ASSETS):
            item = conditional_details[scenario_key][asset]
            threshold_pct = item["threshold"] * 100.0
            probability = item["probability"]
            expected_return = scenario_views[scenario_key][asset] * 100.0
            color = ASSET_COLORS[asset]
            alpha = 0.2 + (0.75 * probability)
            ax.barh(
                row,
                threshold_pct,
                height=0.56,
                color=color,
                alpha=alpha,
                edgecolor=color,
                linewidth=1.0,
            )

            if threshold_pct >= 0:
                if threshold_pct >= (max_threshold_percent - x_padding * 0.6):
                    label_x = threshold_pct - inner_label_offset
                    label_ha = "right"
                else:
                    label_x = threshold_pct + outer_label_offset
                    label_ha = "left"
            else:
                if abs(threshold_pct) >= (max_threshold_percent - x_padding * 0.6):
                    label_x = threshold_pct + inner_label_offset
                    label_ha = "left"
                else:
                    label_x = threshold_pct - outer_label_offset
                    label_ha = "right"

            ax.text(
                label_x,
                row,
                f"p={probability * 100:.1f}%  E[r]={expected_return:+.1f}%",
                ha=label_ha,
                va="center",
                color=TEXT_PRIMARY,
                fontsize=9,
            )

        ax.set_title(
            f"{scenario_label} • normalized scenario weight {scenario_weights[scenario_key] * 100:.1f}%",
            color=TEXT_PRIMARY,
            fontsize=14,
            loc="left",
            pad=12,
        )
        ax.margins(x=0.02)

    axes[0].text(
        0.0,
        1.19,
        "Conditional Threshold Probability Mass",
        transform=axes[0].transAxes,
        color=TEXT_PRIMARY,
        fontsize=20,
        fontweight="bold",
    )
    axes[0].text(
        0.0,
        1.10,
        f"Threshold bars show the return hurdle. Opacity scales with PolyBridge probability. Snapshot {snapshot['generated_at']} UTC.",
        transform=axes[0].transAxes,
        color=TEXT_MUTED,
        fontsize=10,
    )
    axes[-1].set_xlim(-(max_threshold_percent + x_padding), max_threshold_percent + x_padding)
    axes[-1].set_xlabel("Return threshold (%)", color=TEXT_SECONDARY, fontsize=11)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.subplots_adjust(left=0.15, right=0.96, top=0.88, bottom=0.075, hspace=0.42)
    fig.savefig(output_path, facecolor=fig.get_facecolor(), dpi=150)
    plt.close(fig)
    return output_path


def render_allocation_output(snapshot: dict[str, Any], output_path: Path) -> Path:
    equal_weight = snapshot["equal_weight_baseline"]
    optimized = snapshot["optimized_allocation"]
    tilt = snapshot["tilt_vs_equal"]

    equal_values = [equal_weight[asset] * 100.0 for asset in ASSETS]
    optimized_values = [optimized[asset] * 100.0 for asset in ASSETS]
    tilt_values = [tilt[asset] * 100.0 for asset in ASSETS]
    x_positions = np.arange(len(ASSETS))
    width = 0.34

    fig = plt.figure(figsize=(14, 8.5), dpi=150, facecolor=BACKGROUND)
    grid = fig.add_gridspec(1, 2, width_ratios=[2.2, 1.0], wspace=0.18)
    ax_alloc = fig.add_subplot(grid[0, 0])
    ax_tilt = fig.add_subplot(grid[0, 1])

    for ax in (ax_alloc, ax_tilt):
        ax.set_facecolor(SURFACE)
        for spine in ax.spines.values():
            spine.set_color(BORDER)

    ax_alloc.bar(x_positions - width / 2.0, equal_values, width=width, color=TEXT_MUTED, alpha=0.75, label="Equal")
    ax_alloc.bar(
        x_positions + width / 2.0,
        optimized_values,
        width=width,
        color=[ASSET_COLORS[asset] for asset in ASSETS],
        alpha=0.95,
        label="Optimized",
    )
    ax_alloc.set_xticks(x_positions)
    ax_alloc.set_xticklabels(ASSETS, color=TEXT_SECONDARY, fontsize=11)
    ax_alloc.tick_params(axis="y", colors=TEXT_SECONDARY, labelsize=10)
    ax_alloc.grid(axis="y", color=BORDER, alpha=0.35, linewidth=0.8)
    ax_alloc.set_ylabel("Portfolio weight (%)", color=TEXT_SECONDARY, fontsize=11)
    ax_alloc.set_title("Equal Weight vs Optimized Allocation", color=TEXT_PRIMARY, fontsize=18, loc="left", pad=16)
    ax_alloc.text(
        0.0,
        1.03,
        f"Expected return {snapshot['expected_portfolio_return'] * 100:.2f}% • volatility {snapshot['expected_volatility'] * 100:.2f}%",
        transform=ax_alloc.transAxes,
        color=TEXT_MUTED,
        fontsize=10,
    )
    legend = ax_alloc.legend(facecolor=SURFACE_ALT, edgecolor=BORDER, labelcolor=TEXT_PRIMARY, fontsize=10)
    for text in legend.get_texts():
        text.set_color(TEXT_PRIMARY)

    for position, value in zip(x_positions + width / 2.0, optimized_values):
        ax_alloc.text(position, value + 1.0, f"{value:.1f}%", ha="center", va="bottom", color=TEXT_PRIMARY, fontsize=9)

    tilt_colors = [POSITIVE if value >= 0 else NEGATIVE for value in tilt_values]
    ax_tilt.axvline(0, color=BORDER, linewidth=1.2)
    ax_tilt.barh(ASSETS, tilt_values, color=tilt_colors, alpha=0.9)
    ax_tilt.tick_params(axis="x", colors=TEXT_SECONDARY, labelsize=10)
    ax_tilt.tick_params(axis="y", colors=TEXT_SECONDARY, labelsize=11)
    ax_tilt.grid(axis="x", color=BORDER, alpha=0.35, linewidth=0.8)
    ax_tilt.set_xlabel("Tilt vs equal (%)", color=TEXT_SECONDARY, fontsize=11)
    ax_tilt.set_title("Active Tilts", color=TEXT_PRIMARY, fontsize=16, loc="left", pad=16)

    for asset, value in zip(ASSETS, tilt_values):
        ax_tilt.text(
            value + (0.6 if value >= 0 else -0.6),
            asset,
            f"{value:+.1f}%",
            va="center",
            ha="left" if value >= 0 else "right",
            color=TEXT_PRIMARY,
            fontsize=9,
        )

    fig.text(0.06, 0.965, "Portfolio Allocation Output", color=TEXT_PRIMARY, fontsize=20, fontweight="bold")
    fig.text(
        0.06,
        0.935,
        f"Live snapshot {snapshot['generated_at']} UTC • market-implied, not financial advice",
        color=TEXT_MUTED,
        fontsize=10,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(output_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return output_path


def run_once(prompt_for_key: bool = False) -> tuple[WorkflowPaths, dict[str, Any]]:
    log("[workflow] starting portfolio allocation run")
    snapshot, covariance = build_snapshot(prompt_for_key=prompt_for_key)
    summary = build_summary(snapshot)

    write_json(SNAPSHOT_PATH, snapshot)
    write_json(SUMMARY_PATH, summary)
    write_covariance_csv(covariance, COVARIANCE_PATH)
    render_scenario_probabilities(snapshot, SCENARIO_CHART_PATH)
    render_implied_return_distributions(snapshot, IMPLIED_RETURNS_CHART_PATH)
    render_allocation_output(snapshot, ALLOCATION_CHART_PATH)
    log("[workflow] wrote snapshot, summary, covariance CSV, and chart assets")

    return (
        WorkflowPaths(
            snapshot=SNAPSHOT_PATH,
            summary=SUMMARY_PATH,
            covariance_csv=COVARIANCE_PATH,
            scenario_chart=SCENARIO_CHART_PATH,
            implied_returns_chart=IMPLIED_RETURNS_CHART_PATH,
            allocation_chart=ALLOCATION_CHART_PATH,
        ),
        snapshot,
    )


def print_console_summary(snapshot: dict[str, Any], paths: WorkflowPaths) -> None:
    print("Generated portfolio allocation snapshot.")
    print(f"Snapshot: {paths.snapshot}")
    print(f"Summary : {paths.summary}")
    print(f"CSV     : {paths.covariance_csv}")
    print(f"Charts  : {paths.scenario_chart}, {paths.implied_returns_chart}, {paths.allocation_chart}")
    print()
    print("Scenario probabilities:")
    for key, label in [("recession", "Recession"), ("fed_cut", "Fed cut"), ("vol_spike", "Vol spike")]:
        probability = snapshot["scenario_probabilities"][key]
        source_count = snapshot["scenario_source_market_counts"][key]
        print(f"  {label:<10} {probability:.2%}  ({source_count} source markets)")
    print()
    print("Optimized allocation:")
    for asset in ASSETS:
        print(
            f"  {asset:<5} {snapshot['optimized_allocation'][asset]:.2%}  "
            f"(tilt {snapshot['tilt_vs_equal'][asset]:+.2%} vs equal)"
        )
    print()
    print(f"Expected return : {snapshot['expected_portfolio_return']:.2%}")
    print(f"Expected vol    : {snapshot['expected_volatility']:.2%}")


def main() -> None:
    paths, snapshot = run_once(prompt_for_key=False)
    print_console_summary(snapshot, paths)


if __name__ == "__main__":
    main()
