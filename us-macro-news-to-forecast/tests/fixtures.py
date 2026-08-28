"""Test-only synthetic responses matching the public Platform contract."""

from __future__ import annotations

from copy import deepcopy
from urllib.parse import quote

TEST_ONLY_NOTICE = (
    "Synthetic contract values for offline tests; never present as a live result."
)


def _score(total: float) -> dict:
    return {
        "source_grounding": 5,
        "transmission_strength": 5,
        "model_fit": 5,
        "horizon_fit": 5,
        "resolution_quality": 5,
        "quantitative_interest": 4,
        "public_clarity": 5,
        "caveat_burden": 1,
        "total": total,
    }


def _candidate(
    candidate_id: str,
    *,
    family: str,
    nodes: list[str],
    question: str,
    total: float,
) -> dict:
    return {
        "id": candidate_id,
        "question": question,
        "target_nodes": nodes,
        "request_family": family,
        "horizon": "Synthetic covered test window",
        "score": _score(total),
        "valid": True,
        "reason": "Synthetic public reason used only to test rendering.",
        "reason_codes": [],
    }


def _model() -> dict:
    return {
        "name": "US Macro v51",
        "model_id": "us-macro-v51s",
        "model_mode": "fixed_snapshot",
        "public_label": "US Macro v51 — fixed research snapshot",
        "release": "synthetic-test-release",
        "as_of": "2000-01-02T00:00:00Z",
        "fitted_through": "1999-12-31T23:59:59Z",
        "package_hash": "test-only-package-hash",
        "snapshot_hash": "test-only-snapshot-hash",
        "spec_hash": "test-only-spec-hash",
        "request_hash": "test-only-request-hash",
        "evidence_health": "ready",
        "evidence_snapshot_bound": True,
        "forward_source_count": 4,
        "market_channel_count": 2,
        "evidence_channel_health": {
            "status": "healthy",
            "policy": "serve_with_flag",
            "declared_source_count": 6,
            "active_source_count": 6,
            "dark_source_count": 0,
        },
        "research_status": "synthetic_research_test_only",
        "cached": False,
        "settlement_date": "2000-02-01T12:30:00Z",
    }


def _analysis() -> dict:
    return {
        "news_summary": "A synthetic macro story is grounded for an offline contract test.",
        "key_facts": [
            "The story text and every numerical result are explicitly synthetic."
        ],
        "macro_signal": "Synthetic macro signal",
        "transmission_channel": "Synthetic source signal → supported forecast target",
    }


def _source() -> dict:
    return {
        "kind": "text",
        "source_url": "https://example.com/synthetic-story",
        "publisher": "Synthetic Test News",
        "title": "Test-only macro story",
        "extracted_chars": 180,
    }


def _result(kind: str) -> tuple[dict, list[str], str | None, str | None, str | None]:
    intervals = [
        {"level": 0.5, "lower": 1.5, "upper": 2.5},
        {"level": 0.8, "lower": 1.0, "upper": 3.0},
        {"level": 0.9, "lower": 0.5, "upper": 3.5},
    ]
    if kind == "terminal":
        return (
            {
                "kind": "terminal",
                "target_node": "payroll_growth",
                "period": "2099-01",
                "unit": "Thousands of jobs",
                "mean": 2.0,
                "variance": 0.25,
                "standard_deviation": 0.5,
                "intervals": intervals,
                "posterior_draw_count": 200,
                "method": "synthetic_test_method",
            },
            ["payroll_growth"],
            "2099-01",
            None,
            None,
        )
    if kind == "threshold_probability":
        return (
            {
                "kind": "threshold_probability",
                "target_node": "headline_cpi_yoy",
                "period": "2099-01",
                "unit": "Year-over-year change (%)",
                "direction": "above",
                "threshold": 3.0,
                "probability": 0.25,
                "method": "synthetic_test_method",
            },
            ["headline_cpi_yoy"],
            "2099-01",
            None,
            "headline_cpi_yoy above a synthetic threshold in 2099-01",
        )
    if kind == "path_probability":
        event = "headline_cpi_yoy hits above a synthetic threshold in the test window"
        return (
            {
                "kind": "path_probability",
                "target_node": "headline_cpi_yoy",
                "unit": "Year-over-year change (%)",
                "event_definition": event,
                "window_start": "2099-01",
                "window_end": "2099-03",
                "probability": 0.25,
                "mc_standard_error": 0.01,
                "draws": 1024,
                "method": "synthetic_test_method",
                "approximation": "synthetic_test_approximation",
            },
            ["headline_cpi_yoy"],
            None,
            "2099-01",
            event,
        )
    if kind == "joint_probability":
        event = "headline CPI or unemployment crosses its synthetic test threshold"
        return (
            {
                "kind": "joint_probability",
                "target_nodes": ["headline_cpi_yoy", "unemployment_rate"],
                "event_definition": event,
                "window_start": "2099-01",
                "window_end": "2099-03",
                "probability": 0.25,
                "mc_standard_error": 0.01,
                "draws": 1024,
                "method": "synthetic_test_method",
                "approximation": "synthetic_test_approximation",
            },
            ["headline_cpi_yoy", "unemployment_rate"],
            None,
            "2099-01",
            event,
        )
    if kind == "conditional_distribution":
        event = "industrial production conditional on a synthetic financial-conditions event"
        return (
            {
                "kind": "conditional_distribution",
                "condition_node": "financial_conditions",
                "target_node": "industrial_production_growth",
                "target_period": "2099-03",
                "unit": "Year-over-year change (%)",
                "condition_probability": 0.25,
                "mean": 2.0,
                "standard_deviation": 0.5,
                "intervals": intervals,
                "survivor_draws": 256,
                "effective_draw_fraction": 0.25,
                "mc_standard_error": 0.01,
                "draws": 1024,
                "interpretation": "observational_event_condition",
                "method": "synthetic_test_method",
                "approximation": "synthetic_test_approximation",
            },
            ["financial_conditions", "industrial_production_growth"],
            "2099-03",
            "2099-01",
            event,
        )
    if kind == "extremum":
        event = "minimum payroll_growth in the synthetic test window"
        return (
            {
                "kind": "extremum",
                "target_node": "payroll_growth",
                "unit": "Thousands of jobs",
                "functional": "extremum",
                "window_start": "2099-01",
                "window_end": "2099-03",
                "mean": 2.0,
                "standard_deviation": 0.5,
                "intervals": intervals,
                "mc_standard_error": 0.01,
                "draws": 1024,
                "method": "synthetic_test_method",
                "approximation": "synthetic_test_approximation",
            },
            ["payroll_growth"],
            None,
            "2099-01",
            event,
        )
    if kind == "window_aggregate":
        event = "mean policy_stance in the synthetic test window"
        return (
            {
                "kind": "window_aggregate",
                "target_node": "policy_stance",
                "unit": "Percent",
                "functional": "window_aggregate",
                "window_start": "2099-01",
                "window_end": "2099-03",
                "mean": 2.0,
                "standard_deviation": 0.5,
                "intervals": intervals,
                "mc_standard_error": 0.01,
                "draws": 1024,
                "method": "synthetic_test_method",
                "approximation": "synthetic_test_approximation",
            },
            ["policy_stance"],
            None,
            "2099-01",
            event,
        )
    raise ValueError(f"unsupported synthetic fixture family: {kind}")


def forecast_response(kind: str = "terminal") -> dict:
    result, nodes, period, window_start, event = _result(kind)
    window_end = result.get("window_end")
    question = f"What is the synthetic {kind} test question?"
    candidates = [
        _candidate(
            "candidate_1",
            family=kind,
            nodes=nodes,
            question=question,
            total=96.0,
        ),
        _candidate(
            "candidate_2",
            family="terminal",
            nodes=["unemployment_rate"],
            question="What is the synthetic unemployment terminal test question?",
            total=88.0,
        ),
        _candidate(
            "candidate_3",
            family="path_probability",
            nodes=["headline_cpi_yoy"],
            question="What is the synthetic CPI path-probability test question?",
            total=82.0,
        ),
    ]
    draft_text = f"TEST ONLY: synthetic {kind} review draft."
    response = {
        "schema_version": "polybridge.us-macro-news-demo.v1",
        "status": "forecast",
        "request_id": f"test-{kind}",
        "source": _source(),
        "analysis": _analysis(),
        "candidates": candidates,
        "selection": {
            "candidate_id": "candidate_1",
            "question": question,
            "why_selected": "Selected because: synthetic test receipt",
            "score": 96.0,
        },
        "compiled_request": {
            "kind": kind,
            "target_nodes": nodes,
            "period": period,
            "window_start": window_start,
            "window_end": window_end,
            "event_definition": event,
            "model_execution_count": 1,
        },
        "model": _model(),
        "result": result,
        "public_wording": f"Synthetic test-only public wording for {kind}.",
        "x_draft": {
            "text": draft_text,
            "weighted_length": len(draft_text),
            "intent_url": "https://x.com/intent/tweet?text="
            + quote(draft_text, safe=""),
            "posts_automatically": False,
        },
        "caveats": [
            "This is a synthetic test-only response.",
            "This result uses a fixed research snapshot.",
        ],
        "forecast_relationship": "direct",
        "relationship_note": "The story directly concerns the forecast quantity.",
    }
    return deepcopy(response)


def showcase_response(example_id: str) -> dict:
    metadata = {
        "inflation-ap": {
            "kind": "path_probability",
            "publisher": "Associated Press",
            "title": (
                "Inflation slows but prices remain elevated as Iran war and spending on "
                "AI push up prices"
            ),
            "url": (
                "https://apnews.com/article/consumer-prices-inflation-fed-interest-"
                "rates-150e179a6c6b3182ba05cedf0188394b"
            ),
            "question": (
                "What are the chances US headline inflation rises above 4% at any point "
                "from September through December 2026?"
            ),
            "relationship": "direct",
            "relationship_note": "The story directly concerns the forecast quantity.",
            "x_draft": (
                "Inflation has eased, but price pressures haven't disappeared.\n\n"
                "Did America declare victory over inflation too soon?\n\n"
                "PolyBridge puts the chance of US headline inflation rising above 4% at "
                "any point from September through December at 18.4%.\n\n"
                "https://apnews.com/article/consumer-prices-inflation-fed-interest-"
                "rates-150e179a6c6b3182ba05cedf0188394b"
            ),
        },
        "jobs-axios": {
            "kind": "extremum",
            "publisher": "Axios",
            "title": "U.S. economy surprisingly lost 23,000 jobs in July",
            "url": "https://www.axios.com/2026/08/07/july-jobs-report-employment-losses",
            "question": (
                "How high does PolyBridge expect the US unemployment rate to get between "
                "September 2026 and March 2027?"
            ),
            "relationship": "direct",
            "relationship_note": "The story directly concerns the forecast quantity.",
            "x_draft": (
                "The US unexpectedly lost 23,000 jobs in July.\n\n"
                "Does the wider jobs market weaken too?\n\n"
                "PolyBridge expects unemployment to peak around 4.93% by the end of "
                "March '27.\n\n"
                "https://www.axios.com/2026/08/07/july-jobs-report-employment-losses"
            ),
        },
        "treasury-markets-guardian": {
            "kind": "terminal",
            "publisher": "The Guardian",
            "title": (
                "US treasury doubles debt buyback to steady bond market amid inflation "
                "fears"
            ),
            "url": (
                "https://www.theguardian.com/business/2026/aug/19/"
                "us-treasury-doubles-debt-buyback-bond-market"
            ),
            "question": (
                "How strong does PolyBridge expect US economic growth to be in the fourth "
                "quarter of 2026?"
            ),
            "relationship": "related",
            "relationship_note": (
                "The story helped choose the question. It did not update the model."
            ),
            "x_draft": (
                "Treasury is doubling long-end buybacks as pressure remains in bond "
                "markets.\n\n"
                "How much does the economy slow?\n\n"
                "PolyBridge's baseline for Q4 US real GDP growth is 2.37%.\n\n"
                "https://www.theguardian.com/business/2026/aug/19/"
                "us-treasury-doubles-debt-buyback-bond-market"
            ),
        },
    }[example_id]
    response = forecast_response(metadata["kind"])
    response["request_id"] = f"test-{example_id}"
    response["source"] = {
        "kind": "example",
        "source_url": metadata["url"],
        "publisher": metadata["publisher"],
        "title": metadata["title"],
        "extracted_chars": 240,
    }
    response["candidates"][0]["question"] = metadata["question"]
    response["selection"]["question"] = metadata["question"]
    response["forecast_relationship"] = metadata["relationship"]
    response["relationship_note"] = metadata["relationship_note"]
    response["x_draft"] = {
        "text": metadata["x_draft"],
        "weighted_length": 260,
        "intent_url": "https://x.com/intent/tweet?text="
        + quote(metadata["x_draft"], safe=""),
        "posts_automatically": False,
    }

    if example_id == "inflation-ap":
        event = (
            "US headline inflation rises above 4% at any point from September through "
            "December 2026"
        )
        response["candidates"][0].update(
            {
                "target_nodes": ["headline_cpi_yoy"],
                "request_family": "path_probability",
                "horizon": "September through December 2026",
            }
        )
        response["compiled_request"].update(
            {
                "target_nodes": ["headline_cpi_yoy"],
                "period": None,
                "window_start": "2026-09",
                "window_end": "2026-12",
                "event_definition": event,
            }
        )
        response["result"].update(
            {
                "unit": "Year-over-year change (%)",
                "event_definition": event,
                "window_start": "2026-09",
                "window_end": "2026-12",
                "probability": 0.184,
            }
        )
    elif example_id == "jobs-axios":
        event = "maximum unemployment rate from September 2026 through March 2027"
        response["candidates"][0].update(
            {
                "target_nodes": ["unemployment_rate"],
                "request_family": "extremum",
                "horizon": "September 2026 through March 2027",
            }
        )
        response["compiled_request"].update(
            {
                "target_nodes": ["unemployment_rate"],
                "period": None,
                "window_start": "2026-09",
                "window_end": "2027-03",
                "event_definition": event,
            }
        )
        response["result"].update(
            {
                "target_node": "unemployment_rate",
                "unit": "Percent of the labor force",
                "window_start": "2026-09",
                "window_end": "2027-03",
                "mean": 4.93,
                "standard_deviation": 0.2,
                "intervals": [
                    {"level": 0.5, "lower": 4.80, "upper": 5.06},
                    {"level": 0.8, "lower": 4.67, "upper": 5.19},
                    {"level": 0.9, "lower": 4.60, "upper": 5.26},
                ],
            }
        )
    else:
        response["candidates"][0].update(
            {
                "target_nodes": ["real_gdp_growth"],
                "request_family": "terminal",
                "horizon": "Fourth quarter of 2026",
            }
        )
        response["compiled_request"].update(
            {
                "target_nodes": ["real_gdp_growth"],
                "period": "2026Q4",
                "window_start": None,
                "window_end": None,
                "event_definition": None,
            }
        )
        response["result"].update(
            {
                "target_node": "real_gdp_growth",
                "period": "2026Q4",
                "unit": "Annualized quarterly change (%)",
                "mean": 2.37,
                "variance": 0.1,
                "standard_deviation": 0.32,
                "intervals": [
                    {"level": 0.5, "lower": 2.15, "upper": 2.59},
                    {"level": 0.8, "lower": 1.96, "upper": 2.78},
                    {"level": 0.9, "lower": 1.84, "upper": 2.90},
                ],
            }
        )
    return deepcopy(response)


def domain_rejected_response() -> dict:
    return {
        "schema_version": "polybridge.us-macro-news-demo.v1",
        "status": "domain_rejected",
        "request_id": "test-domain-rejected",
        "source": _source(),
        "analysis": {
            "news_summary": "A synthetic non-macro story was evaluated for the offline test.",
            "key_facts": [],
            "macro_signal": None,
            "transmission_channel": None,
        },
        "candidates": [],
        "reason": "No credible supported US macro transmission channel was found.",
        "message": (
            "This story does not have a strong supported US macro forecasting angle for this "
            "fixed model snapshot."
        ),
        "caveats": ["Frozen US Macro v51 was not called."],
    }


ALL_FORECAST_RESPONSES = {
    kind: forecast_response(kind)
    for kind in (
        "terminal",
        "threshold_probability",
        "path_probability",
        "joint_probability",
        "conditional_distribution",
        "extremum",
        "window_aggregate",
    )
}
