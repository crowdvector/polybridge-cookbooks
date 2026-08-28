from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

COOKBOOK_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COOKBOOK_DIR))

import us_macro_news_to_forecast as cookbook  # noqa: E402
from tests.fixtures import (  # noqa: E402
    ALL_FORECAST_RESPONSES,
    domain_rejected_response,
    forecast_response,
    showcase_response,
)


class ContractTests(unittest.TestCase):
    def test_all_actual_result_discriminators_validate(self) -> None:
        self.assertEqual(set(ALL_FORECAST_RESPONSES), cookbook.RESULT_FAMILIES)
        for kind, response in ALL_FORECAST_RESPONSES.items():
            with self.subTest(kind=kind):
                self.assertIs(cookbook.validate_response(response), response)

    def test_domain_rejected_discriminator_validates(self) -> None:
        response = domain_rejected_response()
        self.assertIs(cookbook.validate_response(response), response)

    def test_deterministic_example_source_discriminator_validates(self) -> None:
        response = forecast_response()
        response["source"] = {
            "kind": "example",
            "source_url": "https://www.axios.com/2026/08/07/july-jobs-report-employment-losses",
            "publisher": "Axios",
            "title": "U.S. economy surprisingly lost 23,000 jobs in July",
            "extracted_chars": 240,
        }
        self.assertIs(cookbook.validate_response(response), response)

    def test_unknown_result_family_fails_clearly(self) -> None:
        response = forecast_response()
        response["result"]["kind"] = "trajectory"
        response["compiled_request"]["kind"] = "trajectory"
        response["candidates"][0]["request_family"] = "trajectory"
        with self.assertRaises(cookbook.ContractError) as context:
            cookbook.validate_response(response)
        self.assertIn("unsupported", context.exception.message.lower())

    def test_unknown_status_discriminator_fails_clearly(self) -> None:
        response = domain_rejected_response()
        response["status"] = "maybe"
        with self.assertRaises(cookbook.ContractError) as context:
            cookbook.validate_response(response)
        self.assertIn("status discriminator", context.exception.message)

    def test_schema_drift_fails_clearly(self) -> None:
        response = forecast_response()
        response["schema_version"] = "future-schema"
        with self.assertRaises(cookbook.ContractError) as context:
            cookbook.validate_response(response)
        self.assertIn("Unsupported response schema", context.exception.message)

    def test_unknown_public_field_is_not_treated_as_raw_server_internals(self) -> None:
        response = forecast_response()
        response["raw_server_internals"] = {"private": True}
        with self.assertRaises(cookbook.ContractError) as context:
            cookbook.validate_response(response)
        self.assertIn("unknown fields", context.exception.message)

    def test_forecast_requires_exactly_three_candidates(self) -> None:
        response = forecast_response()
        response["candidates"].pop()
        with self.assertRaises(cookbook.ContractError) as context:
            cookbook.validate_response(response)
        self.assertIn("candidate count", context.exception.message)

    def test_selection_must_match_server_candidate(self) -> None:
        response = forecast_response()
        response["selection"]["candidate_id"] = "candidate_3"
        with self.assertRaises(cookbook.ContractError) as context:
            cookbook.validate_response(response)
        self.assertIn("selected candidate receipt", context.exception.message)

    def test_model_is_fixed_snapshot(self) -> None:
        response = forecast_response()
        response["model"]["model_mode"] = "updating"
        with self.assertRaises(cookbook.ContractError) as context:
            cookbook.validate_response(response)
        self.assertIn("fixed contract", context.exception.message)

    def test_conditioning_must_be_observational(self) -> None:
        response = forecast_response("conditional_distribution")
        response["result"]["interpretation"] = "causal_intervention"
        with self.assertRaises(cookbook.ContractError) as context:
            cookbook.validate_response(response)
        self.assertIn("conditional interpretation", context.exception.message)

    def test_interval_units_and_bounds_are_preserved(self) -> None:
        response = forecast_response("terminal")
        original = deepcopy(response["result"]["intervals"])
        cookbook.validate_response(response)
        self.assertEqual(response["result"]["intervals"], original)
        self.assertEqual(response["result"]["unit"], "Thousands of jobs")

    def test_finished_relationship_fields_validate_when_present(self) -> None:
        for example_id in (
            "inflation-ap",
            "jobs-axios",
            "treasury-markets-guardian",
        ):
            with self.subTest(example_id=example_id):
                response = showcase_response(example_id)
                self.assertIs(cookbook.validate_response(response), response)

    def test_relationship_note_must_match_relationship(self) -> None:
        response = showcase_response("treasury-markets-guardian")
        response["relationship_note"] = "A stale relationship explanation."
        with self.assertRaises(cookbook.ContractError) as context:
            cookbook.validate_response(response)
        self.assertIn("relationship_note", context.exception.message)


class ResultRendererTests(unittest.TestCase):
    def test_related_article_metadata_renders_without_changing_result(self) -> None:
        fixture = cookbook.load_examples()["treasury-markets-guardian"]
        response = showcase_response("treasury-markets-guardian")
        rendered = cookbook.render_terminal(response, fixture=fixture)
        self.assertIn("The Guardian · 2026-08-19", rendered)
        self.assertIn("Relationship: Related", rendered)
        self.assertIn(f"Selected question: {fixture['selected_question']}", rendered)
        self.assertIn("Showcase result: 2.37%", rendered)
        self.assertIn(
            "The story helped choose the question. It did not update the model.",
            rendered,
        )
        self.assertIn("Forecast relationship: Related", rendered)
        self.assertIn(response["selection"]["why_selected"], rendered)

    def test_every_result_family_has_a_distinct_renderer(self) -> None:
        expected_fragments = {
            "terminal": "Forecast:",
            "threshold_probability": "Probability:",
            "path_probability": "Window:",
            "joint_probability": "complete joint event",
            "conditional_distribution": "Conditional forecast",
            "extremum": "Path extremum",
            "window_aggregate": "Window arithmetic mean",
        }
        for kind, fragment in expected_fragments.items():
            with self.subTest(kind=kind):
                response = forecast_response(kind)
                rendered = "\n".join(
                    cookbook.render_result(
                        response["result"], response["compiled_request"]
                    )
                )
                self.assertIn(fragment, rendered)

    def test_terminal_preserves_native_unit_and_all_intervals(self) -> None:
        rendered = cookbook.render_terminal(forecast_response("terminal"))
        self.assertIn("Unit: Thousands of jobs", rendered)
        for level in ("50% interval", "80% interval", "90% interval"):
            self.assertIn(level, rendered)
        self.assertNotIn("Probability: 200.0%", rendered)

    def test_probability_semantics_are_preserved(self) -> None:
        threshold = cookbook.render_terminal(forecast_response("threshold_probability"))
        path = cookbook.render_terminal(forecast_response("path_probability"))
        joint = cookbook.render_terminal(forecast_response("joint_probability"))
        self.assertIn("Probability: 25.0%", threshold)
        self.assertIn("Probability: 25.0%", path)
        self.assertIn("Chance the complete joint event occurs", joint)
        self.assertIn("US headline CPI year-over-year", joint)
        self.assertIn("US unemployment rate", joint)

    def test_showcase_results_render_with_understandable_percentage_units(self) -> None:
        inflation = cookbook.render_terminal(showcase_response("inflation-ap"))
        jobs = cookbook.render_terminal(showcase_response("jobs-axios"))
        treasury = cookbook.render_terminal(
            showcase_response("treasury-markets-guardian")
        )
        self.assertIn("Probability: 18.4%", inflation)
        self.assertIn("Forecast mean: 4.93%", jobs)
        self.assertIn("Unit: Percent of the labor force", jobs)
        self.assertIn("Forecast: 2.37%", treasury)
        self.assertIn("Unit: Annualized quarterly change (%)", treasury)
        for interval in ("2.15% to 2.59%", "1.96% to 2.78%"):
            self.assertIn(interval, treasury)

    def test_raw_showcase_json_keeps_numeric_values_and_result_units(self) -> None:
        inflation = showcase_response("inflation-ap")["result"]
        jobs = showcase_response("jobs-axios")["result"]
        treasury = showcase_response("treasury-markets-guardian")["result"]
        self.assertEqual(inflation["probability"], 0.184)
        self.assertEqual(jobs["mean"], 4.93)
        self.assertEqual(treasury["mean"], 2.37)
        self.assertIsInstance(treasury["mean"], float)
        self.assertEqual(treasury["unit"], "Annualized quarterly change (%)")

    def test_conditional_labels_and_observational_caveat_are_visible(self) -> None:
        rendered = cookbook.render_terminal(
            forecast_response("conditional_distribution")
        )
        self.assertIn("Condition node: US financial conditions", rendered)
        self.assertIn("Condition probability: 25.0%", rendered)
        self.assertIn(
            "Observational conditioning, not a causal intervention.", rendered
        )
        self.assertIn("Condition-surviving draws: 256", rendered)

    def test_fixed_snapshot_metadata_is_always_visible(self) -> None:
        rendered = cookbook.render_terminal(forecast_response())
        self.assertIn("US Macro v51 — fixed research snapshot", rendered)
        self.assertIn("Mode: Reproducible snapshot", rendered)
        self.assertIn("Contract mode: fixed_snapshot", rendered)
        self.assertIn("As of: 2000-01-02T00:00:00Z", rendered)
        self.assertIn("Fitted through: 1999-12-31T23:59:59Z", rendered)
        self.assertIn("Research status: synthetic_research_test_only", rendered)
        self.assertIn("Evidence health: ready", rendered)
        self.assertIn("Settlement: 2000-02-01T12:30:00Z", rendered)
        self.assertIn(
            "This cookbook uses a fixed model snapshot for reproducibility.", rendered
        )
        self.assertNotIn("Cached:", rendered)
        self.assertNotIn("Package hash:", rendered)
        self.assertNotIn("Snapshot hash:", rendered)
        self.assertNotIn("Spec hash:", rendered)

    def test_exactly_three_candidates_render_and_server_selection_is_highlighted(
        self,
    ) -> None:
        response = forecast_response()
        rendered = cookbook.render_terminal(response)
        candidate_section = rendered.split("\nSELECTED QUESTION\n", 1)[0]
        for candidate in response["candidates"]:
            self.assertEqual(candidate_section.count(candidate["question"]), 1)
            self.assertIn(f"Score: {candidate['score']['total']:.1f}/100", rendered)
        self.assertEqual(rendered.count("SELECTED"), 2)
        self.assertIn(response["selection"]["why_selected"], rendered)

    def test_domain_rejection_is_successful_and_has_no_x_section(self) -> None:
        rendered = cookbook.render_terminal(domain_rejected_response())
        self.assertIn("NO STRONG US MACRO QUESTION", rendered)
        self.assertIn("No forecast was run.", rendered)
        self.assertIn("No X draft was created.", rendered)
        self.assertNotIn("X DRAFT", rendered)


if __name__ == "__main__":
    unittest.main()
