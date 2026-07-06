# Agentic Finance Evidence Gate Schema Contract

This document describes the public schema contract for the Agentic Finance Evidence Gate cookbook. The cookbook is research/demo software, not financial advice, not a trading system, and not a live or real-money broker execution integration. Tier 1 is the multi-leg Evidence Gate. Tier 2 is the Portfolio Event-Risk Map. Tier 3 is the optional Alpaca paper-preview and guarded paper-submission layer.

Every public object uses:

```json
{
  "allowed_use": "research_only_not_financial_advice"
}
```

The prompt pack in `prompts/` is documentation only. Prompt outputs must still conform to the objects below, keep `EvidencePacket` as the adapter boundary, treat Search relevance as metadata only, use Forecast as the probability surface, and write memo plus redacted audit artifacts.

## MultiLegThesis

Purpose: configures a deterministic, multi-question thesis gate. Thresholds are user configuration, not model output.

Required fields:

- `thesis_id`
- `as_of`
- `demo`
- `evergreen`
- `thesis`
- `instrument`
- `direction`
- `notional_usd`
- `questions`

Each question includes:

- `q`
- `supports_when`, either `YES` or `NO`
- `threshold`

Safety notes:

- A thesis is not an order and not a recommendation.
- Search relevance is never a probability.
- Forecast probability is the only probability surface.
- The gate must not use a confidence scalar.

Example:

```json
{
  "thesis_id": "labor-resilience-jul2026",
  "as_of": "2026-07-04",
  "demo": true,
  "evergreen": true,
  "thesis": "US labor market stays resilient through July 2026",
  "instrument": "SPY",
  "direction": "long",
  "notional_usd": 1000,
  "questions": [
    {
      "q": "Will the US lose jobs in July 2026?",
      "supports_when": "NO",
      "threshold": 0.25
    }
  ]
}
```

## MultiLegGateDecision

Purpose: deterministic replay gate result for a thesis with multiple evidence legs.

Rules:

- Margin `M = 0.15`.
- If `supports_when = NO`, probability at or below the threshold supports the thesis and probability at or above `threshold + M` contradicts it.
- If `supports_when = YES`, probability at or above the threshold supports the thesis and probability at or below `threshold - M` contradicts it.
- `direct_only` and `direct_mixed` legs have weight `1.0`.
- `proxy_only` legs have weight `0.5`.
- insufficient or failed legs have weight `0.0`.
- Verdict is `PROCEED` only when weighted support is at least `2.0`, at least two legs have direct evidence, no full-weight contradiction exists, and no full-weight leg has insufficient data.

Safety notes:

- Leg evidence is normalized into `EvidencePacket` objects before gate evaluation.
- Raw provider responses do not enter gate logic.
- The gate does not consume confidence scalars.
- A `PROCEED` verdict permits only a local paper-preview object unless the separate guarded paper submission command is explicitly run.

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
  "scenario_id": "labor-resilience-jul2026",
  "thesis": "US labor market stays resilient through July 2026",
  "symbol": "SPY",
  "exposure_direction": "increase_long_exposure",
  "notional_usd": 1000.0,
  "forecast_question": "Will the US lose jobs in July 2026? | Will the US unemployment rate for July 2026 be above 4.3%? | Will the Fed cut rates at its September 2026 meeting?",
  "search_query": "US labor market stays resilient through July 2026 prediction market evidence",
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
  "source": "recorded_fixture_market",
  "question": "US payrolls negative in July 2026?",
  "url": "https://example.invalid/markets/us-payrolls-july-2026-negative",
  "probability": 0.12,
  "relevance": 0.98,
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
  "packet_id": "ep_sample_labor_jobs",
  "created_at": "2026-07-04T12:00:00Z",
  "scenario_id": "labor-resilience-jul2026",
  "question": "Will the US lose jobs in July 2026?",
  "probability": 0.12,
  "confidence": 0.91,
  "confidence_interval": {
    "lower": 0.08,
    "upper": 0.15
  },
  "evidence_profile": {
    "fixture_mode": true,
    "live_polybridge": false,
    "forecast_status": "ok",
    "search_status": "ok",
    "search_result_count": 2,
    "search_max_relevance": 0.99,
    "source_market_count": 6,
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
  "timestamp": "2026-07-04T12:00:00Z",
  "scenario_id": "labor-resilience-jul2026",
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

## PortfolioHolding

Purpose: one row from the local holdings CSV used by the Portfolio Event-Risk Map tier.

Required fields:

- `schema_version`
- `symbol`
- `name`
- `quantity`
- `notional_usd`
- `sector`

Safety notes:

- Holdings samples must be fake or sanitized before commit.
- Do not include account IDs, custodian data, tax lots, order IDs, or broker account data.
- Runtime holdings paths in audit records must be sanitized relative paths when possible.

## PortfolioExposure

Purpose: deterministic mapping from holdings to event-risk exposures.

Required fields:

- `schema_version`
- `exposure_id`
- `label`
- `risk_theme`
- `drivers`
- `affected_symbols`
- `affected_notional_usd`
- `portfolio_weight`
- `forecast_question`
- `search_query`
- `source_rules`

Safety notes:

- Exposure mapping must be deterministic local code.
- No LLM call is required or allowed for mapping.
- Broad equity and technology holdings can map to rates, inflation, volatility, tariff/geopolitical, AI regulation, China/Taiwan, export-control, and rates drivers.
- Rates, energy, and gold holdings map to their documented deterministic drivers.

## PortfolioRiskMap

Purpose: JSON artifact for the read-only portfolio event-risk tier.

Required fields:

- `schema_version`
- `run_id`
- `created_at`
- `tier`
- `allowed_use`
- `portfolio`
- `methodology`
- `exposures`
- `risk_items`
- `guardrails`

Safety notes:

- `tier` must be `portfolio_event_risk_map`.
- `methodology.probability_source` must be `forecast_only`.
- `methodology.search_relevance_use` must be `metadata_only`.
- `methodology.adapter_boundary` must be `EvidencePacket`.
- Gate logic consumes normalized `EvidencePacket` objects only.
- The portfolio tier must not create an Alpaca preview object, broker submission path, or real-money execution path.
- The portfolio memo must describe risk review only and must not contain buy, sell, or recommendation language.

Example:

```json
{
  "schema_version": "portfolio_risk_map.v1",
  "tier": "portfolio_event_risk_map",
  "run_id": "run_sample_portfolio",
  "portfolio": {
    "holding_count": 5,
    "total_notional_usd": 13350.0,
    "symbols": ["SPY", "QQQ", "TLT", "XLE", "GLD"]
  },
  "methodology": {
    "mapping": "deterministic_local_rules",
    "adapter_boundary": "EvidencePacket",
    "probability_source": "forecast_only",
    "search_relevance_use": "metadata_only",
    "raw_polybridge_responses_persisted": false
  },
  "guardrails": {
    "read_only_portfolio_workflow": true,
    "local_holdings_csv": true,
    "no_live_broker_calls": true,
    "no_broker_submission": true,
    "no_real_money_trading_path": true
  }
}
```

## PortfolioAuditRecord

Purpose: redacted JSONL record for a portfolio event-risk run.

Required fields:

- `schema_version`
- `run_id`
- `timestamp`
- `tier`
- `holdings_source`
- `exposures`
- `evidence_packets`
- `gate_decisions`
- `output_paths`
- `guardrails`

Safety notes:

- Runtime portfolio audit logs are written to ignored runtime outputs.
- `holdings_source` and output paths must not expose local usernames or absolute local paths.
- Evidence packets may include provenance hashes, but raw PolyBridge response bodies, headers, bearer tokens, API keys, account IDs, and order IDs must not be persisted.
- Guardrails must show read-only portfolio workflow, local holdings input, no live broker calls, no broker submission, no real-money path, no raw PolyBridge response persistence, and redaction.

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

- The preview object alone is not a submission instruction.
- `submit_supported` must be `false`.
- `human_approval_required` must be `true`.
- Guarded paper submission requires a separate explicit command, paper credentials, confirmation flags, a cleared gate, and submission guardrails.
- Alpaca fields must not leak into `EvidencePacket` or `GateDecision`.
- This cookbook is not a trading system and not financial advice.

Example:

```json
{
  "schema_version": "paper_order_preview.v1",
  "broker": "alpaca",
  "mode": "paper_preview_only",
  "symbol": "SPY",
  "side": "buy",
  "notional_usd": 1000.0,
  "created_at": "2026-07-04T12:00:00Z",
  "human_approval_required": true,
  "submit_supported": false,
  "allowed_use": "research_only_not_financial_advice"
}
```

## AlpacaPaperConfig

Purpose: environment-derived configuration for explicit Alpaca paper account validation.

Required runtime values:

- API key from `APCA_API_KEY_ID` or `ALPACA_API_KEY`
- API secret from `APCA_API_SECRET_KEY` or `ALPACA_SECRET_KEY`
- paper base URL, defaulting to `https://paper-api.alpaca.markets`

Optional runtime value:

- `ALPACA_PAPER_TRADE=true`

Safety notes:

- This object is not written to committed assets.
- Missing credentials block validation.
- `ALPACA_PAPER_TRADE=false` blocks validation.
- Live-looking base URLs block validation.
- Headers and credential values must be redacted from errors and logs.
- Paper account validation fetches sanitized account metadata only and does not submit orders.
- Guarded paper submission additionally requires `ALPACA_PAPER_TRADE=true`, an exact paper base URL, all confirmation flags, an allowlisted symbol, and the demo notional cap.

## AlpacaPaperAccountCheck

Purpose: sanitized metadata output from explicit Alpaca paper account validation.

Required fields:

- `schema_version`
- `broker`
- `mode`
- `paper_endpoint_validated`
- `account_status`
- `trading_blocked`
- `transfers_blocked`
- `account_id`
- `buying_power`
- `allowed_use`
- `no_order_submission`

Safety notes:

- `mode` must be `paper_account_validation`.
- `paper_endpoint_validated` must be `true`.
- `account_id` and `buying_power` must be redacted or sample placeholders.
- Raw account payloads, headers, API keys, secrets, bearer tokens, and local absolute paths must not be persisted.
- This object is a paper account metadata check only. It is not an order, not execution, and not financial advice.

Example:

```json
{
  "schema_version": "alpaca_paper_account_check.v1",
  "broker": "alpaca",
  "mode": "paper_account_validation",
  "paper_endpoint_validated": true,
  "account_status": "ACTIVE",
  "trading_blocked": false,
  "transfers_blocked": false,
  "account_id": "sample_redacted",
  "buying_power": "sample_redacted",
  "allowed_use": "research_only_not_financial_advice",
  "no_order_submission": true
}
```

## AlpacaPaperSubmissionResult

Purpose: sanitized output from an explicit guarded Alpaca paper submission.

Required fields:

- `schema_version`
- `broker`
- `mode`
- `submitted`
- `paper_endpoint_validated`
- `order_id`
- `client_order_id`
- `symbol`
- `side`
- `notional`
- `status`
- `allowed_use`
- `no_live_trading`
- `human_approval_confirmed`

Safety notes:

- `mode` must be `paper_submission_result`.
- `submitted` may be `true` only after all guarded paper submission checks pass.
- The paper base URL must be exactly `https://paper-api.alpaca.markets`.
- `ALPACA_PAPER_TRADE=true` is required.
- Confirmation flags for paper trading, non-advice, and human approval are required.
- Symbols must be allowlisted.
- Notional must be within the demo cap.
- Order IDs and client order IDs must be redacted or sample placeholders.
- Raw broker responses, account IDs, headers, API keys, secrets, bearer tokens, and local absolute paths must not be persisted.
- This object is simulated paper trading output only. It is not live trading and not financial advice.

Example:

```json
{
  "schema_version": "alpaca_paper_submission_result.v1",
  "broker": "alpaca",
  "mode": "paper_submission_result",
  "submitted": true,
  "paper_endpoint_validated": true,
  "order_id": "sample_redacted",
  "client_order_id": "sample_redacted",
  "symbol": "SPY",
  "side": "buy",
  "notional": "1000.00",
  "status": "accepted",
  "allowed_use": "research_only_not_financial_advice",
  "no_live_trading": true,
  "human_approval_confirmed": true
}
```

## AlpacaPaperSubmissionAuditRecord

Purpose: redacted JSONL audit event for explicit guarded paper submission.

Required fields:

- `schema_version`
- `run_id`
- `timestamp`
- `scenario_id`
- `tier`
- `paper_only`
- `human_approval_confirmed`
- `no_live_trading`
- `paper_preview_path`
- `order_result_path`
- `submission_result`
- `guardrails`

Safety notes:

- `tier` must be `alpaca_paper_submission`.
- `paper_only`, `human_approval_confirmed`, and `no_live_trading` must be `true`.
- `order_result_path` should be relative to the cookbook directory or sanitized as an external output.
- Guardrails must show paper endpoint only, no live trading, no raw broker response, no account data, and redaction.
- The audit record must not include raw broker responses, headers, credentials, account IDs, real order IDs, or local absolute paths.
