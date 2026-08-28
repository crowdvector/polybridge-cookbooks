from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

COOKBOOK_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COOKBOOK_DIR))

import us_macro_news_to_forecast as cookbook  # noqa: E402
from tests.fixtures import forecast_response  # noqa: E402
from tests.test_cli import FakeResponse, FakeSession, invoke  # noqa: E402


class XSafetyTests(unittest.TestCase):
    def test_interactive_yes_opens_exact_server_intent_only_after_confirmation(
        self,
    ) -> None:
        response = forecast_response()
        opened: list[str] = []
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "artifact.json"
            code, stdout, _ = invoke(
                ["--demo", "jobs-axios", "--output", str(output)],
                FakeSession(FakeResponse(payload=response)),
                stdin=io.StringIO("y\n"),
                interactive=True,
                browser_open=opened.append,
            )
        self.assertEqual(code, 0)
        self.assertEqual(opened, [response["x_draft"]["intent_url"]])
        self.assertIn("Open draft in X? [y/N]", stdout)
        self.assertIn("Nothing was posted automatically", stdout)

    def test_interactive_no_does_not_open(self) -> None:
        opened: list[str] = []
        with tempfile.TemporaryDirectory() as temporary_dir:
            code, _, _ = invoke(
                [
                    "--demo",
                    "jobs-axios",
                    "--output",
                    str(Path(temporary_dir) / "artifact.json"),
                ],
                FakeSession(),
                stdin=io.StringIO("n\n"),
                interactive=True,
                browser_open=opened.append,
            )
        self.assertEqual(code, 0)
        self.assertEqual(opened, [])

    def test_noninteractive_input_never_prompts_or_opens(self) -> None:
        opened: list[str] = []
        with tempfile.TemporaryDirectory() as temporary_dir:
            code, stdout, _ = invoke(
                [
                    "--demo",
                    "jobs-axios",
                    "--output",
                    str(Path(temporary_dir) / "artifact.json"),
                ],
                FakeSession(),
                stdin=io.StringIO("y\n"),
                interactive=False,
                browser_open=opened.append,
            )
        self.assertEqual(code, 0)
        self.assertEqual(opened, [])
        self.assertNotIn("Open draft in X?", stdout)

    def test_json_mode_never_prompts_or_opens_even_if_marked_interactive(self) -> None:
        opened: list[str] = []
        code, stdout, stderr = invoke(
            ["--demo", "jobs-axios", "--json"],
            FakeSession(),
            stdin=io.StringIO("y\n"),
            interactive=True,
            browser_open=opened.append,
        )
        self.assertEqual(code, 0)
        self.assertEqual(opened, [])
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["status"], "forecast")

    def test_exact_server_x_text_length_intent_and_source_url_render(self) -> None:
        response = forecast_response()
        rendered = cookbook.render_terminal(response)
        self.assertIn(response["x_draft"]["text"], rendered)
        self.assertIn(str(response["x_draft"]["weighted_length"]), rendered)
        self.assertIn(response["x_draft"]["intent_url"], rendered)
        self.assertEqual(
            response["source"]["source_url"],
            "https://example.com/synthetic-story",
        )


class ArtifactTests(unittest.TestCase):
    def test_artifact_is_public_safe_and_does_not_duplicate_source_text(self) -> None:
        source_story = (
            "A long directly supplied story body that must be represented only by a digest "
            "inside the public-safe artifact."
        )
        response = forecast_response()
        artifact = cookbook.build_artifact(
            response,
            context={
                "input_mode": "file",
                "fixture_id": None,
                "source_text": source_story,
            },
            generated_at=datetime(2000, 1, 3, tzinfo=timezone.utc),
        )
        serialized = json.dumps(artifact)
        self.assertNotIn(source_story, serialized)
        self.assertNotIn("Authorization", serialized)
        self.assertNotIn("POLYBRIDGE_API_KEY", serialized)
        self.assertNotIn("cookies", serialized.lower())
        self.assertEqual(
            artifact["source_sha256"],
            __import__("hashlib").sha256(source_story.encode()).hexdigest(),
        )
        self.assertEqual(artifact["platform_response"], response)

    def test_saved_artifact_is_valid_json_and_does_not_include_output_path(
        self,
    ) -> None:
        response = forecast_response()
        artifact = cookbook.build_artifact(
            response,
            context={
                "input_mode": "demo",
                "fixture_id": "jobs-axios",
                "source_text": "story",
            },
            generated_at=datetime(2000, 1, 3, tzinfo=timezone.utc),
        )
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "nested" / "artifact.json"
            saved = cookbook.save_artifact(
                artifact,
                response=response,
                output_path=output,
                generated_at=datetime(2000, 1, 3, tzinfo=timezone.utc),
            )
            loaded = json.loads(saved.read_text(encoding="utf-8"))
        self.assertEqual(loaded, artifact)
        self.assertNotIn(str(output), json.dumps(loaded))

    def test_api_key_used_for_request_is_never_in_terminal_or_artifact(self) -> None:
        secret = "pb_test_artifact_redaction_secret"
        response = forecast_response()
        session = FakeSession(FakeResponse(payload=response))
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "artifact.json"
            with patch.dict(os.environ, {"POLYBRIDGE_API_KEY": secret}, clear=True):
                code, stdout, stderr = invoke(
                    ["--demo", "jobs-axios", "--output", str(output)],
                    session,
                )
            serialized = output.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertNotIn(secret, stdout)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("Authorization", serialized)


class StaticSecurityTests(unittest.TestCase):
    def test_runtime_has_no_private_model_or_provider_dependencies(self) -> None:
        source = (COOKBOOK_DIR / "us_macro_news_to_forecast.py").read_text(
            encoding="utf-8"
        )
        requirements = (COOKBOOK_DIR / "requirements.txt").read_text(encoding="utf-8")
        forbidden = (
            "google" + ".auth",
            "google" + ".cloud",
            "gen" + "ai",
            "service" + "_account",
            "api/query",
            "us-macro-v51-final" + "-staging",
            "tweep" + "y",
            "api." + "x.com",
        )
        for term in forbidden:
            with self.subTest(term=term):
                self.assertNotIn(term.casefold(), (source + requirements).casefold())

    def test_committed_cookbook_has_no_obvious_local_absolute_paths(self) -> None:
        local_patterns = (
            re.compile("/" + "Users" + "/"),
            re.compile("/" + "home" + "/"),
            re.compile(r"[A-Za-z]:" + r"\\" + r"\\"),
        )
        bad: list[str] = []
        for path in COOKBOOK_DIR.rglob("*"):
            if not path.is_file() or {
                "__pycache__",
                ".ruff_cache",
                ".pytest_cache",
            } & set(path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(pattern.search(text) for pattern in local_patterns):
                bad.append(str(path.relative_to(COOKBOOK_DIR)))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
