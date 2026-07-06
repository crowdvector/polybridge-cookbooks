# Agentic Finance Schema

This document describes the technical contracts for the Market Foresight Before Trading cookbook. The cookbook is research/demo software, not financial advice, not a trading system, and not a live or real-money broker integration.

## Thesis Config

`examples/sample_theses.json` contains the shipped thesis object:

- `thesis_id`
- `as_of`
- `demo`
- `evergreen`
- `thesis`
- `instrument`
- `direction`
- `notional_usd`
- `questions`

Each question contains:

- `q`
- `supports_when`: `YES` or `NO`
- `threshold`: probability threshold supplied by the user/demo config

Thresholds are configuration, not model output.

## Recorded Replay

`examples/recorded_run_2026-07-04.json` contains sanitized replay data keyed by thesis ID. Each leg contains:

- `question`
- `probability`
- `interval`
- `evidence_profile`
- `direct_market_count`
- `proxy_market_count`
- `expected_classification`
- `expected_weight`
- `reasoning_summary`
- `source_markets`

Forecast probability is the only probability source. Search relevance and source-market relevance are metadata only.

## Gate Logic

Margin `M = 0.15`.

For `supports_when == "NO"`:

- `p <= threshold` => `SUPPORTS`
- `p >= threshold + M` => `CONTRADICTS`
- otherwise => `NEUTRAL`

For `supports_when == "YES"`:

- `p >= threshold` => `SUPPORTS`
- `p <= threshold - M` => `CONTRADICTS`
- otherwise => `NEUTRAL`

Weights:

- `direct_only` or `direct_mixed` => `1.0`
- `proxy_only` => `0.5`
- `insufficient_data` or failed leg => `0.0`

Verdict is `PROCEED` only when all are true:

- weighted support is at least `2.0`
- no full-weight contradiction
- at least two direct-evidence legs
- no full-weight leg has insufficient data

The gate does not use confidence scalars.

## Tier 1 Outputs

`tier1_evidence_gate.py` writes:

- `outputs/evidence-packet.json`
- `outputs/gate-decision.json`
- `outputs/decision-result.json`
- `outputs/decision-memo.md`
- `outputs/decisions.jsonl`

The decisions log record includes:

- `schema_version`
- `run_id`
- `timestamp`
- `tier`
- `scenario_id`
- `replay_source`
- `verdict`
- `weighted_support`
- `direct_evidence_legs`
- `leg_decisions`
- `paper_preview`
- `output_paths`
- `guardrails`

Runtime output paths may be absolute on a local machine, but committed sample assets use relative paths only.

## SimBroker CLI Preview

`tier3_paper_trader.py` creates a SimBroker preview only after a `PROCEED` verdict.

Preview fields:

- `schema_version`
- `broker`
- `broker_name`
- `mode`
- `thesis_id`
- `symbol`
- `side`
- `notional_usd`
- `allowed_use`
- `no_api_keys_required`
- `no_brokerage_account_required`
- `no_network_calls`
- `no_live_trading`
- `human_confirmation_required`

The preview is not a real order and does not move money.

## SimBroker CLI Fill

After human confirmation, SimBroker appends a fill to `outputs/paper_portfolio.jsonl`.

Core fields shared with the SimBroker MCPB bundle:

- `ts`
- `order_id`
- `symbol`
- `side`
- `notional_usd`
- `simulated`
- `no_real_trading`

CLI fill records also include:

- `schema_version`
- `thesis_id`
- `broker`
- `allowed_use`

No prices, quotes, market data, profit/loss, account IDs, or raw broker responses are recorded.

## Tier 3 Audit

`outputs/decisions.jsonl` also receives a SimBroker audit event with:

- `schema_version`
- `run_id`
- `ts`
- `tier`
- `thesis_id`
- `mode`
- `verdict`
- `leg_summaries`
- `broker`
- `human_decision`
- `order_id`
- `order`
- `order_preview`
- `paper_portfolio_path`
- `paths`
- `simulated_result`
- `guardrails`
- `allowed_use`

When a human declines, `human_decision` is `human_declined`, `order_id` is null, and no simulated fill is written.

## SimBroker MCPB

The SimBroker MCPB source lives in `simbroker-mcpb/`.

The bundle stores data in `SIMBROKER_DATA_DIR` when set, else `~/.simbroker/`. It maintains one folder per account:

- `paper_portfolio.jsonl`
- `orders.jsonl`
- `account.json`

Tool count: seven.

- `create_account`
- `list_accounts`
- `get_account`
- `preview_order`
- `place_simulated_order`
- `get_portfolio`
- `reset_account`

Every tool response ends with:

```text
Simulated. No real trading. Not financial advice.
```

MCPB fill records use the same core fields as the CLI fill record and may additionally include:

- `preview_id`
- `account`
- `reason`
- `cash_after`

The MCPB bundle does not fetch prices, quotes, market data, or ticker existence. Positions are shown at cost basis only.
