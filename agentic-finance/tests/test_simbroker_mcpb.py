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
            self.server.preview_order("SPY", "sell", 100)

    def test_buy_and_sell_flow(self) -> None:
        buy_preview = self.server.preview_order("SPY", "buy", 100)
        buy = self.server.place_simulated_order(buy_preview["preview_id"], True)
        account = self.server.get_account()

        self.assertTrue(buy["ok"])
        self.assertEqual(account["cash"], 99900.0)
        self.assertEqual(account["positions"]["SPY"], 100.0)

        sell_preview = self.server.preview_order("SPY", "sell", 50)
        sell = self.server.place_simulated_order(sell_preview["preview_id"], True)
        after = self.server.get_account()

        self.assertTrue(sell["ok"])
        self.assertEqual(after["cash"], 99950.0)
        self.assertEqual(after["positions"]["SPY"], 50.0)

    def test_per_account_limit_and_independent_accounts(self) -> None:
        self.server.create_account("small", max_order_usd=50)
        with self.assertRaises(ValueError):
            self.server.preview_order("SPY", "buy", 75, account="small")

        self.server.create_account("other")
        preview = self.server.preview_order("SPY", "buy", 100, account="other")
        self.server.place_simulated_order(preview["preview_id"], True)

        self.assertEqual(self.server.get_account("default")["cash"], 100000.0)
        self.assertEqual(self.server.get_account("other")["cash"], 99900.0)

    def test_reset_archives_and_resets(self) -> None:
        preview = self.server.preview_order("SPY", "buy", 100)
        self.server.place_simulated_order(preview["preview_id"], True)

        reset = self.server.reset_account()

        self.assertEqual(reset["cash"], 100000.0)
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

        self.assertEqual(manifest["version"], "0.1.1")
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
        self.assertEqual(result["serverInfo"]["version"], "0.1.1")

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
        self.assertIn("Preview is required before placement.", result["content"][0]["text"])
        self.assertTrue(result["content"][0]["text"].endswith(CLOSING_LINE))

    def test_unknown_method_returns_jsonrpc_error(self) -> None:
        reply = self.server.handle_request({"jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {}})

        self.assertEqual(reply["error"]["code"], -32601)
        self.assertNotIn("result", reply)


if __name__ == "__main__":
    unittest.main()
