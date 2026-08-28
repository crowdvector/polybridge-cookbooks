# Agent workflow: US Macro News to Forecast

Use this cookbook as a public client of `POST /v1/demos/us-macro-news-to-forecast`. It explains the endpoint workflow and its public audit fields; it does not reproduce server orchestration.

## Conceptual sequence

1. **Provide one source.** Send a reviewed example ID, a public HTTPS article URL, or story text with optional `source_url`, `publisher`, and `title` attribution.
2. **Resolve the source.** Reviewed examples use deterministic server-owned content. Custom URLs and text are extracted or normalized, and the endpoint returns a concise `analysis`: `news_summary`, `key_facts`, `macro_signal`, and `transmission_channel`.
3. **Return exactly three candidates.** Reviewed examples use their approved question set. For a custom story, the endpoint proposes three supported forecast questions within the fixed snapshot's target, functional, and horizon coverage.
4. **Validate and score on the server.** Each public candidate carries its question, target nodes, request family, horizon, public component scores, total, validity, reason, and reason codes. Treat these as an audit receipt; do not rescore them in the client.
5. **Select exactly one question.** When a candidate passes the server's validation and quality checks, `selection` identifies it and `compiled_request` summarizes the factual operation. The receipt reports `model_execution_count: 1`.
6. **Execute the fixed model.** The forecast model, not the story analysis, supplies the numerical result. No model switch, scenario, intervention, or fallback belongs in the client.
7. **Return provenance and review copy.** A forecast response includes typed `result`, model metadata, relationship wording, public wording, caveats, and a review-only `x_draft`. A `domain_rejected` response explains why no model call or draft was produced.

## Public request

Reviewed example source:

```json
{
  "source": {
    "kind": "example",
    "id": "inflation-ap"
  }
}
```

Example IDs are an exact allowlist. Do not attach story text or attribution metadata to an example request, and do not fetch the article URL in the client. Public example metadata labels each article relationship as `direct` or `related`. For a related result, preserve the explanation: "The story helped choose the question. It did not update the model."

URL source:

```json
{
  "source": {
    "kind": "url",
    "url": "https://example.com/macro-story"
  }
}
```

Text source:

```json
{
  "source": {
    "kind": "text",
    "text": "A sufficiently detailed US macro story goes here.",
    "source_url": "https://example.com/macro-story",
    "publisher": "Example News",
    "title": "Example macro headline"
  }
}
```

If `POLYBRIDGE_API_KEY` is present, send it as a bearer token. Never log or persist that header. If a configured token fails, stop instead of retrying anonymously.

## Public response audit fields

First branch on `status`:

- `forecast` — exactly three candidates, one selection, one compiled factual request, fixed-snapshot model metadata, a discriminated quantitative result, optional `forecast_relationship` and `relationship_note` fields, public wording, caveats, and an X Web Intent.
- `domain_rejected` — grounded analysis plus a public reason and caveat; no forecast result or X draft.

For a forecast, branch again on `result.kind`: `terminal`, `threshold_probability`, `path_probability`, `joint_probability`, `conditional_distribution`, `extremum`, or `window_aggregate`. Preserve each family's native probability, distribution, interval, unit, condition, event, and simulation fields. Conditional results are observational event conditioning, not causal interventions.

The model receipt identifies the fixed public model and its timing and evidence status. Preserve the raw public response in JSON or generated artifacts; keep reader-facing output focused on the question, result, units, relationship, and caveats.

## Reproduce through the endpoint

Use the bundled CLI rather than rebuilding the server workflow:

```bash
python3 us_macro_news_to_forecast.py --demo inflation-ap --json
```

Or call the public endpoint directly with the request shapes above and an honest timeout of several minutes. Send the POST once. Do not retry automatically after timeout, connection loss, rate limits, or server failures because execution status may be ambiguous.

`PROMPT.md` is not a substitute for the server's private analysis, validation, or routing logic. Agents should consume the public candidates, selection, operation summary, result discriminator, and provenance rather than attempting to infer hidden instructions.

## X boundary

Treat `x_draft.text` and `x_draft.intent_url` as review material. Display them exactly. Opening the Web Intent requires explicit local user confirmation, and publishing still requires the user to choose **Post** in X. Never add posting credentials or an automatic publish path.

## Model positioning

This demo uses a fixed model. The story helps choose the question; it does not update the model.
