from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any


CLOSING_LINE = "Simulated. No real trading. Not financial advice."
STARTING_CASH = 100000.0
MAX_NOTIONAL = 100000.0
PREVIEW_TTL_SECONDS = 900
ACCOUNT_RE = re.compile(r"^[a-z0-9-]{1,20}$")
SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")


def now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def data_dir() -> Path:
    return Path(os.environ.get("SIMBROKER_DATA_DIR", "~/.simbroker")).expanduser()


def account_dir(account: str) -> Path:
    return data_dir() / account


def assert_account_name(name: str) -> str:
    if not ACCOUNT_RE.fullmatch(name):
        raise ValueError("Account names must use lowercase letters, digits, or hyphens and be at most 20 characters.")
    return name


def jsonl_append(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def jsonl_read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def ensure_account(account: str = "default", max_order_usd: float | None = None) -> Path:
    name = assert_account_name(account)
    folder = account_dir(name)
    folder.mkdir(parents=True, exist_ok=True)
    config_path = folder / "account.json"
    if not config_path.exists():
        config = {
            "account": name,
            "starting_cash": STARTING_CASH,
            "max_order_usd": max_order_usd,
            "created_at": now_ts(),
        }
        config_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for filename in ("paper_portfolio.jsonl", "orders.jsonl"):
        path = folder / filename
        if not path.exists():
            path.write_text("", encoding="utf-8")
    return folder


def read_config(account: str) -> dict[str, Any]:
    folder = ensure_account(account)
    return json.loads((folder / "account.json").read_text(encoding="utf-8"))


def replay_state(account: str) -> dict[str, Any]:
    config = read_config(account)
    cash = float(config.get("starting_cash", STARTING_CASH))
    positions: dict[str, float] = {}
    for record in jsonl_read(account_dir(account) / "paper_portfolio.jsonl"):
        symbol = str(record["symbol"])
        notional = float(record["notional_usd"])
        side = str(record["side"]).lower()
        if side == "buy":
            cash -= notional
            positions[symbol] = positions.get(symbol, 0.0) + notional
        elif side == "sell":
            cash += notional
            positions[symbol] = max(0.0, positions.get(symbol, 0.0) - notional)
    return {
        "cash": round(cash, 2),
        "positions": {symbol: round(value, 2) for symbol, value in sorted(positions.items()) if value > 0},
        "max_order_usd": config.get("max_order_usd"),
    }


def response(fields: dict[str, Any], message: str) -> dict[str, Any]:
    text = message.rstrip()
    if text:
        text = f"{text}\n{CLOSING_LINE}"
    else:
        text = CLOSING_LINE
    return {**fields, "message": text}


def error_response(message: str) -> dict[str, Any]:
    return response({"ok": False, "error": message}, message)


def validate_order(symbol: str, side: str, notional_usd: Any, account: str) -> tuple[str, str, float, dict[str, Any]]:
    ensure_account(account)
    raw_symbol = str(symbol).strip()
    normalized_symbol = raw_symbol.upper()
    normalized_side = str(side).strip().lower()
    try:
        notional = round(float(notional_usd), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError("Notional must be numeric.") from exc
    if raw_symbol != normalized_symbol or not SYMBOL_RE.fullmatch(normalized_symbol):
        raise ValueError("Symbol must be non-empty uppercase text with at most 5 characters.")
    if normalized_side not in {"buy", "sell"}:
        raise ValueError("Side must be buy or sell.")
    if not (1.0 <= notional <= MAX_NOTIONAL):
        raise ValueError("Notional must be between 1 and 100000.")
    state = replay_state(account)
    max_order = state.get("max_order_usd")
    if max_order is not None and notional > float(max_order):
        raise ValueError("Notional exceeds this account's max_order_usd.")
    if normalized_side == "buy" and notional > float(state["cash"]):
        raise ValueError("Buy notional exceeds available simulated cash.")
    if normalized_side == "sell" and notional > float(state["positions"].get(normalized_symbol, 0.0)):
        raise ValueError("Sell requires an existing cost-basis position at least that large.")
    return normalized_symbol, normalized_side, notional, state


def create_account(name: str, max_order_usd: float | None = None) -> dict[str, Any]:
    account = assert_account_name(str(name))
    ensure_account(account, max_order_usd=max_order_usd)
    config = read_config(account)
    if max_order_usd is not None:
        config["max_order_usd"] = round(float(max_order_usd), 2)
        (account_dir(account) / "account.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return response({"ok": True, "account": account, "max_order_usd": config.get("max_order_usd")}, f"Account `{account}` is ready.")


def list_accounts() -> dict[str, Any]:
    ensure_account("default")
    names = sorted(path.name for path in data_dir().iterdir() if path.is_dir() and ACCOUNT_RE.fullmatch(path.name))
    return response({"ok": True, "accounts": names}, "Accounts listed.")


def get_account(account: str = "default") -> dict[str, Any]:
    name = assert_account_name(str(account))
    state = replay_state(name)
    return response({"ok": True, "account": name, **state}, f"Account `{name}` loaded.")


def preview_order(symbol: str, side: str, notional_usd: float, account: str = "default", reason: str | None = None) -> dict[str, Any]:
    name = assert_account_name(str(account))
    normalized_symbol, normalized_side, notional, state = validate_order(symbol, side, notional_usd, name)
    preview_id = f"prev_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    preview = {
        "event": "preview",
        "ts": now_ts(),
        "preview_id": preview_id,
        "account": name,
        "symbol": normalized_symbol,
        "side": normalized_side,
        "notional_usd": notional,
        "reason": reason,
        "cash_before": state["cash"],
        "simulated": True,
        "no_real_trading": True,
    }
    jsonl_append(account_dir(name) / "orders.jsonl", preview)
    return response({"ok": True, **preview}, f"Preview `{preview_id}` created.")


def find_preview(preview_id: str) -> tuple[str, dict[str, Any]] | None:
    ensure_account("default")
    for folder in sorted(path for path in data_dir().iterdir() if path.is_dir()):
        orders = jsonl_read(folder / "orders.jsonl")
        for record in orders:
            if record.get("preview_id") == preview_id and record.get("event") == "preview":
                return folder.name, record
    return None


def preview_used(account: str, preview_id: str) -> bool:
    for record in jsonl_read(account_dir(account) / "orders.jsonl"):
        if record.get("event") == "place_attempt" and record.get("preview_id") == preview_id:
            return True
    return False


def place_simulated_order(preview_id: str, user_approved: bool) -> dict[str, Any]:
    preview_ref = find_preview(str(preview_id))
    if preview_ref is None:
        return error_response("Preview is required before placement.")
    account, preview = preview_ref
    if preview_used(account, str(preview_id)):
        return error_response("Preview has already been used.")
    if user_approved is not True:
        jsonl_append(
            account_dir(account) / "orders.jsonl",
            {"event": "place_attempt", "ts": now_ts(), "preview_id": preview_id, "approved": False},
        )
        return error_response("Placement requires user_approved=true.")
    created_epoch = int(str(preview_id).split("_")[1])
    if int(time.time()) - created_epoch > PREVIEW_TTL_SECONDS:
        return error_response("Preview is no longer fresh.")
    symbol, side, notional, state = validate_order(
        preview["symbol"],
        preview["side"],
        preview["notional_usd"],
        account,
    )
    order_id = f"sim_{uuid.uuid4().hex[:12]}"
    fill = {
        "ts": now_ts(),
        "order_id": order_id,
        "preview_id": preview_id,
        "account": account,
        "symbol": symbol,
        "side": side,
        "notional_usd": notional,
        "reason": preview.get("reason"),
        "simulated": True,
        "no_real_trading": True,
    }
    jsonl_append(account_dir(account) / "paper_portfolio.jsonl", fill)
    jsonl_append(
        account_dir(account) / "orders.jsonl",
        {
            "event": "place_attempt",
            "ts": fill["ts"],
            "preview_id": preview_id,
            "order_id": order_id,
            "approved": True,
            "cash_before": state["cash"],
        },
    )
    after = replay_state(account)
    return response({"ok": True, **fill, "cash_after": after["cash"]}, f"Simulated order `{order_id}` recorded.")


def get_portfolio(account: str = "default") -> dict[str, Any]:
    name = assert_account_name(str(account))
    state = replay_state(name)
    fills = jsonl_read(account_dir(name) / "paper_portfolio.jsonl")
    return response({"ok": True, "account": name, **state, "fills": fills}, f"Portfolio for `{name}` loaded at cost basis.")


def reset_account(account: str = "default") -> dict[str, Any]:
    name = assert_account_name(str(account))
    folder = ensure_account(name)
    suffix = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    archived: list[str] = []
    for filename in ("paper_portfolio.jsonl", "orders.jsonl"):
        path = folder / filename
        if path.exists() and path.read_text(encoding="utf-8").strip():
            archive_path = folder / f"{filename}.{suffix}.bak"
            path.rename(archive_path)
            archived.append(archive_path.name)
        path.write_text("", encoding="utf-8")
    return response({"ok": True, "account": name, "archived": archived, **replay_state(name)}, f"Account `{name}` reset.")


TOOLS = {
    "create_account": create_account,
    "list_accounts": list_accounts,
    "get_account": get_account,
    "preview_order": preview_order,
    "place_simulated_order": place_simulated_order,
    "get_portfolio": get_portfolio,
    "reset_account": reset_account,
}

ACCOUNT_PROPERTY = {
    "type": "string",
    "description": "Account name (lowercase letters, digits, hyphens). Defaults to `default`.",
}

TOOL_SPECS: dict[str, dict[str, Any]] = {
    "create_account": {
        "description": "Create a local simulated paper account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Account name (lowercase letters, digits, hyphens)."},
                "max_order_usd": {"type": "number", "description": "Optional per-order simulated notional cap."},
            },
            "required": ["name"],
        },
    },
    "list_accounts": {
        "description": "List local simulated paper accounts.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    "get_account": {
        "description": "Show simulated cash and cost-basis positions for an account.",
        "inputSchema": {
            "type": "object",
            "properties": {"account": ACCOUNT_PROPERTY},
            "required": [],
        },
    },
    "preview_order": {
        "description": "Preview a simulated notional paper order before placement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Uppercase ticker symbol, at most 5 characters."},
                "side": {"type": "string", "enum": ["buy", "sell"], "description": "Order side."},
                "notional_usd": {"type": "number", "description": "Simulated notional between 1 and 100000."},
                "account": ACCOUNT_PROPERTY,
                "reason": {"type": "string", "description": "Optional note recorded with the preview."},
            },
            "required": ["symbol", "side", "notional_usd"],
        },
    },
    "place_simulated_order": {
        "description": "Record a simulated fill only after a fresh preview and explicit user approval.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "preview_id": {"type": "string", "description": "Preview ID returned by preview_order."},
                "user_approved": {"type": "boolean", "description": "Must be true; set only after the user explicitly approves."},
            },
            "required": ["preview_id", "user_approved"],
        },
    },
    "get_portfolio": {
        "description": "Show simulated fills and cost-basis positions.",
        "inputSchema": {
            "type": "object",
            "properties": {"account": ACCOUNT_PROPERTY},
            "required": [],
        },
    },
    "reset_account": {
        "description": "Archive and reset a local simulated paper account.",
        "inputSchema": {
            "type": "object",
            "properties": {"account": ACCOUNT_PROPERTY},
            "required": [],
        },
    },
}

PROTOCOL_VERSION = "2024-11-05"
SERVER_VERSION = "0.1.1"


def tool_list() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
        for name, spec in TOOL_SPECS.items()
    ]


def tool_call_result(payload: dict[str, Any]) -> dict[str, Any]:
    structured = {key: value for key, value in payload.items() if key != "message"}
    return {
        "content": [{"type": "text", "text": payload["message"]}],
        "structuredContent": structured,
        "isError": not structured.get("ok", True),
    }


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    method = request.get("method")
    if "id" not in request:
        return None
    request_id = request["id"]
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "SimBroker", "version": SERVER_VERSION},
        }
    elif method == "tools/list":
        result = {"tools": tool_list()}
    elif method == "tools/call":
        params = request.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in TOOLS:
            result = tool_call_result(error_response("Unknown tool."))
        else:
            try:
                result = tool_call_result(TOOLS[name](**arguments))
            except Exception as exc:
                result = tool_call_result(error_response(str(exc)))
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found."},
        }
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> None:
    ensure_account("default")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except Exception:
            continue
        if not isinstance(request, dict):
            continue
        response_payload = handle_request(request)
        if response_payload is None:
            continue
        sys.stdout.write(json.dumps(response_payload) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
