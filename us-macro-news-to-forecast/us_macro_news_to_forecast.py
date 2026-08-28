#!/usr/bin/env python3
"""Public client for the PolyBridge US Macro News to Forecast demo endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import webbrowser
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

import requests

CLIENT_VERSION = "1.3.0"
ARTIFACT_SCHEMA_VERSION = "polybridge.us-macro-news-demo.client-artifact.v1"
PLATFORM_SCHEMA_VERSION = "polybridge.us-macro-news-demo.v1"
EXAMPLE_SCHEMA_VERSION = "polybridge.us-macro-news-demo.examples.v3"
API_ENDPOINT = "https://api.polybridge.ai/v1/demos/us-macro-news-to-forecast"
REQUEST_TIMEOUT_SECONDS = (10, 360)
MAX_SOURCE_TEXT_CHARS = 20_000
MAX_SOURCE_TEXT_BYTES = 64_000
MAX_SOURCE_URL_CHARS = 2_048

BASE_DIR = Path(__file__).resolve().parent
EXAMPLES_PATH = BASE_DIR / "golden_examples.json"
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs"

PUBLIC_EXAMPLE_IDS = frozenset(
    {"inflation-ap", "jobs-axios", "treasury-markets-guardian"}
)
EXAMPLE_FIELDS = frozenset(
    {
        "id",
        "label",
        "publisher",
        "title",
        "publication_date",
        "canonical_url",
        "relationship",
        "relationship_note",
        "selected_question",
        "result",
        "result_type",
        "unit",
        "x_draft",
    }
)

RESULT_FAMILIES = frozenset(
    {
        "terminal",
        "threshold_probability",
        "path_probability",
        "joint_probability",
        "conditional_distribution",
        "extremum",
        "window_aggregate",
    }
)

TARGET_LABELS = {
    "headline_cpi_yoy": "US headline CPI year-over-year",
    "core_cpi_yoy": "US core CPI year-over-year",
    "energy_cpi_yoy": "US energy CPI year-over-year",
    "unemployment_rate": "US unemployment rate",
    "payroll_growth": "US nonfarm payroll growth",
    "job_openings": "US job openings",
    "labor_force_participation": "US labour-force participation",
    "nominal_wage_growth": "US nominal average-hourly-earnings growth",
    "employment_to_population": "US employment-to-population ratio",
    "housing_starts": "US housing starts",
    "real_gdp_growth": "US real GDP growth",
    "retail_sales_growth": "US retail-sales growth",
    "industrial_production_growth": "US industrial-production growth",
    "financial_conditions": "US financial conditions",
    "policy_stance": "US monetary-policy rate level",
}

SCORE_LABELS = (
    ("source_grounding", "Source grounding"),
    ("transmission_strength", "Transmission"),
    ("model_fit", "Model fit"),
    ("horizon_fit", "Horizon fit"),
    ("resolution_quality", "Resolution"),
    ("quantitative_interest", "Quantitative interest"),
    ("public_clarity", "Public clarity"),
    ("caveat_burden", "Caveat burden"),
)

HEAVY_RULE = "═" * 52
LIGHT_RULE = "─" * 52


class CookbookError(RuntimeError):
    """A public-safe CLI error with a stable code and exit status."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        exit_code: int,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.http_status = http_status

    def as_json(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.http_status is not None:
            error["http_status"] = self.http_status
        return {"status": "client_error", "error": error}


class ContractError(CookbookError):
    def __init__(self, message: str) -> None:
        super().__init__("unexpected_response", message, exit_code=7)


class RaisingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CookbookError("invalid_arguments", message, exit_code=2)


def load_examples(path: Path = EXAMPLES_PATH) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CookbookError(
            "examples_unavailable",
            "The bundled golden examples could not be loaded.",
            exit_code=5,
        ) from exc
    if payload.get("schema_version") != EXAMPLE_SCHEMA_VERSION:
        raise CookbookError(
            "examples_invalid",
            "The bundled golden-example schema is not supported by this client.",
            exit_code=5,
        )
    examples = payload.get("examples")
    if not isinstance(examples, list) or not examples:
        raise CookbookError(
            "examples_invalid", "No golden examples were found.", exit_code=5
        )
    by_id: dict[str, dict[str, Any]] = {}
    for index, example in enumerate(examples):
        if not isinstance(example, dict) or set(example) != EXAMPLE_FIELDS:
            raise CookbookError(
                "examples_invalid",
                f"Golden example {index + 1} does not match the public fixture schema.",
                exit_code=5,
            )
        example_id = example.get("id")
        if (
            not isinstance(example_id, str)
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", example_id) is None
            or example_id in by_id
        ):
            raise CookbookError(
                "examples_invalid",
                "Golden example IDs must be valid and unique.",
                exit_code=5,
            )
        if any(
            not isinstance(example[field], str) or not example[field].strip()
            for field in EXAMPLE_FIELDS - {"id"}
        ):
            raise CookbookError(
                "examples_invalid",
                f"Golden example {index + 1} has incomplete public metadata.",
                exit_code=5,
            )
        try:
            datetime.strptime(example["publication_date"], "%Y-%m-%d")
        except ValueError as exc:
            raise CookbookError(
                "examples_invalid",
                f"Golden example {index + 1} has an invalid publication date.",
                exit_code=5,
            ) from exc
        if not example["canonical_url"].startswith("https://"):
            raise CookbookError(
                "examples_invalid",
                f"Golden example {index + 1} must use a canonical HTTPS URL.",
                exit_code=5,
            )
        if example["relationship"] not in {"direct", "related"}:
            raise CookbookError(
                "examples_invalid",
                f"Golden example {index + 1} has an unsupported relationship.",
                exit_code=5,
            )
        by_id[example_id] = example
    if frozenset(by_id) != PUBLIC_EXAMPLE_IDS:
        raise CookbookError(
            "examples_invalid",
            "The public example allowlist does not match this client.",
            exit_code=5,
        )
    return by_id


def build_parser(
    examples: dict[str, dict[str, Any]] | None = None,
) -> argparse.ArgumentParser:
    examples = examples or load_examples()
    parser = RaisingArgumentParser(
        description=(
            "Turn one US macro news article into three supported questions and one "
            "quantitative forecast."
        ),
        epilog=(
            "The request is sent once and is never retried automatically. Set "
            "POLYBRIDGE_API_KEY for authenticated access."
        ),
    )
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument(
        "--demo", choices=sorted(examples), help="run a built-in article example"
    )
    inputs.add_argument("--url", help="public HTTPS article URL")
    inputs.add_argument("--text", help="story text supplied directly")
    inputs.add_argument(
        "--file", type=Path, help="UTF-8 text file containing the story"
    )
    parser.add_argument("--source-url", help="optional public HTTPS attribution URL")
    parser.add_argument("--publisher", help="optional publisher name for text input")
    parser.add_argument("--title", help="optional story title for text input")
    parser.add_argument(
        "--json",
        action="store_true",
        help="write only the public JSON response to stdout; never prompt or open a browser",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="save the public-safe audit artifact at this path",
    )
    return parser


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip()
    return cleaned or None


def _validate_https_url(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned.startswith("https://") or len(cleaned) > MAX_SOURCE_URL_CHARS:
        raise CookbookError(
            "invalid_source",
            f"{label} must be a public HTTPS URL no longer than {MAX_SOURCE_URL_CHARS:,} characters.",
            exit_code=2,
        )
    return cleaned


def _validate_story_text(value: str) -> str:
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        raise CookbookError(
            "invalid_source", "Story text must not be blank.", exit_code=2
        )
    if (
        len(cleaned) > MAX_SOURCE_TEXT_CHARS
        or len(cleaned.encode("utf-8")) > MAX_SOURCE_TEXT_BYTES
    ):
        raise CookbookError(
            "invalid_source",
            f"Story text must be {MAX_SOURCE_TEXT_CHARS:,} characters or fewer.",
            exit_code=2,
        )
    return cleaned


def build_request(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata_supplied = any((args.source_url, args.publisher, args.title))
    if args.demo:
        if metadata_supplied:
            raise CookbookError(
                "invalid_arguments",
                "--source-url, --publisher, and --title apply only to text or file input.",
                exit_code=2,
            )
        return {"source": {"kind": "example", "id": args.demo}}, {
            "input_mode": "demo",
            "fixture_id": args.demo,
            "source_text": None,
        }

    if args.url:
        if metadata_supplied:
            raise CookbookError(
                "invalid_arguments",
                "--source-url, --publisher, and --title apply only to text or file input.",
                exit_code=2,
            )
        url = _validate_https_url(args.url, "--url")
        return {"source": {"kind": "url", "url": url}}, {
            "input_mode": "url",
            "fixture_id": None,
            "source_text": None,
        }

    input_mode = "text"
    if args.file:
        input_mode = "file"
        try:
            story_text = args.file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise CookbookError(
                "file_unavailable",
                "The story file could not be read as UTF-8 text.",
                exit_code=2,
            ) from exc
    else:
        story_text = args.text

    story_text = _validate_story_text(story_text)
    source_url = args.source_url
    publisher = args.publisher
    title = args.title
    source: dict[str, Any] = {"kind": "text", "text": story_text}
    if source_url:
        source["source_url"] = _validate_https_url(source_url, "--source-url")
    publisher = _clean_optional(publisher)
    title = _clean_optional(title)
    if publisher:
        source["publisher"] = publisher
    if title:
        source["title"] = title
    return {"source": source}, {
        "input_mode": input_mode,
        "fixture_id": args.demo,
        "source_text": story_text,
    }


class PolyBridgeClient:
    """One-shot public endpoint client. POST outcomes are deliberately never retried."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        session: requests.Session | Any | None = None,
        timeout: tuple[int, int] = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = _clean_optional(api_key)
        self.session = session or requests.Session()
        self.timeout = timeout

    def forecast(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"PolyBridge-Cookbook-US-Macro-News/{CLIENT_VERSION}",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = self.session.post(
                API_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise CookbookError(
                "request_timeout",
                "The request timed out. The fixed-snapshot calculation may still be running; "
                "it was not retried. Rerun explicitly if you want to try again.",
                exit_code=6,
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise CookbookError(
                "endpoint_unavailable",
                "The endpoint could not be reached. The POST was not retried because its "
                "server-side outcome may be unknown.",
                exit_code=6,
            ) from exc

        if response.status_code != 200:
            raise _http_error(
                response.status_code,
                api_key_present=self.api_key is not None,
                retry_after=getattr(response, "headers", {}).get("Retry-After"),
            )
        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ContractError("The endpoint returned malformed JSON.") from exc
        validate_response(body)
        return body


def _http_error(
    status_code: int,
    *,
    api_key_present: bool,
    retry_after: str | None,
) -> CookbookError:
    if status_code == 401:
        if api_key_present:
            message = (
                "The configured POLYBRIDGE_API_KEY was rejected. It was not retried "
                "anonymously; set a valid key and rerun."
            )
        else:
            message = (
                "Anonymous demo access is not enabled for this deployment. Set "
                "POLYBRIDGE_API_KEY and rerun."
            )
        return CookbookError(
            "authentication_required", message, exit_code=3, http_status=401
        )
    if status_code == 403:
        return CookbookError(
            "authentication_forbidden",
            "The configured PolyBridge API key is not authorized for this endpoint. "
            "It was not retried anonymously.",
            exit_code=3,
            http_status=403,
        )
    if status_code == 429:
        wait = ""
        if retry_after and retry_after.isascii() and retry_after.isdecimal():
            wait = f" The server suggested waiting {retry_after} seconds."
        return CookbookError(
            "capacity_limited",
            "The demo rate, daily, or concurrent-request limit was reached."
            + wait
            + " No automatic retry was attempted.",
            exit_code=4,
            http_status=429,
        )
    messages = {
        413: (
            "request_too_large",
            "The story request is too large for the public demo.",
        ),
        422: (
            "source_rejected",
            (
                "The source could not be validated or extracted. For URL failures, paste the "
                "relevant story text with --text or --file."
            ),
        ),
        431: ("headers_too_large", "The request headers exceeded the public limit."),
        502: (
            "result_unverified",
            (
                "The story analysis or fixed-snapshot result could not be verified. "
                "No automatic retry was attempted."
            ),
        ),
        503: (
            "model_unavailable",
            (
                "Story analysis or the US Macro v51 fixed snapshot is temporarily unavailable. "
                "There is no model fallback and no automatic retry."
            ),
        ),
        504: (
            "model_timeout",
            (
                "US Macro v51 did not finish in time. The calculation was not retried; rerun "
                "explicitly if you want to try again."
            ),
        ),
    }
    code, message = messages.get(
        status_code,
        (
            "endpoint_error",
            f"The endpoint returned HTTP {status_code}. No automatic retry was attempted.",
        ),
    )
    exit_code = 6 if status_code >= 500 else 5
    return CookbookError(code, message, exit_code=exit_code, http_status=status_code)


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"Malformed response: {path} must be an object.")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"Malformed response: {path} must be an array.")
    return value


def _keys(
    value: dict[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    path: str,
) -> None:
    optional = optional or set()
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise ContractError(
            f"Malformed response: {path} is missing {', '.join(sorted(missing))}."
        )
    if unknown:
        raise ContractError(
            f"Malformed response: {path} contains unknown fields: {', '.join(sorted(unknown))}."
        )


def _string(value: Any, path: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not value:
        raise ContractError(f"Malformed response: {path} must be a non-empty string.")
    return value


def _number(
    value: Any,
    path: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    nullable: bool = False,
) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"Malformed response: {path} must be numeric.")
    number = float(value)
    if not math.isfinite(number):
        raise ContractError(f"Malformed response: {path} must be finite.")
    if minimum is not None and number < minimum:
        raise ContractError(f"Malformed response: {path} is below its allowed bound.")
    if maximum is not None and number > maximum:
        raise ContractError(f"Malformed response: {path} exceeds its allowed bound.")
    return number


def _integer(
    value: Any,
    path: str,
    *,
    minimum: int | None = None,
    nullable: bool = False,
) -> int | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"Malformed response: {path} must be an integer.")
    if minimum is not None and value < minimum:
        raise ContractError(f"Malformed response: {path} is below its allowed bound.")
    return value


def _string_list(
    value: Any, path: str, *, minimum: int = 0, maximum: int | None = None
) -> list[str]:
    items = _list(value, path)
    if len(items) < minimum or (maximum is not None and len(items) > maximum):
        raise ContractError(f"Malformed response: {path} has an invalid item count.")
    for index, item in enumerate(items):
        _string(item, f"{path}[{index}]")
    return items


def _timestamp(value: Any, path: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    text = _string(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ContractError(
            f"Malformed response: {path} must be an ISO-8601 timestamp."
        ) from None
    if parsed.utcoffset() is None:
        raise ContractError(f"Malformed response: {path} must include a UTC offset.")


def validate_response(payload: Any) -> dict[str, Any]:
    body = _object(payload, "response")
    if body.get("schema_version") != PLATFORM_SCHEMA_VERSION:
        raise ContractError(
            "Unsupported response schema. Expected " + PLATFORM_SCHEMA_VERSION + "."
        )
    status = body.get("status")
    if status == "forecast":
        _validate_forecast(body)
    elif status == "domain_rejected":
        _validate_domain_rejected(body)
    else:
        raise ContractError(f"Unsupported response status discriminator: {status!r}.")
    return body


def _validate_common(body: dict[str, Any]) -> None:
    _string(body["request_id"], "request_id")
    _validate_source(body["source"])
    _validate_analysis(body["analysis"])
    caveats = _string_list(body["caveats"], "caveats")
    if any(len(item) > 1_000 for item in caveats):
        raise ContractError("Malformed response: a caveat exceeds the public limit.")


def _validate_source(value: Any) -> None:
    source = _object(value, "source")
    _keys(
        source,
        required={"kind", "source_url", "publisher", "title", "extracted_chars"},
        path="source",
    )
    if source["kind"] not in {"url", "text", "example"}:
        raise ContractError("Malformed response: source.kind is unsupported.")
    for field in ("source_url", "publisher", "title"):
        _string(source[field], f"source.{field}", nullable=True)
    _integer(source["extracted_chars"], "source.extracted_chars", minimum=1)


def _validate_analysis(value: Any) -> None:
    analysis = _object(value, "analysis")
    _keys(
        analysis,
        required={"news_summary", "key_facts", "macro_signal", "transmission_channel"},
        path="analysis",
    )
    _string(analysis["news_summary"], "analysis.news_summary")
    _string_list(analysis["key_facts"], "analysis.key_facts", maximum=5)
    _string(analysis["macro_signal"], "analysis.macro_signal", nullable=True)
    _string(
        analysis["transmission_channel"],
        "analysis.transmission_channel",
        nullable=True,
    )


def _validate_candidates(value: Any, *, forecast: bool) -> list[dict[str, Any]]:
    candidates = _list(value, "candidates")
    if (forecast and len(candidates) != 3) or (not forecast and len(candidates) > 3):
        raise ContractError(
            "Malformed response: candidate count violates the public contract."
        )
    output = []
    for index, raw in enumerate(candidates):
        path = f"candidates[{index}]"
        item = _object(raw, path)
        _keys(
            item,
            required={
                "id",
                "question",
                "target_nodes",
                "request_family",
                "horizon",
                "score",
                "valid",
                "reason",
                "reason_codes",
            },
            path=path,
        )
        _string(item["id"], f"{path}.id")
        _string(item["question"], f"{path}.question")
        _string_list(item["target_nodes"], f"{path}.target_nodes", minimum=1, maximum=3)
        if item["request_family"] not in RESULT_FAMILIES:
            raise ContractError(
                f"Malformed response: {path}.request_family is unsupported."
            )
        _string(item["horizon"], f"{path}.horizon")
        _validate_score(item["score"], path=f"{path}.score")
        if not isinstance(item["valid"], bool):
            raise ContractError(f"Malformed response: {path}.valid must be boolean.")
        _string(item["reason"], f"{path}.reason")
        _string_list(item["reason_codes"], f"{path}.reason_codes")
        output.append(item)
    if forecast and [item["id"] for item in output] != [
        "candidate_1",
        "candidate_2",
        "candidate_3",
    ]:
        raise ContractError(
            "Malformed response: forecast candidate IDs are out of contract order."
        )
    return output


def _validate_score(value: Any, *, path: str) -> None:
    score = _object(value, path)
    component_fields = {key for key, _ in SCORE_LABELS}
    _keys(score, required=component_fields | {"total"}, path=path)
    for field in component_fields:
        component = _integer(score[field], f"{path}.{field}", minimum=0)
        if component is not None and component > 5:
            raise ContractError(f"Malformed response: {path}.{field} exceeds 5.")
    _number(score["total"], f"{path}.total", minimum=0, maximum=100)


def _validate_domain_rejected(body: dict[str, Any]) -> None:
    _keys(
        body,
        required={
            "schema_version",
            "status",
            "request_id",
            "source",
            "analysis",
            "candidates",
            "reason",
            "message",
            "caveats",
        },
        path="response",
    )
    _validate_common(body)
    _validate_candidates(body["candidates"], forecast=False)
    _string(body["reason"], "reason")
    expected = (
        "This story does not have a strong supported US macro forecasting angle for this "
        "fixed model snapshot."
    )
    if body["message"] != expected:
        raise ContractError(
            "Malformed response: domain-rejection message changed unexpectedly."
        )


def _validate_forecast(body: dict[str, Any]) -> None:
    _keys(
        body,
        required={
            "schema_version",
            "status",
            "request_id",
            "source",
            "analysis",
            "candidates",
            "selection",
            "compiled_request",
            "model",
            "result",
            "public_wording",
            "x_draft",
            "caveats",
        },
        optional={"forecast_relationship", "relationship_note"},
        path="response",
    )
    _validate_common(body)
    candidates = _validate_candidates(body["candidates"], forecast=True)
    selection = _validate_selection(body["selection"])
    selected = next(
        (item for item in candidates if item["id"] == selection["candidate_id"]), None
    )
    if (
        selected is None
        or not selected["valid"]
        or selected["question"] != selection["question"]
    ):
        raise ContractError(
            "Malformed response: selected candidate receipt is inconsistent."
        )
    compiled = _validate_compiled_request(body["compiled_request"])
    _validate_model(body["model"])
    result = _validate_result(body["result"])
    if (
        compiled["kind"] != result["kind"]
        or compiled["kind"] != selected["request_family"]
    ):
        raise ContractError(
            "Malformed response: result and compiled request families differ."
        )
    _string(body["public_wording"], "public_wording")
    _validate_x_draft(body["x_draft"])
    relationship = body.get("forecast_relationship")
    relationship_note = body.get("relationship_note")
    if relationship is None and relationship_note is not None:
        raise ContractError(
            "Malformed response: relationship_note requires forecast_relationship."
        )
    if relationship is not None:
        if relationship not in {"direct", "related"}:
            raise ContractError(
                "Malformed response: forecast_relationship is unsupported."
            )
        _string(relationship_note, "relationship_note")
        expected_note = {
            "direct": "The story directly concerns the forecast quantity.",
            "related": (
                "The story helped choose the question. It did not update the model."
            ),
        }[relationship]
        if relationship_note != expected_note:
            raise ContractError(
                "Malformed response: relationship_note is inconsistent with the forecast relationship."
            )


def _validate_selection(value: Any) -> dict[str, Any]:
    selection = _object(value, "selection")
    _keys(
        selection,
        required={"candidate_id", "question", "why_selected", "score"},
        path="selection",
    )
    for field in ("candidate_id", "question", "why_selected"):
        _string(selection[field], f"selection.{field}")
    _number(selection["score"], "selection.score", minimum=0, maximum=100)
    return selection


def _validate_compiled_request(value: Any) -> dict[str, Any]:
    compiled = _object(value, "compiled_request")
    _keys(
        compiled,
        required={
            "kind",
            "target_nodes",
            "period",
            "window_start",
            "window_end",
            "event_definition",
            "model_execution_count",
        },
        path="compiled_request",
    )
    if compiled["kind"] not in RESULT_FAMILIES:
        raise ContractError("Malformed response: compiled_request.kind is unsupported.")
    _string_list(
        compiled["target_nodes"], "compiled_request.target_nodes", minimum=1, maximum=3
    )
    for field in ("period", "window_start", "window_end", "event_definition"):
        _string(compiled[field], f"compiled_request.{field}", nullable=True)
    if compiled["model_execution_count"] != 1:
        raise ContractError(
            "Malformed response: model_execution_count must be exactly one."
        )
    return compiled


def _validate_model(value: Any) -> None:
    model = _object(value, "model")
    required = {
        "name",
        "model_id",
        "model_mode",
        "public_label",
        "release",
        "as_of",
        "fitted_through",
        "package_hash",
        "snapshot_hash",
        "spec_hash",
        "request_hash",
        "evidence_health",
        "evidence_snapshot_bound",
        "forward_source_count",
        "market_channel_count",
        "evidence_channel_health",
        "research_status",
        "cached",
        "settlement_date",
    }
    _keys(model, required=required, path="model")
    expected = {
        "name": "US Macro v51",
        "model_id": "us-macro-v51s",
        "model_mode": "fixed_snapshot",
        "public_label": "US Macro v51 — fixed research snapshot",
        "evidence_snapshot_bound": True,
    }
    for field, expected_value in expected.items():
        if model[field] != expected_value:
            raise ContractError(
                f"Malformed response: model.{field} violates the fixed contract."
            )
    for field in (
        "release",
        "package_hash",
        "snapshot_hash",
        "spec_hash",
        "request_hash",
        "evidence_health",
        "research_status",
    ):
        _string(model[field], f"model.{field}")
    _timestamp(model["as_of"], "model.as_of")
    _timestamp(model["fitted_through"], "model.fitted_through", nullable=True)
    _timestamp(model["settlement_date"], "model.settlement_date", nullable=True)
    _integer(model["forward_source_count"], "model.forward_source_count", minimum=0)
    _integer(model["market_channel_count"], "model.market_channel_count", minimum=0)
    if not isinstance(model["cached"], bool):
        raise ContractError("Malformed response: model.cached must be boolean.")
    health = model["evidence_channel_health"]
    if health is not None:
        health = _object(health, "model.evidence_channel_health")
        _keys(
            health,
            required={
                "status",
                "policy",
                "declared_source_count",
                "active_source_count",
                "dark_source_count",
            },
            path="model.evidence_channel_health",
        )
        if health["status"] not in {"healthy", "degraded"}:
            raise ContractError(
                "Malformed response: evidence channel status is unsupported."
            )
        if health["policy"] not in {"serve_with_flag", "refuse"}:
            raise ContractError(
                "Malformed response: evidence channel policy is unsupported."
            )
        for field in (
            "declared_source_count",
            "active_source_count",
            "dark_source_count",
        ):
            _integer(health[field], f"model.evidence_channel_health.{field}", minimum=0)


def _validate_intervals(value: Any, path: str) -> None:
    intervals = _list(value, path)
    levels: list[float] = []
    for index, raw in enumerate(intervals):
        item_path = f"{path}[{index}]"
        item = _object(raw, item_path)
        _keys(item, required={"level", "lower", "upper"}, path=item_path)
        level = _number(item["level"], f"{item_path}.level", minimum=0, maximum=1)
        lower = _number(item["lower"], f"{item_path}.lower")
        upper = _number(item["upper"], f"{item_path}.upper")
        if level in {0.0, 1.0} or lower is None or upper is None or lower > upper:
            raise ContractError(f"Malformed response: {item_path} is invalid.")
        levels.append(level)
    if levels != sorted(set(levels)):
        raise ContractError(
            f"Malformed response: {path} levels must be ordered and unique."
        )


def _validate_result(value: Any) -> dict[str, Any]:
    result = _object(value, "result")
    kind = result.get("kind")
    if kind not in RESULT_FAMILIES:
        supported = ", ".join(sorted(RESULT_FAMILIES))
        raise ContractError(
            f"Unsupported result family {kind!r}. Supported families: {supported}."
        )
    common_optional = {"method", "approximation"}
    if kind == "terminal":
        _keys(
            result,
            required={"kind", "target_node", "period", "unit", "mean", "intervals"},
            optional={
                "variance",
                "standard_deviation",
                "posterior_draw_count",
                "method",
            },
            path="result",
        )
        for field in ("target_node", "period", "unit"):
            _string(result[field], f"result.{field}")
        _number(result["mean"], "result.mean")
        _number(result.get("variance"), "result.variance", minimum=0, nullable=True)
        _number(
            result.get("standard_deviation"),
            "result.standard_deviation",
            minimum=0,
            nullable=True,
        )
        _integer(
            result.get("posterior_draw_count"),
            "result.posterior_draw_count",
            minimum=1,
            nullable=True,
        )
        _validate_intervals(result["intervals"], "result.intervals")
    elif kind == "threshold_probability":
        _keys(
            result,
            required={
                "kind",
                "target_node",
                "period",
                "unit",
                "direction",
                "threshold",
                "probability",
            },
            optional={"method"},
            path="result",
        )
        for field in ("target_node", "period", "unit"):
            _string(result[field], f"result.{field}")
        if result["direction"] not in {"above", "below"}:
            raise ContractError("Malformed response: result.direction is unsupported.")
        _number(result["threshold"], "result.threshold")
        _number(result["probability"], "result.probability", minimum=0, maximum=1)
    elif kind == "path_probability":
        _keys(
            result,
            required={
                "kind",
                "target_node",
                "unit",
                "event_definition",
                "window_start",
                "window_end",
                "probability",
            },
            optional={"mc_standard_error", "draws"} | common_optional,
            path="result",
        )
        for field in (
            "target_node",
            "unit",
            "event_definition",
            "window_start",
            "window_end",
        ):
            _string(result[field], f"result.{field}")
        _validate_probability_receipt(result)
    elif kind == "joint_probability":
        _keys(
            result,
            required={
                "kind",
                "target_nodes",
                "event_definition",
                "window_start",
                "window_end",
                "probability",
            },
            optional={"mc_standard_error", "draws"} | common_optional,
            path="result",
        )
        _string_list(
            result["target_nodes"], "result.target_nodes", minimum=2, maximum=3
        )
        for field in ("event_definition", "window_start", "window_end"):
            _string(result[field], f"result.{field}")
        _validate_probability_receipt(result)
    elif kind == "conditional_distribution":
        _keys(
            result,
            required={
                "kind",
                "condition_node",
                "target_node",
                "target_period",
                "unit",
                "condition_probability",
                "mean",
                "intervals",
                "interpretation",
            },
            optional={
                "standard_deviation",
                "survivor_draws",
                "effective_draw_fraction",
                "mc_standard_error",
                "draws",
            }
            | common_optional,
            path="result",
        )
        for field in ("condition_node", "target_node", "target_period", "unit"):
            _string(result[field], f"result.{field}")
        _number(
            result["condition_probability"],
            "result.condition_probability",
            minimum=0,
            maximum=1,
        )
        _number(result["mean"], "result.mean")
        _number(
            result.get("standard_deviation"),
            "result.standard_deviation",
            minimum=0,
            nullable=True,
        )
        _integer(
            result.get("survivor_draws"),
            "result.survivor_draws",
            minimum=0,
            nullable=True,
        )
        _number(
            result.get("effective_draw_fraction"),
            "result.effective_draw_fraction",
            minimum=0,
            maximum=1,
            nullable=True,
        )
        if result["interpretation"] != "observational_event_condition":
            raise ContractError(
                "Malformed response: conditional interpretation is unsupported."
            )
        _validate_intervals(result["intervals"], "result.intervals")
        _validate_draw_receipt(result)
    else:
        _keys(
            result,
            required={
                "kind",
                "target_node",
                "unit",
                "functional",
                "window_start",
                "window_end",
                "mean",
                "intervals",
            },
            optional={"standard_deviation", "mc_standard_error", "draws"}
            | common_optional,
            path="result",
        )
        for field in (
            "target_node",
            "unit",
            "functional",
            "window_start",
            "window_end",
        ):
            _string(result[field], f"result.{field}")
        if result["functional"] != kind:
            raise ContractError(
                "Malformed response: path-distribution functional differs from kind."
            )
        _number(result["mean"], "result.mean")
        _number(
            result.get("standard_deviation"),
            "result.standard_deviation",
            minimum=0,
            nullable=True,
        )
        _validate_intervals(result["intervals"], "result.intervals")
        _validate_draw_receipt(result)
    if "method" in result:
        _string(result["method"], "result.method", nullable=True)
    if "approximation" in result:
        _string(result["approximation"], "result.approximation", nullable=True)
    return result


def _validate_probability_receipt(result: dict[str, Any]) -> None:
    _number(result["probability"], "result.probability", minimum=0, maximum=1)
    _validate_draw_receipt(result)


def _validate_draw_receipt(result: dict[str, Any]) -> None:
    _number(
        result.get("mc_standard_error"),
        "result.mc_standard_error",
        minimum=0,
        nullable=True,
    )
    _integer(result.get("draws"), "result.draws", minimum=1, nullable=True)


def _validate_x_draft(value: Any) -> None:
    draft = _object(value, "x_draft")
    _keys(
        draft,
        required={"text", "weighted_length", "intent_url", "posts_automatically"},
        path="x_draft",
    )
    _string(draft["text"], "x_draft.text")
    length = _integer(draft["weighted_length"], "x_draft.weighted_length", minimum=1)
    if length is not None and length > 280:
        raise ContractError("Malformed response: X weighted length exceeds 280.")
    intent_url = _string(draft["intent_url"], "x_draft.intent_url")
    if not intent_url.startswith("https://x.com/intent/tweet?"):
        raise ContractError(
            "Malformed response: X intent URL is not a public Web Intent."
        )
    if draft["posts_automatically"] is not False:
        raise ContractError("Malformed response: X draft must be review-only.")


def _target_label(node: str) -> str:
    return TARGET_LABELS.get(node, node.replace("_", " ").title())


def _format_number(value: float, unit: str) -> str:
    lowered = unit.casefold()
    if "percent" in lowered or "change (%)" in lowered:
        return f"{value:.2f}%"
    if "thousand" in lowered:
        return f"{value:,.0f}k"
    return f"{value:,.2f}"


def _format_probability(value: float) -> str:
    return f"{value * 100:.1f}%"


def _section(title: str, body: list[str]) -> list[str]:
    return ["", title, LIGHT_RULE, *body]


def render_result(result: dict[str, Any], compiled: dict[str, Any]) -> list[str]:
    kind = result["kind"]
    lines: list[str] = []
    if kind == "terminal":
        lines.extend(
            [
                _target_label(result["target_node"]),
                result["period"],
                "",
                f"Forecast: {_format_number(result['mean'], result['unit'])}",
                f"Unit: {result['unit']}",
            ]
        )
        lines.extend(_render_intervals(result.get("intervals", []), result["unit"]))
        if result.get("standard_deviation") is not None:
            lines.append(
                "Standard deviation: "
                + _format_number(result["standard_deviation"], result["unit"])
            )
    elif kind == "threshold_probability":
        label = _target_label(result["target_node"])
        lines.extend(
            [
                (
                    f"Chance {label} is {result['direction']} "
                    f"{_format_number(result['threshold'], result['unit'])}"
                ),
                result["period"],
                "",
                f"Probability: {_format_probability(result['probability'])}",
                f"Unit: {result['unit']}",
            ]
        )
    elif kind == "path_probability":
        lines.extend(
            [
                result["event_definition"],
                f"Window: {result['window_start']} → {result['window_end']}",
                "",
                f"Probability: {_format_probability(result['probability'])}",
                f"Target: {_target_label(result['target_node'])}",
                f"Unit: {result['unit']}",
            ]
        )
        lines.extend(_render_draw_receipt(result))
    elif kind == "joint_probability":
        lines.extend(
            [
                "Chance the complete joint event occurs:",
                result["event_definition"],
                f"Window: {result['window_start']} → {result['window_end']}",
                "",
                f"Probability: {_format_probability(result['probability'])}",
                "Targets:",
            ]
        )
        lines.extend(f"- {_target_label(node)}" for node in result["target_nodes"])
        lines.extend(_render_draw_receipt(result))
    elif kind == "conditional_distribution":
        lines.extend(
            [
                f"Condition node: {_target_label(result['condition_node'])}",
                f"Condition probability: {_format_probability(result['condition_probability'])}",
            ]
        )
        if compiled.get("event_definition"):
            lines.append(f"Event: {compiled['event_definition']}")
        lines.extend(
            [
                "",
                f"Conditional forecast for {_target_label(result['target_node'])}",
                f"Period: {result['target_period']}",
                f"Forecast: {_format_number(result['mean'], result['unit'])}",
                f"Unit: {result['unit']}",
            ]
        )
        lines.extend(_render_intervals(result.get("intervals", []), result["unit"]))
        lines.extend(_render_draw_receipt(result))
        lines.append("Observational conditioning, not a causal intervention.")
    else:
        label = "Path extremum" if kind == "extremum" else "Window arithmetic mean"
        lines.extend(
            [
                f"{label}: {_target_label(result['target_node'])}",
                f"Window: {result['window_start']} → {result['window_end']}",
            ]
        )
        if compiled.get("event_definition"):
            lines.append(f"Functional: {compiled['event_definition']}")
        lines.extend(
            [
                "",
                f"Forecast mean: {_format_number(result['mean'], result['unit'])}",
                f"Unit: {result['unit']}",
            ]
        )
        lines.extend(_render_intervals(result.get("intervals", []), result["unit"]))
        lines.extend(_render_draw_receipt(result))
    if result.get("method"):
        lines.append(f"Method: {result['method']}")
    if result.get("approximation"):
        lines.append(f"Approximation: {result['approximation']}")
    return lines


def _render_intervals(intervals: list[dict[str, Any]], unit: str) -> list[str]:
    return [
        f"{interval['level'] * 100:g}% interval: "
        f"{_format_number(interval['lower'], unit)} to "
        f"{_format_number(interval['upper'], unit)}"
        for interval in intervals
    ]


def _render_draw_receipt(result: dict[str, Any]) -> list[str]:
    lines = []
    if result.get("mc_standard_error") is not None:
        lines.append(f"Monte Carlo standard error: {result['mc_standard_error']:.4f}")
    if result.get("draws") is not None:
        lines.append(f"Simulation draws: {result['draws']:,}")
    if result.get("survivor_draws") is not None:
        lines.append(f"Condition-surviving draws: {result['survivor_draws']:,}")
    if result.get("effective_draw_fraction") is not None:
        lines.append(
            "Effective draw fraction: "
            f"{_format_probability(result['effective_draw_fraction'])}"
        )
    return lines


def render_terminal(
    response: dict[str, Any], *, fixture: dict[str, Any] | None = None
) -> str:
    lines = ["US MACRO NEWS TO FORECAST", HEAVY_RULE]
    if fixture is not None:
        lines.extend(
            _section(
                "DEMO",
                [
                    fixture["label"],
                    f"{fixture['publisher']} · {fixture['publication_date']}",
                    fixture["title"],
                    fixture["canonical_url"],
                    f"Relationship: {fixture['relationship'].title()}",
                    f"Selected question: {fixture['selected_question']}",
                    (
                        f"Showcase result: {fixture['result']} · "
                        f"{fixture['unit']} · {fixture['result_type']}"
                    ),
                    f"Relationship note: {fixture['relationship_note']}",
                ],
            )
        )
    analysis = response["analysis"]
    lines.extend(_section("WHAT HAPPENED", [analysis["news_summary"]]))
    if analysis["key_facts"]:
        lines.extend(["", "Key facts:"])
        lines.extend(f"- {fact}" for fact in analysis["key_facts"])
    lines.extend(
        _section(
            "MACRO SIGNAL",
            [analysis["macro_signal"] or "No strong supported macro signal."],
        )
    )
    lines.extend(
        _section(
            "TRANSMISSION",
            [analysis["transmission_channel"] or "No supported transmission channel."],
        )
    )
    if response["status"] == "domain_rejected":
        lines.extend(
            _section(
                "NO STRONG US MACRO QUESTION",
                [
                    response["message"],
                    "",
                    response["reason"],
                    "",
                    "No forecast was run.",
                    "No X draft was created.",
                ],
            )
        )
        if response["caveats"]:
            lines.extend(
                _section("CAVEATS", [f"- {item}" for item in response["caveats"]])
            )
        return "\n".join(lines).rstrip() + "\n"

    selected_id = response["selection"]["candidate_id"]
    candidate_lines: list[str] = []
    for index, candidate in enumerate(response["candidates"], start=1):
        marker = "  SELECTED" if candidate["id"] == selected_id else ""
        validity = "valid" if candidate["valid"] else "not executable"
        candidate_lines.extend(
            [
                f"{index}. {candidate['question']}{marker}",
                f"   Type: {candidate['request_family']}",
                "   Targets: "
                + ", ".join(_target_label(node) for node in candidate["target_nodes"]),
                f"   Horizon: {candidate['horizon']}",
                f"   Score: {candidate['score']['total']:.1f}/100 · {validity}",
                "   Components: "
                + " · ".join(
                    f"{label} {candidate['score'][key]}/5"
                    for key, label in SCORE_LABELS[:4]
                ),
                "               "
                + " · ".join(
                    f"{label} {candidate['score'][key]}/5"
                    for key, label in SCORE_LABELS[4:]
                ),
                f"   Reason: {candidate['reason']}",
            ]
        )
        if candidate["reason_codes"]:
            candidate_lines.append(
                "   Validity notes: " + ", ".join(candidate["reason_codes"])
            )
        if index != len(response["candidates"]):
            candidate_lines.append("")
    lines.extend(_section("QUESTIONS CONSIDERED", candidate_lines))
    selection = response["selection"]
    selection_lines = [
        selection["question"],
        "",
        "Why this question:",
        selection["why_selected"],
    ]
    if response.get("forecast_relationship"):
        selection_lines.extend(
            [
                "",
                f"Forecast relationship: {response['forecast_relationship'].title()}",
                f"Relationship note: {response['relationship_note']}",
            ]
        )
    lines.extend(_section("SELECTED QUESTION", selection_lines))
    lines.extend(
        _section(
            "POLYBRIDGE FORECAST",
            render_result(response["result"], response["compiled_request"]),
        )
    )
    model = response["model"]
    model_lines = [
        f"Model: {model['public_label']}",
        "Mode: Reproducible snapshot",
        f"Contract mode: {model['model_mode']}",
        f"As of: {model['as_of']}",
        f"Fitted through: {model['fitted_through'] or 'Not supplied'}",
        f"Release: {model['release']}",
        f"Research status: {model['research_status']}",
        f"Evidence health: {model['evidence_health']}",
    ]
    if model.get("settlement_date"):
        model_lines.append(f"Settlement: {model['settlement_date']}")
    channel = model.get("evidence_channel_health")
    if channel:
        model_lines.append(
            "Evidence channels: "
            f"{channel['status']} · {channel['active_source_count']}/"
            f"{channel['declared_source_count']} active · policy {channel['policy']}"
        )
    model_lines.extend(
        [
            "",
            "This cookbook uses a fixed model snapshot for reproducibility.",
        ]
    )
    lines.extend(_section("MODEL", model_lines))
    compiled = response["compiled_request"]
    audit_lines = [
        f"Schema: {response['schema_version']}",
        f"Request ID: {response['request_id']}",
        f"Forecast operation: {compiled['kind']}",
        "Forecast targets: " + ", ".join(compiled["target_nodes"]),
        f"Model executions: {compiled['model_execution_count']}",
    ]
    lines.extend(_section("AUDIT TRAIL", audit_lines))
    if response["caveats"]:
        lines.extend(_section("CAVEATS", [f"- {item}" for item in response["caveats"]]))
    draft = response["x_draft"]
    lines.extend(
        _section(
            "X DRAFT — REVIEW ONLY",
            [
                draft["text"],
                "",
                f"Weighted length: {draft['weighted_length']}/280",
                f"Compose: {draft['intent_url']}",
                "",
                "Nothing has been posted.",
                "Nothing is posted until you choose Post in X.",
            ],
        )
    )
    return "\n".join(lines).rstrip() + "\n"


def build_artifact(
    response: dict[str, Any],
    *,
    context: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc)
    source_text = context.get("source_text")
    artifact: dict[str, Any] = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "client_version": CLIENT_VERSION,
        "generated_at": generated_at.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "input_mode": context["input_mode"],
        "fixture_id": context.get("fixture_id"),
        "source": dict(response["source"]),
        "platform_response": response,
    }
    if source_text is not None:
        artifact["source_sha256"] = hashlib.sha256(
            source_text.encode("utf-8")
        ).hexdigest()
    return artifact


def _safe_run_id(response: dict[str, Any], generated_at: datetime) -> str:
    timestamp = generated_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    request_id = re.sub(r"[^A-Za-z0-9_-]", "", response.get("request_id", ""))[:24]
    return f"{timestamp}-{request_id or 'run'}"


def save_artifact(
    artifact: dict[str, Any],
    *,
    response: dict[str, Any],
    output_path: Path | None,
    generated_at: datetime,
) -> Path:
    path = (
        output_path
        or DEFAULT_OUTPUT_DIR / f"{_safe_run_id(response, generated_at)}.json"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = (
            json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
        os.replace(temporary, path)
    except OSError as exc:
        raise CookbookError(
            "artifact_write_failed",
            "The public audit artifact could not be saved.",
            exit_code=5,
        ) from exc
    return path


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(BASE_DIR))
    except ValueError:
        return str(path)


def _json_dump(value: Any, stream: TextIO) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def run(
    argv: list[str] | None = None,
    *,
    session: requests.Session | Any | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    stdin: TextIO = sys.stdin,
    browser_open: Callable[[str], Any] = webbrowser.open,
    interactive: bool | None = None,
    now: Callable[[], datetime] | None = None,
) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    json_requested = "--json" in argv
    try:
        examples = load_examples()
        parser = build_parser(examples)
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:
            return int(exc.code)
        payload, context = build_request(args)
        api_key = _clean_optional(os.getenv("POLYBRIDGE_API_KEY"))
        response = PolyBridgeClient(api_key=api_key, session=session).forecast(payload)
        generated_at = (now or (lambda: datetime.now(timezone.utc)))()
        artifact_path: Path | None = None
        if args.output is not None or not args.json:
            artifact = build_artifact(
                response, context=context, generated_at=generated_at
            )
            artifact_path = save_artifact(
                artifact,
                response=response,
                output_path=args.output,
                generated_at=generated_at,
            )
        if args.json:
            _json_dump(response, stdout)
            return 0
        fixture = examples.get(args.demo) if args.demo else None
        stdout.write(render_terminal(response, fixture=fixture))
        if artifact_path is not None:
            stdout.write(f"\nSaved: {_display_path(artifact_path)}\n")
        should_prompt = interactive
        if should_prompt is None:
            should_prompt = bool(stdin.isatty() and stdout.isatty())
        if response["status"] == "forecast" and should_prompt:
            stdout.write("\nOpen draft in X? [y/N] ")
            stdout.flush()
            answer = stdin.readline().strip().casefold()
            if answer == "y":
                browser_open(response["x_draft"]["intent_url"])
                stdout.write(
                    "Opened the review draft. Nothing was posted automatically.\n"
                )
        return 0
    except CookbookError as exc:
        if json_requested:
            _json_dump(exc.as_json(), stdout)
        else:
            stderr.write(f"Error: {exc.message}\n")
        return exc.exit_code


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
