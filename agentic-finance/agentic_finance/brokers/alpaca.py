from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ..models import ALLOWED_USE, FinancialActionIntent, GateDecision, PaperOrderPreview
from ..redaction import REDACTED, redact_string


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
REQUEST_TIMEOUT_SECONDS = 30


class AlpacaPaperError(RuntimeError):
    """Raised when optional Alpaca paper validation cannot complete safely."""


class AlpacaPaperAuthError(AlpacaPaperError):
    """Raised when Alpaca paper credentials are rejected."""


@dataclass(frozen=True)
class AlpacaPaperConfig:
    api_key: str | None
    api_secret: str | None
    base_url: str = PAPER_BASE_URL
    paper_trade: str | None = None
    schema_version: str = "alpaca_paper_config.v1"

    def redacted(self) -> dict[str, str | None]:
        return {
            "schema_version": self.schema_version,
            "api_key": REDACTED if self.api_key else None,
            "api_secret": REDACTED if self.api_secret else None,
            "base_url": self.base_url,
            "paper_trade": self.paper_trade,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_base_url(value: str | None) -> str:
    text = clean_text(value) or PAPER_BASE_URL
    return text.rstrip("/")


def read_alpaca_paper_config_from_env(environ: dict[str, str] | None = None) -> AlpacaPaperConfig:
    if environ is None:
        environ = os.environ
    return AlpacaPaperConfig(
        api_key=clean_text(environ.get("APCA_API_KEY_ID") or environ.get("ALPACA_API_KEY")),
        api_secret=clean_text(environ.get("APCA_API_SECRET_KEY") or environ.get("ALPACA_SECRET_KEY")),
        base_url=normalize_base_url(environ.get("APCA_API_BASE_URL")),
        paper_trade=clean_text(environ.get("ALPACA_PAPER_TRADE")),
    )


def is_paper_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return False
    if hostname == "api.alpaca.markets":
        return False
    if base_url.rstrip("/") == PAPER_BASE_URL:
        return True
    return "paper" in hostname and "alpaca.markets" in hostname


def validate_alpaca_paper_config(config: AlpacaPaperConfig) -> AlpacaPaperConfig:
    base_url = normalize_base_url(config.base_url)
    if not config.api_key or not config.api_secret:
        raise AlpacaPaperError(
            "Alpaca paper validation requires APCA_API_KEY_ID/APCA_API_SECRET_KEY "
            "or ALPACA_API_KEY/ALPACA_SECRET_KEY."
        )
    if config.paper_trade is not None and config.paper_trade.lower() != "true":
        raise AlpacaPaperError("ALPACA_PAPER_TRADE must be true for Alpaca paper validation.")
    if not is_paper_base_url(base_url):
        raise AlpacaPaperError(
            "Live-looking Alpaca base URL is blocked. Use the paper endpoint "
            f"{PAPER_BASE_URL}."
        )
    return AlpacaPaperConfig(
        api_key=config.api_key,
        api_secret=config.api_secret,
        base_url=base_url,
        paper_trade=config.paper_trade,
    )


def redact_alpaca_message(message: str) -> str:
    text = redact_string(message)
    text = re.sub(r"\bAPCA-API-KEY-ID\b\s*[:=]\s*[^,\s}]+", REDACTED, text)
    text = re.sub(r"\bAPCA-API-SECRET-KEY\b\s*[:=]\s*[^,\s}]+", REDACTED, text)
    text = text.replace("APCA-API-KEY-ID", REDACTED)
    text = text.replace("APCA-API-SECRET-KEY", REDACTED)
    return text


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


class AlpacaPaperClient:
    def __init__(
        self,
        config: AlpacaPaperConfig,
        session: Any | None = None,
        timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.config = validate_alpaca_paper_config(config)
        self.timeout_seconds = timeout_seconds
        if session is None:
            import requests

            self.session = requests.Session()
        else:
            self.session = session

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.config.api_key or "",
            "APCA-API-SECRET-KEY": self.config.api_secret or "",
            "Accept": "application/json",
        }

    def _account_url(self) -> str:
        return f"{self.config.base_url}/v2/account"

    def get_account_metadata(self) -> dict[str, Any]:
        try:
            response = self.session.get(
                self._account_url(),
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            message = redact_alpaca_message(str(exc))
            raise AlpacaPaperError(f"Alpaca paper account validation request failed: {message}") from exc

        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code in {401, 403}:
            raise AlpacaPaperAuthError(f"Alpaca paper account validation failed with HTTP {status_code}.")
        if status_code < 200 or status_code >= 300:
            raise AlpacaPaperError(f"Alpaca paper account validation failed with HTTP {status_code}.")

        try:
            data = response.json()
        except ValueError as exc:
            raise AlpacaPaperError("Alpaca paper account validation response was not valid JSON.") from exc
        if not isinstance(data, dict):
            raise AlpacaPaperError("Alpaca paper account validation response JSON was not an object.")
        return sanitize_account_metadata(data)

    def build_order_payload(self, preview: PaperOrderPreview) -> dict[str, Any]:
        if preview.broker != "alpaca" or preview.mode != "paper_preview_only":
            raise AlpacaPaperError("Only Alpaca paper-preview objects can be converted to payloads.")
        if preview.submit_supported:
            raise AlpacaPaperError("Order payload preview requires submit_supported=false.")
        return {
            "symbol": preview.symbol,
            "side": preview.side,
            "type": "market",
            "time_in_force": "day",
            "notional": f"{preview.notional_usd:.2f}",
            "extended_hours": False,
            "client_order_id": None,
            "preview_only": True,
            "submit_supported": False,
        }


def sanitize_account_metadata(data: dict[str, Any]) -> dict[str, Any]:
    account_present = any(data.get(key) for key in ("id", "account_id", "account_number"))
    buying_power_present = data.get("buying_power") not in (None, "")
    return {
        "schema_version": "alpaca_paper_account_check.v1",
        "broker": "alpaca",
        "mode": "paper_account_validation",
        "paper_endpoint_validated": True,
        "account_status": clean_text(data.get("status")) or "unknown",
        "trading_blocked": bool(data.get("trading_blocked", False)),
        "transfers_blocked": bool(data.get("transfers_blocked", False)),
        "account_id": REDACTED if account_present else None,
        "buying_power": REDACTED if buying_power_present else None,
        "allowed_use": ALLOWED_USE,
        "no_order_submission": True,
    }
