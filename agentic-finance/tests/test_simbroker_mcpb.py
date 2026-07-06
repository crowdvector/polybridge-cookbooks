from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BASE_DIR = Path(__file__).resolve().parents[1]
SERVER_PATH = BASE_DIR / "simbroker-mcpb" / "server.py"
MANIFEST_PATH = BASE_DIR / "simbroker-mcpb" / "manifest.json"
CLOSING_LINE = "Simulated. No real trading. Not financial advice."
TOOL_NAMES = (
    "create_account",
    "list_accounts",
    "get_account",
    "preview_order",
    "place_simulated_order",
    "get_portfolio",
    "reset_account",
)


def load_server():
    spec = importlib.util.spec_from_file_location("simbroker_mcpb_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SimBrokerMcpbTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.patch_env = patch.dict(os.environ, {"SIMBROKER_DATA_DIR": self.temp.name}, clear=True)
        self.patch_env.start()
        self.server = load_server()

    def tearDown(self) -> None:
        self.patch_env.stop()
        self.temp.cleanup()

    def assert_closing(self, payload: dict) -> None:
        self.assertTrue(payload["message"].endswith(CLOSING_LINE))

    def test_default_account_exists(self) -> None:
        payload = self.server.list_accounts()

        self.assertIn("default", payload["accounts"])
        self.assert_closing(payload)

    def test_create_account_and_bad_account_name(self) -> None:
        payload = self.server.create_account("demo-1", max_order_usd=500)

        self.assertEqual(payload["account"], "demo-1")
        self.assertEqual(payload["max_order_usd"], 500.0)
        self.assert_closing(payload)
        with self.assertRaises(ValueError):
            self.server.create_account("Bad_Name")

    def test_preview_order_validates_symbol_side_and_notional(self) -> None:
        with self.assertRaises(ValueError):
            self.server.preview_order("spy", "buy", 100)
        with self.assertRaises(ValueError):
            self.server.preview_order("SPY", "hold", 100)
        with self.assertRaises(ValueError):
            self.server.preview_order("SPY", "buy", 0)

        payload = self.server.preview_order("SPY", "buy", 100)
        self.assertTrue(payload["preview_id"].startswith("prev_"))
        self.assert_closing(payload)

    def test_preview_required_and_user_approval_required_before_place(self) -> None:
        missing = self.server.place_simulated_order("prev_missing", True)
        self.assertFalse(missing["ok"])
        self.assert_closing(missing)

        preview = self.server.preview_order("SPY", "buy", 100)
        denied = self.server.place_simulated_order(preview["preview_id"], False)
        self.assertFalse(denied["ok"])
        self.assert_closing(denied)

    def test_reused_preview_refused(self) -> None:
        preview = self.server.preview_order("SPY", "buy", 100)
        first = self.server.place_simulated_order(preview["preview_id"], True)
        second = self.server.place_simulated_order(preview["preview_id"], True)

        self.assertTrue(first["ok"])
        self.assertFalse(second["ok"])
        self.assert_closing(first)
        self.assert_closing(second)

    def test_buy_reduces_cash_and_sell_requires_position(self) -> None:
        with self.assertRaises(ValueError):
            self.server.preview_order("SPY", "sell", 2000)
        with self.assertRaises(ValueError):
            self.server.preview_order("QQQ", "sell", 100)

    def test_buy_and_sell_flow(self) -> None:
        buy_preview = self.server.preview_order("SPY", "buy", 100)
        buy = self.server.place_simulated_order(buy_preview["preview_id"], True)
        account = self.server.get_account()

        self.assertTrue(buy["ok"])
        self.assertEqual(account["cash"], 98900.0)
        self.assertEqual(account["positions"]["SPY"], 1100.0)

        sell_preview = self.server.preview_order("SPY", "sell", 50)
        sell = self.server.place_simulated_order(sell_preview["preview_id"], True)
        after = self.server.get_account()

        self.assertTrue(sell["ok"])
        self.assertEqual(after["cash"], 98950.0)
        self.assertEqual(after["positions"]["SPY"], 1050.0)

    def test_per_account_limit_and_independent_accounts(self) -> None:
        self.server.create_account("small", max_order_usd=50)
        with self.assertRaises(ValueError):
            self.server.preview_order("SPY", "buy", 75, account="small")

        self.server.create_account("other")
        preview = self.server.preview_order("SPY", "buy", 100, account="other")
        self.server.place_simulated_order(preview["preview_id"], True)

        self.assertEqual(self.server.get_account("default")["cash"], 99000.0)
        self.assertEqual(self.server.get_account("other")["cash"], 98900.0)

    def test_reset_archives_and_resets(self) -> None:
        preview = self.server.preview_order("SPY", "buy", 100)
        self.server.place_simulated_order(preview["preview_id"], True)

        reset = self.server.reset_account()

        self.assertEqual(reset["cash"], 99000.0)
        self.assertEqual(reset["positions"]["SPY"], 1000.0)
        self.assertTrue(reset["archived"])
        self.assert_closing(reset)

    def test_every_tool_response_has_closing_line(self) -> None:
        responses = [
            self.server.list_accounts(),
            self.server.get_account(),
            self.server.get_portfolio(),
            self.server.reset_account(),
        ]
        for payload in responses:
            self.assert_closing(payload)

    def test_server_has_no_network_code(self) -> None:
        source = SERVER_PATH.read_text(encoding="utf-8").lower()
        banned = ("http", "requests", "urllib", "socket", "sub" + "process", "openai", "al" + "paca", "api" + ".")
        for term in banned:
            self.assertNotIn(term, source)

    def test_manifest_shape_for_claude_desktop(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertEqual(manifest["version"], "0.2.0")
        self.assertIn("author", manifest)
        self.assertIn("name", manifest["author"])
        self.assertIn("server", manifest)
        self.assertIn("mcp_config", manifest["server"])
        self.assertIn("command", manifest["server"]["mcp_config"])
        self.assertEqual(len(manifest["tools"]), 7)
        for tool in manifest["tools"]:
            self.assertIsInstance(tool, dict)
            self.assertIn("name", tool)
            self.assertIn("description", tool)
        self.assertEqual(tuple(tool["name"] for tool in manifest["tools"]), TOOL_NAMES)

    def test_initialize_returns_mcp_shape(self) -> None:
        reply = self.server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

        self.assertEqual(reply["id"], 1)
        result = reply["result"]
        self.assertEqual(result["protocolVersion"], "2024-11-05")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "SimBroker")
        self.assertEqual(result["serverInfo"]["version"], "0.2.0")

    def test_tools_list_returns_tool_objects_with_input_schema(self) -> None:
        reply = self.server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

        tools = reply["result"]["tools"]
        self.assertEqual(tuple(tool["name"] for tool in tools), TOOL_NAMES)
        for tool in tools:
            self.assertIsInstance(tool, dict)
            self.assertTrue(tool["description"])
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertIn("properties", schema)
            self.assertIn("required", schema)

    def test_notifications_produce_no_response(self) -> None:
        for method in ("notifications/initialized", "tools/list"):
            reply = self.server.handle_request({"jsonrpc": "2.0", "method": method})
            self.assertIsNone(reply)

    def test_tools_call_returns_mcp_content(self) -> None:
        reply = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_account", "arguments": {}},
            }
        )

        result = reply["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertTrue(result["content"][0]["text"].endswith(CLOSING_LINE))
        self.assertEqual(result["structuredContent"]["account"], "default")

    def test_tools_call_validation_refusal_is_mcp_error_content(self) -> None:
        reply = self.server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "place_simulated_order", "arguments": {"preview_id": "prev_missing", "user_approved": True}},
            }
        )

        result = reply["result"]
        self.assertTrue(result["isError"])
        self.assertIn("Call preview_order first", result["content"][0]["text"])
        self.assertTrue(result["content"][0]["text"].endswith(CLOSING_LINE))

    def test_unknown_method_returns_jsonrpc_error(self) -> None:
        reply = self.server.handle_request({"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}})

        self.assertEqual(reply["error"]["code"], -32601)
        self.assertNotIn("result", reply)


class SimBrokerVisibleTextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.patch_env = patch.dict(os.environ, {"SIMBROKER_DATA_DIR": self.temp.name}, clear=True)
        self.patch_env.start()
        self.server = load_server()

    def tearDown(self) -> None:
        self.patch_env.stop()
        self.temp.cleanup()

    def call_text(self, name: str, arguments: dict | None = None) -> str:
        reply = self.server.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}}
        )
        text = reply["result"]["content"][0]["text"]
        self.assertTrue(text.endswith(CLOSING_LINE))
        return text

    def buy_spy(self, notional: float = 1000) -> str:
        preview = self.server.preview_order("SPY", "buy", notional)
        return self.server.place_simulated_order(preview["preview_id"], True)["message"]

    def test_get_account_fresh_text(self) -> None:
        text = self.call_text("get_account")

        self.assertIn("SIMBROKER ACCOUNT", text)
        self.assertIn("Cash:      $99,000.00", text)
        self.assertIn("Positions: SPY $1,000.00 (1 fill)", text)

    def test_get_account_after_fill_text(self) -> None:
        self.buy_spy()
        text = self.call_text("get_account")

        self.assertIn("Cash:      $98,000.00", text)
        self.assertIn("Positions: SPY $2,000.00 (2 fills)", text)

    def test_create_account_text(self) -> None:
        text = self.call_text("create_account", {"name": "john", "max_order_usd": 5000})

        self.assertIn("SIMBROKER ACCOUNT CREATED  john", text)
        self.assertIn("Cash:  $99,000.00", text)
        self.assertIn("Limit: $5,000.00 per order", text)

    def test_list_accounts_text(self) -> None:
        self.call_text("create_account", {"name": "john", "max_order_usd": 5000})
        text = self.call_text("list_accounts")

        self.assertIn("SIMBROKER ACCOUNTS", text)
        self.assertIn("default", text)
        self.assertIn("cash", text)
        self.assertIn("deployed $1,000.00", text)
        self.assertIn("fills 1", text)
        self.assertIn("limit $5,000/order", text)
        lines = text.splitlines()
        self.assertLess(lines.index(next(l for l in lines if l.startswith("default"))),
                        lines.index(next(l for l in lines if l.startswith("john"))))

    def test_preview_order_text(self) -> None:
        text = self.call_text(
            "preview_order",
            {"symbol": "SPY", "side": "buy", "notional_usd": 1000, "reason": "labor-resilience thesis, 3 of 3 passed"},
        )

        self.assertIn("SIMULATED ORDER PREVIEW", text)
        self.assertIn("SYMBOL:   SPY", text)
        self.assertIn("SIDE:     BUY", text)
        self.assertIn("NOTIONAL: $1,000.00", text)
        self.assertIn("REASON:   labor-resilience thesis, 3 of 3 passed", text)
        self.assertIn("ACCOUNT:  default", text)
        self.assertIn("Show this to the user", text)

    def test_preview_order_text_omits_reason_when_missing(self) -> None:
        text = self.call_text("preview_order", {"symbol": "SPY", "side": "buy", "notional_usd": 1000})

        self.assertNotIn("REASON:", text)

    def test_place_simulated_order_text(self) -> None:
        preview = self.server.preview_order("SPY", "buy", 1000)
        text = self.call_text(
            "place_simulated_order", {"preview_id": preview["preview_id"], "user_approved": True}
        )

        self.assertIn("SIMULATED FILL", text)
        self.assertIn("SYMBOL:   SPY", text)
        self.assertIn("SIDE:     BUY", text)
        self.assertIn("NOTIONAL: $1,000.00", text)
        self.assertIn("CASH:", text)
        self.assertIn("$98,000.00 remaining", text)
        self.assertIn("Recorded:", text)
        self.assertIn("paper_portfolio.jsonl", text)

    def test_get_portfolio_fresh_text_shows_starter(self) -> None:
        text = self.call_text("get_portfolio")

        self.assertIn("SIMBROKER PORTFOLIO", text)
        self.assertIn("SPY", text)
        self.assertIn("BUY", text)
        self.assertIn("$1,000.00", text)
        self.assertIn("sim_starter", text)
        self.assertIn("Showing 1 of 1 fills", text)

    def test_get_portfolio_after_fill_text(self) -> None:
        self.buy_spy()
        text = self.call_text("get_portfolio")

        self.assertIn("SIMBROKER PORTFOLIO", text)
        self.assertIn("SPY", text)
        self.assertIn("BUY", text)
        self.assertIn("$1,000.00", text)
        self.assertIn("Showing 2 of 2 fills", text)

    def test_reset_account_text_mentions_starter_and_archives(self) -> None:
        self.buy_spy()
        text = self.call_text("reset_account")

        self.assertIn("Simulated account reset. Cash: $99,000.00.", text)
        self.assertIn("Starter position restored: SPY $1,000.00.", text)
        self.assertIn("Previous records archived as", text)
        self.assertIn("paper_portfolio.", text)

    def test_refusal_texts_are_explicit(self) -> None:
        no_preview = self.call_text("place_simulated_order", {"preview_id": "prev_missing", "user_approved": True})
        self.assertIn("Call preview_order first", no_preview)

        preview = self.server.preview_order("SPY", "buy", 1000)
        denied = self.call_text("place_simulated_order", {"preview_id": preview["preview_id"], "user_approved": False})
        self.assertIn("user_approved was not true", denied)

        self.buy_spy()
        insufficient = self.call_text("preview_order", {"symbol": "SPY", "side": "buy", "notional_usd": 100000.0})
        self.assertIn("Insufficient simulated cash", insufficient)

        self.call_text("create_account", {"name": "small", "max_order_usd": 50})
        capped = self.call_text("preview_order", {"symbol": "SPY", "side": "buy", "notional_usd": 75, "account": "small"})
        self.assertIn("per-order limit", capped)

        self.call_text("create_account", {"name": "empty"})
        no_position = self.call_text("preview_order", {"symbol": "QQQ", "side": "sell", "notional_usd": 100, "account": "empty"})
        self.assertIn("No QQQ position to sell", no_position)


class SimBrokerStarterPositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.patch_env = patch.dict(os.environ, {"SIMBROKER_DATA_DIR": self.temp.name}, clear=True)
        self.patch_env.start()
        self.server = load_server()

    def tearDown(self) -> None:
        self.patch_env.stop()
        self.temp.cleanup()

    def test_fresh_default_account_is_seeded(self) -> None:
        account = self.server.get_account()
        portfolio = self.server.get_portfolio()

        self.assertEqual(account["cash"], 99000.0)
        self.assertEqual(account["positions"]["SPY"], 1000.0)
        self.assertEqual(len(portfolio["fills"]), 1)
        starter = portfolio["fills"][0]
        self.assertEqual(starter["order_id"], "sim_starter")
        self.assertEqual(starter["symbol"], "SPY")
        self.assertEqual(starter["side"], "buy")
        self.assertEqual(starter["notional_usd"], 1000.0)
        self.assertEqual(starter["reason"], "starter position: labor-resilience thesis (see cookbook)")
        self.assertTrue(starter["simulated"])
        self.assertTrue(starter["no_real_trading"])
        self.assertTrue(starter["ts"])

    def test_create_account_is_seeded_and_limit_does_not_block_seed(self) -> None:
        self.server.create_account("tiny", max_order_usd=50)
        account = self.server.get_account("tiny")
        portfolio = self.server.get_portfolio("tiny")

        self.assertEqual(account["cash"], 99000.0)
        self.assertEqual(account["positions"]["SPY"], 1000.0)
        self.assertEqual(len(portfolio["fills"]), 1)
        self.assertEqual(portfolio["fills"][0]["order_id"], "sim_starter")

        listing = self.server.list_accounts()["message"]
        tiny_row = next(line for line in listing.splitlines() if line.startswith("tiny"))
        self.assertIn("deployed $1,000.00", tiny_row)
        self.assertIn("fills 1", tiny_row)

    def test_reset_restores_starter_position(self) -> None:
        preview = self.server.preview_order("SPY", "buy", 500)
        self.server.place_simulated_order(preview["preview_id"], True)

        reset = self.server.reset_account()
        portfolio = self.server.get_portfolio()

        self.assertEqual(reset["cash"], 99000.0)
        self.assertEqual(reset["positions"]["SPY"], 1000.0)
        self.assertTrue(reset["archived"])
        self.assertIn("Starter position restored: SPY $1,000.00.", reset["message"])
        self.assertIn("Previous records archived as", reset["message"])
        self.assertEqual(len(portfolio["fills"]), 1)
        self.assertEqual(portfolio["fills"][0]["order_id"], "sim_starter")

    def test_selling_starter_position_flow(self) -> None:
        preview = self.server.preview_order("SPY", "sell", 1000)
        fill = self.server.place_simulated_order(preview["preview_id"], True)
        account = self.server.get_account()

        self.assertTrue(fill["ok"])
        self.assertEqual(account["cash"], 100000.0)
        self.assertEqual(account["positions"], {})
        self.assertIn("Positions: none", account["message"])

    def test_overselling_starter_position_refuses(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self.server.preview_order("SPY", "sell", 2000)
        self.assertIn("No SPY position to sell", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
