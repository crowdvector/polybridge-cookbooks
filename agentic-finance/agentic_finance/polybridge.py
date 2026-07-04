from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from .redaction import redact_string

FORECAST_ENDPOINT = "https://api.polybridge.ai/v1/forecast"
SEARCH_ENDPOINT = "https://api.polybridge.ai/v1/search"
REQUEST_TIMEOUT_SECONDS = 75
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 2.0


class PolyBridgeError(RuntimeError):
    """Raised when the optional live PolyBridge adapter cannot fetch evidence."""


class PolyBridgeAuthError(PolyBridgeError):
    """Raised when a configured PolyBridge API key is rejected."""


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
    try:
        return float(text)
    except ValueError:
        return None


def retry_after_seconds(value: str | None) -> float | None:
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


class PolyBridgeClient:
    def __init__(
        self,
        api_key: str | None = None,
        session: Any | None = None,
        timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.api_key = clean_text(api_key if api_key is not None else os.getenv("POLYBRIDGE_API_KEY"))
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sleep = sleep
        if session is None:
            import requests

            self.session = requests.Session()
        else:
            self.session = session

    def forecast(self, question: str) -> dict[str, Any]:
        return self._post("forecast", FORECAST_ENDPOINT, {"question": question})

    def search(self, query: str) -> dict[str, Any]:
        return self._post("search", SEARCH_ENDPOINT, {"query": query})

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, label: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = self._headers()

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except Exception as exc:  # requests and fake sessions expose different exception types.
                if attempt >= self.max_retries:
                    message = redact_string(str(exc))
                    raise PolyBridgeError(f"PolyBridge {label} request failed: {message}") from exc
                self.sleep(min(20.0, BACKOFF_BASE_SECONDS * (2**attempt)))
                continue

            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code in {429, 503}:
                if attempt >= self.max_retries:
                    raise PolyBridgeError(f"PolyBridge {label} request failed with HTTP {status_code}.")
                response_headers = getattr(response, "headers", {}) or {}
                wait_seconds = retry_after_seconds(response_headers.get("Retry-After"))
                if wait_seconds is None:
                    wait_seconds = min(20.0, BACKOFF_BASE_SECONDS * (2**attempt))
                self.sleep(wait_seconds)
                continue

            if status_code in {401, 403}:
                if self.api_key:
                    raise PolyBridgeAuthError(
                        f"PolyBridge {label} authentication failed with HTTP {status_code}. "
                        "The configured POLYBRIDGE_API_KEY was rejected."
                    )
                raise PolyBridgeError(f"PolyBridge anonymous {label} request failed with HTTP {status_code}.")

            if status_code < 200 or status_code >= 300:
                raise PolyBridgeError(f"PolyBridge {label} request failed with HTTP {status_code}.")

            try:
                data = response.json()
            except ValueError as exc:
                raise PolyBridgeError(f"PolyBridge {label} response was not valid JSON.") from exc
            if not isinstance(data, dict):
                raise PolyBridgeError(f"PolyBridge {label} response JSON was not an object.")
            return data

        raise PolyBridgeError(f"PolyBridge {label} request failed after retries.")
