from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

SENSITIVE_NAMES = {
    "POLYBRIDGE_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
}

BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
ENV_ASSIGN_RE = re.compile(
    r"\b(POLYBRIDGE_API_KEY|ALPACA_API_KEY|ALPACA_SECRET_KEY|APCA_API_KEY_ID|APCA_API_SECRET_KEY)"
    r"\s*[:=]\s*['\"]?[^'\"\s,}]+",
    re.IGNORECASE,
)
AUTHORIZATION_RE = re.compile(r"\b(Authorization)\s*[:=]\s*['\"]?[^'\"\r\n,}]+", re.IGNORECASE)
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
PREFIXED_TOKEN_RE = re.compile(r"\b(?:sk|pk|alpaca|polybridge|apca)[_-]?[A-Za-z0-9_-]{16,}\b", re.IGNORECASE)
GENERIC_TOKEN_RE = re.compile(r"\b(?=[A-Za-z0-9._~+/-]{32,}\b)(?=.*[A-Z])(?=.*[a-z])(?=.*\d)[A-Za-z0-9._~+/-]{32,}\b")


def is_sensitive_key(key: str) -> bool:
    normalized = key.upper()
    lower = key.lower()
    if lower == "secrets_redacted":
        return False
    if normalized in SENSITIVE_NAMES:
        return True
    if lower == "authorization":
        return True
    if "raw_response_sha256" in lower:
        return False
    return any(marker in lower for marker in ("api_key", "secret", "bearer_token", "access_token", "refresh_token"))


def redact_string(value: str, key: str | None = None) -> str:
    if key and "sha256" in key.lower():
        return value
    if key and key.lower() in {"schema_version", "tier", "mode", "broker", "allowed_use"}:
        return value
    if key and key.lower().endswith("_path") and value.startswith(("outputs/", "external-output/")):
        return value
    text = AUTHORIZATION_RE.sub(lambda match: f"{match.group(1)}: {REDACTED}", value)
    text = BEARER_RE.sub(f"Bearer {REDACTED}", text)
    text = ENV_ASSIGN_RE.sub(lambda match: f"{match.group(1).upper()}={REDACTED}", text)
    text = JWT_RE.sub(REDACTED, text)
    text = PREFIXED_TOKEN_RE.sub(REDACTED, text)
    text = GENERIC_TOKEN_RE.sub(REDACTED, text)
    return text


def redact(value: Any, key: str | None = None) -> Any:
    if key and is_sensitive_key(key):
        return REDACTED
    if isinstance(value, dict):
        return {item_key: redact(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_string(value, key=key)
    return value
