# Agentic Finance Evidence Gate Schema Contract

This document describes the public schema contract for the offline Agentic Finance Evidence Gate cookbook. The cookbook is research/demo software, not financial advice, not a trading system, and not a broker integration.

Every public object uses:

```json
{
  "allowed_use": "research_only_not_financial_advice"
}
```

## FinancialActionIntent

Purpose: captures the research thesis and the broker-neutral action intent before evidence is fetched or normalized.

Required fields:

- `schema_version`
- `scenario_id`
- `thesis`
- `symbol`
- `exposure_direction`
- `notional_usd`
- `forecast_question`
- `search_query`
- `allowed_use`

Safety notes:

- This object is not an order and not a recommendation.
- `exposure_direction` describes a research intent only.
- Do not include API keys, account IDs, authorization headers, or broker account data.

Example:

```json
{
  "schema_version": "financial_action_intent.v1",
  "scenario_id": "offline-demo-aapl-margin-resilience",
  "thesis": "Evaluate whether evidence is strong enough for a paper-only preview.",
  "symbol": "AAPL",
  "exposure_direction": "increase_long_exposure",
  "notional_usd": 1000.0,
  "forecast_question": "Will Apple report gross margin above 45% for fiscal Q4 2026?",
  "search_query": "Apple fiscal Q4 2026 gross margin prediction market evidence",
  "allowed_use": "research_only_not_financial_advice"
}
```

## SourceMarket

Purpose: represents one sanitized evidence source used inside an `EvidencePacket`.

Allowed use: `research_only_not_financial_advice`, inherited from the enclosing `EvidencePacket`.

Required fields:

- `schema_version`
- `source`
- `question`
- `is_proxy`

Optional fields:

- `url`
- `probability`
- `relevance`

Safety notes:

- Source markets must be sanitized before they enter the packet.
- Do not include raw API responses, headers, secrets, or account data.
- Proxy sources must be marked with `is_proxy=true`.

Example:

```json
{
  "schema_version": "source_market.v1",
  "source": "offline_fixture_market",
  "question": "Offline fixture: Apple gross margin above 45% for fiscal Q4 2026?",
  "url": "https://example.invalid/markets/apple-gross-margin-q4-2026",
  "probability": 0.68,
  "relevance": 0.92,
  "is_proxy": false
}
```

## EvidencePacket

Purpose: normalized evidence contract consumed by the deterministic gate. `EvidencePacket` is the adapter boundary.

Allowed use: `research_only_not_financial_advice`.

Required fields:

- `schema_version`
- `packet_id`
- `created_at`
- `scenario_id`
- `question`
- `probability`
- `confidence`
- `confidence_interval`
- `evidence_profile`
- `source_markets`
- `reasoning_summary`
- `quality_flags`
- `raw_response_sha256`
- `allowed_use`

Safety notes:

- Core gate logic must not consume raw PolyBridge API responses.
- Only `evidence.py` should know the raw fixture or live adapter shape.
- Optional live PolyBridge responses must be normalized into this object before gate logic runs.
- Search relevance may appear in `evidence_profile` as metadata, but Forecast remains the only probability source.
- Raw response bodies, headers, bearer tokens, API keys, and account data must not be persisted.
- `raw_response_sha256` is a provenance hash, not raw evidence.
- Alpaca fields must not appear in `EvidencePacket`.

Example:

```json
{
  "schema_version": "evidence_packet.v1",
  "packet_id": "ep_9e8dc8d275b77a98",
  "created_at": "2026-07-03T12:00:00Z",
  "scenario_id": "offline-demo-aapl-margin-resilience",
  "question": "Will Apple report gross margin above 45% for fiscal Q4 2026?",
  "probability": 0.66,
  "confidence": 0.72,
  "confidence_interval": {
    "lower": 0.56,
    "upper": 0.78
  },
  "evidence_profile": {
    "fixture_mode": true,
    "live_polybridge": false,
    "forecast_status": "ok",
    "search_status": "ok",
    "search_result_count": 2,
    "search_max_relevance": 0.99,
    "source_market_count": 2,
    "proxy_only": false
  },
  "source_markets": [],
  "reasoning_summary": "Sanitized offline fixture summary.",
  "quality_flags": [
    "offline_fixture",
    "sanitized_fixture"
  ],
  "raw_response_sha256": "9e8dc8d275b77a982a3bc1c4767d78b53b785b6b8337e086568d5c9abc14cb2e",
  "allowed_use": "research_only_not_financial_advice"
}
```

## GateConfig

Purpose: deterministic policy thresholds for deciding whether a paper-preview object may be created.

Allowed use: `research_only_not_financial_advice`.

Required fields:

- `schema_version`
- `min_confidence`
- `max_interval_width`
- `min_source_markets`
- `allow_proxy_only`
- `allowed_use`

Safety notes:

- Gate configuration is not model output and should be explicit.
- Lowering thresholds can make the demo less conservative.
- `allow_proxy_only=false` is the default.

Example:

```json
{
  "schema_version": "gate_config.v1",
  "min_confidence": 0.55,
  "max_interval_width": 0.35,
  "min_source_markets": 1,
  "allow_proxy_only": false,
  "allowed_use": "research_only_not_financial_advice"
}
```

## GateDecision

Purpose: deterministic decision result produced from an `EvidencePacket` and `GateConfig`.

Allowed use: `research_only_not_financial_advice`.

Required fields:

- `schema_version`
- `decision`
- `cleared_for_paper_preview`
- `reasons`
- `next_step`
- `config_snapshot`
- `allowed_use`

Safety notes:

- `GateDecision` must not include Alpaca fields.
- `GateDecision` must not contain buy, sell, or recommendation language.
- `cleared_for_paper_preview=true` permits only a local paper-preview object for human review.

Example:

```json
{
  "schema_version": "gate_decision.v1",
  "decision": "cleared_for_paper_preview",
  "cleared_for_paper_preview": true,
  "reasons": [
    "Evidence meets the configured confidence, interval, and source-market thresholds."
  ],
  "next_step": "Create a paper-preview object for explicit human review.",
  "config_snapshot": {
    "min_confidence": 0.55,
    "max_interval_width": 0.35,
    "min_source_markets": 1,
    "allow_proxy_only": false
  },
  "allowed_use": "research_only_not_financial_advice"
}
```

## DecisionMemo

Purpose: human-readable Markdown explanation of the thesis, normalized evidence, gate decision, reasons, sources, next step, and disclaimer.

Allowed use: `research_only_not_financial_advice`.

Required fields:

- `schema_version`
- `memo_id`
- `created_at`
- `scenario_id`
- `markdown`
- `allowed_use`

Safety notes:

- Memo text must say the output is research/demo software and not financial advice.
- Memo text must not include secrets, account data, headers, or raw API responses.
- Memo text must not imply execution or real-money trading.

## AuditRecord

Purpose: redacted JSONL record of the run for reproducibility and review.

Allowed use: `research_only_not_financial_advice`, inherited from the cookbook guardrails and nested records.

Required fields:

- `schema_version`
- `run_id`
- `timestamp`
- `scenario_id`
- `evidence_packet`
- `gate_decision`
- `memo_path`
- `paper_preview_path`
- `guardrails`

Safety notes:

- Runtime audit logs are written to `outputs/audit-log.jsonl` and ignored by git.
- Live PolyBridge mode must not write raw headers, API keys, or unredacted error details to audit records.
- Paths in audit records should be relative to the cookbook directory during normal runs.
- If a path cannot be represented relative to the cookbook, it must use a sanitized fallback.
- Audit records must not include local usernames, home directories, account IDs, secrets, bearer tokens, or authorization headers.

Example:

```json
{
  "schema_version": "audit_record.v1",
  "run_id": "sample_run_sanitized",
  "timestamp": "2026-07-03T12:00:00Z",
  "scenario_id": "offline-demo-aapl-margin-resilience",
  "memo_path": "outputs/decision-memo.md",
  "paper_preview_path": "outputs/alpaca-order-preview.json",
  "guardrails": {
    "offline_fixture_mode": true,
    "no_live_polybridge_calls": true,
    "no_live_broker_calls": true,
    "no_broker_submission": true,
    "paper_preview_only": true,
    "secrets_redacted": true
  }
}
```

## PaperOrderPreview

Purpose: local Alpaca-style paper-preview object created only when the gate clears.

Allowed use: `research_only_not_financial_advice`.

Required fields:

- `schema_version`
- `broker`
- `mode`
- `symbol`
- `side`
- `notional_usd`
- `created_at`
- `human_approval_required`
- `submit_supported`
- `allowed_use`

Safety notes:

- This cookbook supports preview only.
- `submit_supported` must be `false`.
- `human_approval_required` must be `true`.
- The object is not an order and cannot be submitted by this cookbook.
- Alpaca fields must not leak into `EvidencePacket` or `GateDecision`.
- This cookbook is not a trading system and not financial advice.

Example:

```json
{
  "schema_version": "paper_order_preview.v1",
  "broker": "alpaca",
  "mode": "paper_preview_only",
  "symbol": "AAPL",
  "side": "buy",
  "notional_usd": 1000.0,
  "created_at": "2026-07-03T12:00:00Z",
  "human_approval_required": true,
  "submit_supported": false,
  "allowed_use": "research_only_not_financial_advice"
}
```
