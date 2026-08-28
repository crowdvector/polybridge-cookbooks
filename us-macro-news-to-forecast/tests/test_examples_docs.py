from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

COOKBOOK_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = COOKBOOK_DIR.parent
EXAMPLES_PATH = COOKBOOK_DIR / "golden_examples.json"
README_PATH = COOKBOOK_DIR / "README.md"

EXPECTED_EXAMPLES = [
    {
        "id": "inflation-ap",
        "label": "Inflation",
        "publisher": "Associated Press",
        "title": (
            "Inflation slows but prices remain elevated as Iran war and spending "
            "on AI push up prices"
        ),
        "publication_date": "2026-08-12",
        "canonical_url": (
            "https://apnews.com/article/consumer-prices-inflation-fed-interest-"
            "rates-150e179a6c6b3182ba05cedf0188394b"
        ),
        "relationship": "direct",
        "relationship_note": "The story directly concerns the forecast quantity.",
        "selected_question": (
            "What are the chances US headline inflation rises above 4% at any point "
            "from September through December 2026?"
        ),
        "result": "18.4%",
        "result_type": "Probability/path-hit forecast",
        "unit": "Probability",
        "x_draft": (
            "Inflation has eased, but price pressures haven't disappeared.\n\n"
            "Did America declare victory over inflation too soon?\n\n"
            "PolyBridge puts the chance of US headline inflation rising above 4% at "
            "any point from September through December at 18.4%.\n\n"
            "https://apnews.com/article/consumer-prices-inflation-fed-interest-"
            "rates-150e179a6c6b3182ba05cedf0188394b"
        ),
    },
    {
        "id": "jobs-axios",
        "label": "Jobs",
        "publisher": "Axios",
        "title": "U.S. economy surprisingly lost 23,000 jobs in July",
        "publication_date": "2026-08-07",
        "canonical_url": (
            "https://www.axios.com/2026/08/07/july-jobs-report-employment-losses"
        ),
        "relationship": "direct",
        "relationship_note": "The story directly concerns the forecast quantity.",
        "selected_question": (
            "How high does PolyBridge expect the US unemployment rate to get between "
            "September 2026 and March 2027?"
        ),
        "result": "4.93%",
        "result_type": "Maximum/extremum forecast across the window",
        "unit": "US unemployment rate",
        "x_draft": (
            "The US unexpectedly lost 23,000 jobs in July.\n\n"
            "Does the wider jobs market weaken too?\n\n"
            "PolyBridge expects unemployment to peak around 4.93% by the end of "
            "March '27.\n\n"
            "https://www.axios.com/2026/08/07/july-jobs-report-employment-losses"
        ),
    },
    {
        "id": "treasury-markets-guardian",
        "label": "Treasury markets",
        "publisher": "The Guardian",
        "title": (
            "US treasury doubles debt buyback to steady bond market amid inflation "
            "fears"
        ),
        "publication_date": "2026-08-19",
        "canonical_url": (
            "https://www.theguardian.com/business/2026/aug/19/"
            "us-treasury-doubles-debt-buyback-bond-market"
        ),
        "relationship": "related",
        "relationship_note": (
            "The story helped choose the question. It did not update the model."
        ),
        "selected_question": (
            "How strong does PolyBridge expect US economic growth to be in the "
            "fourth quarter of 2026?"
        ),
        "result": "2.37%",
        "result_type": "Quarterly baseline forecast",
        "unit": "Annualized percentage change in real GDP during Q4 2026",
        "x_draft": (
            "Treasury is doubling long-end buybacks as pressure remains in bond "
            "markets.\n\n"
            "How much does the economy slow?\n\n"
            "PolyBridge's baseline for Q4 US real GDP growth is 2.37%.\n\n"
            "https://www.theguardian.com/business/2026/aug/19/"
            "us-treasury-doubles-debt-buyback-bond-market"
        ),
    },
]
EXPECTED_IDS = {item["id"] for item in EXPECTED_EXAMPLES}


class GoldenExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
        cls.examples = cls.payload["examples"]

    def test_exact_verified_metadata_is_preserved(self) -> None:
        self.assertEqual(
            self.payload["schema_version"],
            "polybridge.us-macro-news-demo.examples.v3",
        )
        self.assertEqual(self.examples, EXPECTED_EXAMPLES)

    def test_exactly_three_public_example_ids_are_present_and_unique(self) -> None:
        ids = [item["id"] for item in self.examples]
        self.assertEqual(set(ids), EXPECTED_IDS)
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(ids), len(set(ids)))

    def test_examples_store_metadata_without_article_bodies(self) -> None:
        expected_fields = set(EXPECTED_EXAMPLES[0])
        forbidden_fields = {
            "article_body",
            "body",
            "excerpt",
            "story_text",
            "text",
            "probability",
            "forecast_value",
            "model_as_of",
        }
        for example in self.examples:
            with self.subTest(example=example["id"]):
                self.assertEqual(set(example), expected_fields)
                self.assertTrue(forbidden_fields.isdisjoint(example))
                self.assertTrue(example["canonical_url"].startswith("https://"))
                self.assertRegex(example["publication_date"], r"^2026-08-\d{2}$")

    def test_deterministic_examples_do_not_fetch_publishers_in_the_client(self) -> None:
        source = (COOKBOOK_DIR / "us_macro_news_to_forecast.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("requests.get(", source)
        self.assertNotIn("session.get(", source)

    def test_direct_and_related_relationships_are_explicit(self) -> None:
        relationships = {item["id"]: item["relationship"] for item in self.examples}
        self.assertEqual(
            relationships,
            {
                "inflation-ap": "direct",
                "jobs-axios": "direct",
                "treasury-markets-guardian": "related",
            },
        )
        related = self.examples[2]
        self.assertEqual(
            related["relationship_note"],
            "The story helped choose the question. It did not update the model.",
        )
        for example in self.examples:
            self.assertNotIn(
                "financial conditions", example["selected_question"].casefold()
            )

    def test_showcase_results_and_x_drafts_are_exact_and_unit_aware(self) -> None:
        self.assertEqual(
            [example["result"] for example in self.examples],
            ["18.4%", "4.93%", "2.37%"],
        )
        self.assertEqual(
            [example["result_type"] for example in self.examples],
            [
                "Probability/path-hit forecast",
                "Maximum/extremum forecast across the window",
                "Quarterly baseline forecast",
            ],
        )
        self.assertIn("Annualized percentage change", self.examples[2]["unit"])
        for example in self.examples:
            with self.subTest(example=example["id"]):
                self.assertIn(example["result"], example["x_draft"])
                self.assertTrue(example["x_draft"].endswith(example["canonical_url"]))


class DocumentationTests(unittest.TestCase):
    def test_readme_local_links_resolve(self) -> None:
        text = README_PATH.read_text(encoding="utf-8")
        targets = re.findall(r"\[[^]]+\]\(([^)]+)\)", text)
        missing = []
        for target in targets:
            if target.startswith(("https://", "http://", "#")):
                continue
            clean = target.split("#", 1)[0]
            if clean and not (COOKBOOK_DIR / clean).exists():
                missing.append(clean)
        self.assertEqual(missing, [])

    def test_root_index_registers_the_cookbook_as_an_api_example(self) -> None:
        root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        row = next(
            line
            for line in root_readme.splitlines()
            if line.startswith("| `us-macro-news-to-forecast/`")
        )
        self.assertIn("PolyBridge US Macro News demo", row)
        self.assertIn("View GitHub", row)
        legacy_terms = (
            "co" + "lab",
            "note" + "book",
            "." + "ipynb",
            "co" + "lab." + "research.google.com",
        )
        for term in legacy_terms:
            self.assertNotIn(term, row.casefold())

    def test_readme_uses_the_requested_sections_and_model_language(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        headings = re.findall(r"^## (.+)$", readme, flags=re.MULTILINE)
        self.assertEqual(
            headings,
            [
                "What it does",
                "Quick start",
                "Try one of the 3 examples",
                "Run your own article",
                "Adapt the pattern",
            ],
        )
        self.assertIn("News story → question → forecast → post", readme)
        self.assertIn("one workflow you can build with PolyBridge", readme)

    def test_readme_exposes_only_the_three_verified_demo_ids(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        documented_ids = set(re.findall(r"--demo ([a-z0-9-]+)", readme))
        self.assertEqual(documented_ids, EXPECTED_IDS)
        for example in EXPECTED_EXAMPLES:
            with self.subTest(example=example["id"]):
                self.assertIn(example["publisher"], readme)
                self.assertIn(example["title"], readme)
                self.assertIn(example["publication_date"], readme)
                self.assertIn(example["canonical_url"], readme)
                self.assertIn(example["selected_question"], readme)
                self.assertIn(example["result"], readme)

    def test_readme_curl_calls_the_complete_demo_endpoint(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "curl https://api.polybridge.ai/v1/demos/us-macro-news-to-forecast",
            readme,
        )
        self.assertIn(
            '-d \'{"source":{"kind":"url","url":"https://example.com/news-story"}}\'',
            readme,
        )
        self.assertIn("complete demo endpoint", readme)

    def test_readme_keeps_public_results_readable(self) -> None:
        readme = README_PATH.read_text(encoding="utf-8")
        for result in ("18.4%", "4.93%", "2.37%"):
            self.assertIn(result, readme)
        self.assertIn("annualized percentage change in real GDP", readme)
        self.assertNotIn("US financial conditions: -0.58", readme)
        self.assertNotIn("/v1/forecast", readme)
        self.assertNotIn("Model Lab", readme)

    def test_internal_cache_details_are_not_documented(self) -> None:
        public_docs = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (README_PATH, COOKBOOK_DIR / "PROMPT.md")
        ).casefold()
        for term in (
            "redis",
            "cache ttl",
            "concurrency lease",
            "package hash",
            "snapshot hash",
            "spec hash",
            "cloud run cold start",
        ):
            with self.subTest(term=term):
                self.assertNotIn(term, public_docs)

    def test_removed_interactive_surface_does_not_reappear(self) -> None:
        legacy_terms = (
            "co" + "lab",
            "note" + "book",
            "." + "ipynb",
            "co" + "lab." + "research.google.com",
        )
        checked_suffixes = {".json", ".md", ".py", ".sh", ".txt"}
        for path in COOKBOOK_DIR.rglob("*"):
            if not path.is_file() or path.suffix not in checked_suffixes:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").casefold()
            for term in legacy_terms:
                with self.subTest(path=path.name, term=term):
                    self.assertNotIn(term, text)

    def test_prompt_document_is_conceptual_not_a_server_prompt(self) -> None:
        prompt = (COOKBOOK_DIR / "PROMPT.md").read_text(encoding="utf-8")
        self.assertIn("Return exactly three candidates", prompt)
        self.assertIn('"id": "inflation-ap"', prompt)
        self.assertIn("model_execution_count: 1", prompt)
        self.assertIn("does not reproduce server orchestration", prompt)
        self.assertNotIn("system prompt", prompt.casefold())


if __name__ == "__main__":
    unittest.main()
