from __future__ import annotations

import os
import re
from collections.abc import Iterable
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ..models import ALLOWED_USE, FinancialActionIntent, GateDecision, PaperOrderPreview
from ..redaction import REDACTED, redact_string


PAPER_BASE_URL = "https://paper-api.alpaca.markets"
REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_PAPER_SUBMISSION_NOTIONAL_CAP_USD = 1000.0
DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST = ("SPY", "QQQ", "TLT", "GLD", "XLE", "AAPL")
ALLOWED_PAPER_SUBMISSION_SIDES = ("buy", "sell")


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

    def _orders_url(self) -> str:
        return f"{PAPER_BASE_URL}/v2/orders"

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


def normalize_symbol_allowlist(symbol_allowlist: Iterable[str] | None = None) -> tuple[str, ...]:
    source = symbol_allowlist or DEFAULT_PAPER_SUBMISSION_SYMBOL_ALLOWLIST
    normalized = tuple(sorted({str(symbol).strip().upper() for symbol in source if str(symbol).strip()}))
    if not normalized:
        raise AlpacaPaperError("Alpaca paper submission requires at least one allowlisted symbol.")
    return normalized


def validate_alpaca_paper_submission_config(config: AlpacaPaperConfig) -> AlpacaPaperConfig:
    validated = validate_alpaca_paper_config(config)
    if validated.paper_trade is None or validated.paper_trade.lower() != "true":
        raise AlpacaPaperError("ALPACA_PAPER_TRADE=true is required for guarded paper submission.")
    if validated.base_url != PAPER_BASE_URL:
        raise AlpacaPaperError(f"Guarded paper submission requires APCA_API_BASE_URL={PAPER_BASE_URL}.")
    return validated


def require_submission_confirmations(
    *,
    confirm_paper_trading: bool,
    confirm_not_financial_advice: bool,
    confirm_human_approval: bool,
) -> None:
    missing = []
    if not confirm_paper_trading:
        missing.append("--confirm-paper-trading")
    if not confirm_not_financial_advice:
        missing.append("--confirm-not-financial-advice")
    if not confirm_human_approval:
        missing.append("--confirm-human-approval")
    if missing:
        raise AlpacaPaperError(
            "Guarded paper submission requires explicit confirmation flags: "
            + ", ".join(missing)
            + "."
        )


def build_guarded_paper_order_payload(
    preview: PaperOrderPreview,
    *,
    max_notional_usd: float = DEFAULT_PAPER_SUBMISSION_NOTIONAL_CAP_USD,
    symbol_allowlist: Iterable[str] | None = None,
) -> dict[str, Any]:
    if preview.broker != "alpaca" or preview.mode != "paper_preview_only":
        raise AlpacaPaperError("Guarded paper submission requires an Alpaca paper-preview object.")
    if not preview.human_approval_required:
        raise AlpacaPaperError("Guarded paper submission requires a preview with human_approval_required=true.")
    if preview.submit_supported:
        raise AlpacaPaperError("Guarded paper submission requires submit_supported=false on the preview.")

    symbol = preview.symbol.strip().upper()
    allowed_symbols = normalize_symbol_allowlist(symbol_allowlist)
    if symbol not in allowed_symbols:
        raise AlpacaPaperError(f"Guarded paper submission blocked: symbol {symbol} is not allowlisted.")

    side = preview.side.strip().lower()
    if side not in ALLOWED_PAPER_SUBMISSION_SIDES:
        raise AlpacaPaperError(f"Guarded paper submission blocked: side {side!r} is not allowed.")

    notional = round(float(preview.notional_usd), 2)
    if notional <= 0:
        raise AlpacaPaperError("Guarded paper submission requires a positive notional value.")
    if max_notional_usd <= 0:
        raise AlpacaPaperError("Guarded paper submission requires a positive demo notional cap.")
    if notional > round(float(max_notional_usd), 2):
        raise AlpacaPaperError(
            "Guarded paper submission blocked: notional exceeds the configured demo cap."
        )

    return {
        "symbol": symbol,
        "side": side,
        "type": "market",
        "time_in_force": "day",
        "notional": f"{notional:.2f}",
    }


def sanitize_paper_submission_result(
    data: dict[str, Any],
    payload: dict[str, Any],
    *,
    human_approval_confirmed: bool,
) -> dict[str, Any]:
    order_present = any(data.get(key) for key in ("id", "order_id"))
    client_order_present = data.get("client_order_id") not in (None, "")
    return {
        "schema_version": "alpaca_paper_submission_result.v1",
        "broker": "alpaca",
        "mode": "paper_submission_result",
        "submitted": True,
        "paper_endpoint_validated": True,
        "order_id": REDACTED if order_present else None,
        "client_order_id": REDACTED if client_order_present else None,
        "symbol": payload["symbol"],
        "side": payload["side"],
        "notional": payload["notional"],
        "status": clean_text(data.get("status")) or "unknown",
        "allowed_use": ALLOWED_USE,
        "no_live_trading": True,
        "human_approval_confirmed": bool(human_approval_confirmed),
    }


def submit_paper_order(
    preview: PaperOrderPreview,
    config: AlpacaPaperConfig,
    *,
    gate_decision: GateDecision,
    confirm_paper_trading: bool,
    confirm_not_financial_advice: bool,
    confirm_human_approval: bool,
    max_notional_usd: float = DEFAULT_PAPER_SUBMISSION_NOTIONAL_CAP_USD,
    symbol_allowlist: Iterable[str] | None = None,
    session: Any | None = None,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    require_submission_confirmations(
        confirm_paper_trading=confirm_paper_trading,
        confirm_not_financial_advice=confirm_not_financial_advice,
        confirm_human_approval=confirm_human_approval,
    )
    if not gate_decision.cleared_for_paper_preview:
        raise AlpacaPaperError("Evidence Gate did not clear; guarded paper submission is blocked.")
    submission_config = validate_alpaca_paper_submission_config(config)
    payload = build_guarded_paper_order_payload(
        preview,
        max_notional_usd=max_notional_usd,
        symbol_allowlist=symbol_allowlist,
    )
    client = AlpacaPaperClient(submission_config, session=session, timeout_seconds=timeout_seconds)
    try:
        response = client.session.post(
            client._orders_url(),
            headers=client._headers(),
            json=payload,
            timeout=client.timeout_seconds,
        )
    except Exception as exc:
        message = redact_alpaca_message(str(exc))
        raise AlpacaPaperError(f"Alpaca paper submission request failed: {message}") from exc

    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code in {401, 403}:
        raise AlpacaPaperAuthError(f"Alpaca paper submission failed with HTTP {status_code}.")
    if status_code < 200 or status_code >= 300:
        raise AlpacaPaperError(f"Alpaca paper submission failed with HTTP {status_code}.")

    try:
        response_data = response.json()
    except ValueError as exc:
        raise AlpacaPaperError("Alpaca paper submission response was not valid JSON.") from exc
    if not isinstance(response_data, dict):
        raise AlpacaPaperError("Alpaca paper submission response JSON was not an object.")
    return sanitize_paper_submission_result(
        response_data,
        payload,
        human_approval_confirmed=confirm_human_approval,
    )
