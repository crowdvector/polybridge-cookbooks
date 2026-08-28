from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

COOKBOOK_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COOKBOOK_DIR))

import us_macro_news_to_forecast as cookbook  # noqa: E402
from tests.fixtures import domain_rejected_response, forecast_response  # noqa: E402


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: dict | None = None,
        *,
        headers: dict[str, str] | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.payload = payload if payload is not None else forecast_response()
        self.headers = headers or {}
        self.json_error = json_error

    def json(self) -> dict:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class FakeSession:
    def __init__(
        self, response: FakeResponse | None = None, error: Exception | None = None
    ) -> None:
        self.response = response or FakeResponse()
        self.error = error
        self.calls: list[dict] = []

    def post(
        self, endpoint: str, *, headers: dict, json: dict, timeout: tuple
    ) -> FakeResponse:
        self.calls.append(
            {"endpoint": endpoint, "headers": headers, "json": json, "timeout": timeout}
        )
        if self.error is not None:
            raise self.error
        return self.response


def invoke(
    argv: list[str],
    session: FakeSession,
    *,
    stdin: io.StringIO | None = None,
    interactive: bool | None = False,
    browser_open=lambda _url: None,
) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = cookbook.run(
        argv,
        session=session,
        stdout=stdout,
        stderr=stderr,
        stdin=stdin or io.StringIO(),
        browser_open=browser_open,
        interactive=interactive,
    )
    return code, stdout.getvalue(), stderr.getvalue()


class CliInputTests(unittest.TestCase):
    def test_every_golden_demo_posts_only_its_exact_example_id(self) -> None:
        examples = cookbook.load_examples()
        self.assertEqual(set(examples), cookbook.PUBLIC_EXAMPLE_IDS)
        self.assertEqual(len(examples), 3)
        with patch.dict(os.environ, {}, clear=True):
            for example_id in examples:
                with self.subTest(example_id=example_id):
                    metadata = examples[example_id]
                    response = forecast_response()
                    response["source"] = {
                        "kind": "example",
                        "source_url": metadata["canonical_url"],
                        "publisher": metadata["publisher"],
                        "title": metadata["title"],
                        "extracted_chars": 240,
                    }
                    session = FakeSession(FakeResponse(payload=response))
                    code, stdout, stderr = invoke(
                        ["--demo", example_id, "--json"], session
                    )
                    self.assertEqual(code, 0)
                    self.assertEqual(stderr, "")
                    self.assertEqual(len(session.calls), 1)
                    source = session.calls[0]["json"]["source"]
                    self.assertEqual(source, {"kind": "example", "id": example_id})
                    self.assertNotIn("text", source)
                    self.assertEqual(json.loads(stdout)["status"], "forecast")

    def test_unknown_demo_id_fails_locally_before_post(self) -> None:
        session = FakeSession()
        code, stdout, stderr = invoke(
            ["--demo", "not-a-reviewed-example", "--json"], session
        )
        self.assertEqual(code, 2)
        self.assertEqual(session.calls, [])
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["error"]["code"], "invalid_arguments")

    def test_demo_rejects_custom_text_metadata_before_post(self) -> None:
        session = FakeSession()
        code, _, stderr = invoke(
            ["--demo", "jobs-axios", "--title", "Not part of an example request"],
            session,
        )
        self.assertEqual(code, 2)
        self.assertEqual(session.calls, [])
        self.assertIn("apply only to text or file", stderr)

    def test_url_mode_uses_exact_public_contract(self) -> None:
        session = FakeSession()
        code, _, _ = invoke(
            ["--url", "https://example.com/story?campaign=test", "--json"],
            session,
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            session.calls[0]["json"],
            {
                "source": {
                    "kind": "url",
                    "url": "https://example.com/story?campaign=test",
                }
            },
        )

    def test_text_mode_preserves_optional_metadata(self) -> None:
        story = "A sufficiently detailed synthetic US macro story for the public client test."
        session = FakeSession()
        code, _, _ = invoke(
            [
                "--text",
                story,
                "--source-url",
                "https://example.com/story",
                "--publisher",
                "Example News",
                "--title",
                "Example headline",
                "--json",
            ],
            session,
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            session.calls[0]["json"]["source"],
            {
                "kind": "text",
                "text": story,
                "source_url": "https://example.com/story",
                "publisher": "Example News",
                "title": "Example headline",
            },
        )

    def test_file_mode_reads_utf8_and_does_not_send_local_path(self) -> None:
        story = "A sufficiently detailed UTF-8 macro story about wages and prices for testing."
        with tempfile.TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "story.txt"
            path.write_text(story, encoding="utf-8")
            session = FakeSession()
            code, _, _ = invoke(["--file", str(path), "--json"], session)
        self.assertEqual(code, 0)
        sent = session.calls[0]["json"]
        self.assertEqual(sent["source"]["kind"], "text")
        self.assertEqual(sent["source"]["text"], story)
        self.assertNotIn(str(path), json.dumps(sent))

    def test_conflicting_inputs_fail_before_post(self) -> None:
        session = FakeSession()
        code, stdout, stderr = invoke(
            [
                "--demo",
                "jobs-axios",
                "--text",
                "A competing story input",
                "--json",
            ],
            session,
        )
        self.assertEqual(code, 2)
        self.assertEqual(session.calls, [])
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout)["error"]["code"], "invalid_arguments")

    def test_missing_input_fails_before_post(self) -> None:
        session = FakeSession()
        code, _, stderr = invoke([], session)
        self.assertEqual(code, 2)
        self.assertEqual(session.calls, [])
        self.assertIn("one of the arguments", stderr)

    def test_url_mode_rejects_text_metadata(self) -> None:
        session = FakeSession()
        code, _, stderr = invoke(
            ["--url", "https://example.com/story", "--publisher", "Example"],
            session,
        )
        self.assertEqual(code, 2)
        self.assertEqual(session.calls, [])
        self.assertIn("apply only to text", stderr)


class HttpClientTests(unittest.TestCase):
    def test_anonymous_request_omits_authorization(self) -> None:
        session = FakeSession()
        with patch.dict(os.environ, {}, clear=True):
            code, _, _ = invoke(["--demo", "jobs-axios", "--json"], session)
        self.assertEqual(code, 0)
        self.assertNotIn("Authorization", session.calls[0]["headers"])

    def test_authenticated_request_uses_bearer_header_once(self) -> None:
        session = FakeSession()
        with patch.dict(
            os.environ, {"POLYBRIDGE_API_KEY": "pb_test_example_secret"}, clear=True
        ):
            code, _, _ = invoke(["--demo", "jobs-axios", "--json"], session)
        self.assertEqual(code, 0)
        self.assertEqual(
            session.calls[0]["headers"]["Authorization"],
            "Bearer pb_test_example_secret",
        )
        self.assertEqual(len(session.calls), 1)

    def test_invalid_credentials_never_retry_anonymously(self) -> None:
        for status in (401, 403):
            with self.subTest(status=status):
                session = FakeSession(FakeResponse(status))
                with patch.dict(
                    os.environ,
                    {"POLYBRIDGE_API_KEY": "pb_test_example_secret"},
                    clear=True,
                ):
                    code, stdout, stderr = invoke(["--demo", "jobs-axios"], session)
                self.assertEqual(code, 3)
                self.assertEqual(stdout, "")
                self.assertIn("not retried anonymously", stderr.lower())
                self.assertEqual(len(session.calls), 1)
                self.assertIn("Authorization", session.calls[0]["headers"])

    def test_anonymous_auth_error_explains_how_to_set_key(self) -> None:
        session = FakeSession(FakeResponse(401))
        with patch.dict(os.environ, {}, clear=True):
            code, _, stderr = invoke(["--demo", "jobs-axios"], session)
        self.assertEqual(code, 3)
        self.assertIn("Set POLYBRIDGE_API_KEY", stderr)

    def test_rate_limit_is_not_retried_and_honors_public_wait_hint(self) -> None:
        session = FakeSession(FakeResponse(429, headers={"Retry-After": "7"}))
        code, _, stderr = invoke(["--demo", "jobs-axios"], session)
        self.assertEqual(code, 4)
        self.assertEqual(len(session.calls), 1)
        self.assertIn("waiting 7 seconds", stderr)
        self.assertIn("No automatic retry", stderr)

    def test_timeout_is_not_retried(self) -> None:
        session = FakeSession(error=requests.exceptions.Timeout("synthetic timeout"))
        code, _, stderr = invoke(["--demo", "jobs-axios"], session)
        self.assertEqual(code, 6)
        self.assertEqual(len(session.calls), 1)
        self.assertIn("may still be running", stderr)
        self.assertIn("not retried", stderr)

    def test_connection_drop_is_not_retried(self) -> None:
        session = FakeSession(
            error=requests.exceptions.ConnectionError("synthetic disconnect")
        )
        code, _, stderr = invoke(["--demo", "jobs-axios"], session)
        self.assertEqual(code, 6)
        self.assertEqual(len(session.calls), 1)
        self.assertIn("outcome may be unknown", stderr)

    def test_model_unavailable_is_not_retried(self) -> None:
        session = FakeSession(FakeResponse(503))
        code, _, stderr = invoke(["--demo", "jobs-axios"], session)
        self.assertEqual(code, 6)
        self.assertEqual(len(session.calls), 1)
        self.assertIn("fixed snapshot", stderr)
        self.assertIn("no model fallback", stderr.lower())

    def test_model_timeout_is_not_retried(self) -> None:
        session = FakeSession(FakeResponse(504))
        code, _, stderr = invoke(["--demo", "jobs-axios"], session)
        self.assertEqual(code, 6)
        self.assertEqual(len(session.calls), 1)
        self.assertIn("did not finish in time", stderr)

    def test_url_extraction_error_suggests_text_mode(self) -> None:
        session = FakeSession(FakeResponse(422))
        code, _, stderr = invoke(["--url", "https://example.com/story"], session)
        self.assertEqual(code, 5)
        self.assertIn("--text or --file", stderr)

    def test_other_public_endpoint_errors_are_clean_and_not_retried(self) -> None:
        cases = {
            413: (5, "too large"),
            431: (5, "headers exceeded"),
            502: (6, "could not be verified"),
        }
        for status, (expected_code, fragment) in cases.items():
            with self.subTest(status=status):
                session = FakeSession(FakeResponse(status))
                code, stdout, stderr = invoke(["--demo", "jobs-axios"], session)
                self.assertEqual(code, expected_code)
                self.assertEqual(stdout, "")
                self.assertIn(fragment, stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertEqual(len(session.calls), 1)

    def test_malformed_json_is_a_clean_contract_error(self) -> None:
        session = FakeSession(
            FakeResponse(json_error=ValueError("synthetic malformed JSON"))
        )
        code, _, stderr = invoke(["--demo", "jobs-axios"], session)
        self.assertEqual(code, 7)
        self.assertIn("malformed JSON", stderr)
        self.assertNotIn("Traceback", stderr)

    def test_json_errors_are_machine_readable_and_secret_free(self) -> None:
        session = FakeSession(FakeResponse(401))
        secret = "pb_test_should_never_be_printed"
        with patch.dict(os.environ, {"POLYBRIDGE_API_KEY": secret}, clear=True):
            code, stdout, stderr = invoke(["--demo", "jobs-axios", "--json"], session)
        self.assertEqual(code, 3)
        self.assertEqual(stderr, "")
        parsed = json.loads(stdout)
        self.assertEqual(parsed["status"], "client_error")
        self.assertNotIn(secret, stdout)

    def test_client_timeout_is_longer_than_platform_numerical_timeout(self) -> None:
        self.assertGreater(cookbook.REQUEST_TIMEOUT_SECONDS[1], 190)


class JsonAndDomainTests(unittest.TestCase):
    def test_json_stdout_is_only_the_public_response(self) -> None:
        response = forecast_response("path_probability")
        session = FakeSession(FakeResponse(payload=response))
        code, stdout, stderr = invoke(["--demo", "inflation-ap", "--json"], session)
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(json.loads(stdout), response)
        self.assertNotIn("US MACRO NEWS TO FORECAST", stdout)

    def test_json_mode_does_not_write_default_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            temporary_output = Path(temporary_dir) / "outputs"
            with patch.object(cookbook, "DEFAULT_OUTPUT_DIR", temporary_output):
                code, _, _ = invoke(["--demo", "jobs-axios", "--json"], FakeSession())
            self.assertEqual(code, 0)
            self.assertFalse(temporary_output.exists())

    def test_json_mode_writes_artifact_only_when_output_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            output = Path(temporary_dir) / "explicit.json"
            code, stdout, stderr = invoke(
                ["--demo", "jobs-axios", "--json", "--output", str(output)],
                FakeSession(),
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(json.loads(stdout)["status"], "forecast")
            self.assertTrue(output.exists())
            self.assertEqual(json.loads(output.read_text())["fixture_id"], "jobs-axios")

    def test_domain_rejection_is_success_and_saves_artifact_in_terminal_mode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            artifact_path = Path(temporary_dir) / "rejected.json"
            session = FakeSession(FakeResponse(payload=domain_rejected_response()))
            code, stdout, stderr = invoke(
                ["--demo", "jobs-axios", "--output", str(artifact_path)],
                session,
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")
            self.assertIn("No forecast was run.", stdout)
            self.assertTrue(artifact_path.exists())


if __name__ == "__main__":
    unittest.main()
