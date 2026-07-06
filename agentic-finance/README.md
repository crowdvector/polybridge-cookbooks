# Agentic Finance Evidence Gate

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb)

> Safety banner: this cookbook is research/demo software, not financial advice. Offline mode is the default. Optional live PolyBridge evidence mode is read-only. Optional Alpaca paper account validation is explicit, paper-only, and metadata-only. Guarded paper submission is off by default, simulated only, and requires explicit human confirmation. No live trades are placed.

## Quick Links

- Colab: https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb
- GitHub folder: https://github.com/crowdvector/polybridge-cookbooks/tree/main/agentic-finance
- Disclaimer: `DISCLAIMER.md`

## What This Is

The most important agentic finance behavior is not trading. It is knowing when not to trade.

This cookbook has three research/demo tiers for financial-agent guardrails. PolyBridge is the probability-and-evidence layer before an agent acts. Alpaca appears only as a simulated paper-trading adapter after the gate clears and explicit paper safeguards are met.

Tier 1 is the multi-leg Evidence Gate:

```text
financial thesis
  -> replayed or optional live PolyBridge Search/Forecast evidence
  -> normalized EvidencePackets per leg
  -> deterministic multi-leg Evidence Gate
  -> decision memo
  -> redacted JSONL audit log
  -> optional Alpaca-style paper order preview object only when the gate says PROCEED
```

Tier 2 is the Portfolio Event-Risk Map:

```text
holdings CSV
  -> deterministic exposure mapping
  -> offline fixtures or optional live PolyBridge Search/Forecast evidence per exposure
  -> normalized EvidencePackets
  -> deterministic Evidence Gate decisions
  -> portfolio risk map JSON
  -> portfolio risk memo Markdown
  -> redacted JSONL audit log
```

The demo is designed for teams evaluating agentic finance guardrails. It uses fake, sanitized fixtures by default to model how evidence can be normalized before any broker-format object is created. Optional live PolyBridge mode fetches Search and Forecast evidence, remains read-only, and still writes only local review artifacts. The portfolio tier is a read-only risk memo workflow, not a recommendation or trade/action workflow.

The main end-to-end demo is `labor-resilience-jul2026`: a three-leg labor-resilience thesis that produces a `PROCEED` verdict on the recorded replay and prepares an SPY long paper preview for `$1,000.00` notional. The decline examples are `oil-shock-jul2026` and `rates-fall-2026`; both write memos and audits without preparing a paper preview.

PolyBridge supplies probabilities and evidence only. Thresholds are user configuration, not model output. Search relevance is metadata only; Forecast is the probability surface. The gate can say no.

The cookbook also includes an optional Alpaca paper adapter. Preview-only mode requires no credentials and does not call Alpaca. Paper account validation must be requested explicitly, requires paper credentials, validates the paper endpoint, fetches only sanitized account metadata, and does not submit orders. Guarded paper submission must be requested separately, requires all confirmation flags, enforces the paper endpoint, symbol allowlist, and demo notional cap, and remains simulated paper trading only.

## What This Is Not

- Not financial advice.
- Not an investment recommendation system.
- Not a trading bot.
- Not connected to live PolyBridge APIs unless `--live-polybridge` is explicitly selected.
- Not connected to Alpaca unless an explicit paper account validation or guarded paper submission command is run.
- Not capable of live order submission.
- Not capable of default or accidental order submission.
- Not a real-money workflow.
- Not a portfolio action engine.

## Quickstart

### Setup

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/agentic-finance
bash setup.sh
```

### Run Offline Evidence Gate

From the cookbook folder:

```bash
python tier1_evidence_gate.py --thesis labor-resilience-jul2026 --replay examples/recorded_run_2026-07-04.json
```

From the repository root:

```bash
python agentic-finance/tier1_evidence_gate.py --thesis labor-resilience-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json
```

Expected recorded replay result: `PROCEED`, weighted support `3.0`, no full-weight contradictions, and a local SPY paper preview.

Decline examples:

```bash
python agentic-finance/tier1_evidence_gate.py --thesis oil-shock-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json
python agentic-finance/tier1_evidence_gate.py --thesis rates-fall-2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json
```

### Run Offline Portfolio Event-Risk Map

From the repository root:

```bash
python3 agentic-finance/run_portfolio_risk_map.py --offline --holdings agentic-finance/examples/sample_holdings.csv
```

From the cookbook folder:

```bash
python3 run_portfolio_risk_map.py --offline --holdings examples/sample_holdings.csv
```

### Run Alpaca Paper Preview Only

This runs the labor-resilience replay and writes a local Alpaca-style SPY paper preview if the gate clears. It requires no Alpaca credentials and does not call Alpaca:

```bash
python agentic-finance/tier3_alpaca_paper_trader.py --thesis labor-resilience-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json --preview-only
```

### Optional Live PolyBridge Mode

Live PolyBridge mode is available but is never the default:

```bash
python3 agentic-finance/evidence_gate.py --live-polybridge
```

If `POLYBRIDGE_API_KEY` is unset, live mode omits the `Authorization` header entirely and uses anonymous PolyBridge limits. If a configured key is rejected with `401` or `403`, the run fails clearly and does not retry anonymously. Live mode is still read-only and is not financial advice.

### Optional Alpaca Paper Account Validation

Paper account validation is available only by explicit command:

```bash
python3 agentic-finance/run_alpaca_paper_check.py --validate-paper-account
```

This command requires paper credentials and `APCA_API_BASE_URL=https://paper-api.alpaca.markets`. It fetches sanitized paper account metadata with `GET /v2/account` only, writes `outputs/alpaca-paper-account-check.json`, and does not submit orders. Use paper keys only; live-looking base URLs are blocked.

### Optional Guarded Alpaca Paper Submission

This is not part of the first quickstart. Do not run it unless you understand Alpaca paper trading, have explicit human approval, and are using paper credentials only.

Full Alpaca paper-trading run:

```bash
export APCA_API_KEY_ID="your_paper_key_id"
export APCA_API_SECRET_KEY="your_paper_secret_key"
export APCA_API_BASE_URL="https://paper-api.alpaca.markets"
export ALPACA_PAPER_TRADE="true"
```

Guarded paper submission is off by default and requires every confirmation flag:

```bash
python agentic-finance/tier3_alpaca_paper_trader.py \
  --thesis labor-resilience-jul2026 \
  --replay agentic-finance/examples/recorded_run_2026-07-04.json \
  --submit-paper-order \
  --confirm-paper-trading \
  --confirm-not-financial-advice \
  --confirm-human-approval
```

It requires `ALPACA_PAPER_TRADE=true` and `APCA_API_BASE_URL=https://paper-api.alpaca.markets`, blocks live-looking endpoints, blocks symbols outside `SPY,QQQ,TLT,GLD,XLE,AAPL`, and blocks notional values above the default demo cap of `1000.00` USD. It writes `outputs/alpaca-paper-submission-result.json` only after the offline Evidence Gate clears and all guardrails pass. This is simulated paper trading, not live trading, not financial advice, and not a recommendation.

### Open In Colab

Use the badge at the top of this README or open:

```text
https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb
```

The notebook runs offline fixtures by default, does not require API keys, and previews generated local artifacts.

### Prompt Pack

Use `PROMPT.md` as the prompt index. Copy-paste workflow prompts live in `prompts/`.

## Files

- `tier1_evidence_gate.py` is the public Tier 1 multi-leg replay entry point.
- `tier3_alpaca_paper_trader.py` is the public Tier 3 paper-preview and guarded paper-submission entry point.
- `evidence_gate.py` is the legacy single-leg Tier 1 runnable entry point kept for compatibility.
- `run_portfolio_risk_map.py` is the Tier 2 runnable entry point.
- `run_alpaca_paper_check.py` runs preview-only mode, explicit Alpaca paper account validation, or explicit guarded Alpaca paper submission.
- `agentic_finance/` contains the offline workflow package and optional live PolyBridge adapter.
- `prompts/` contains copy-paste prompts for Claude, Cursor, MCP-style agents, broker-neutral workflows, custom agents, and portfolio review agents.
- `examples/sample_theses.json` and `examples/recorded_run_2026-07-04.json` contain the primary multi-leg demo replay.
- `fixtures/` contains legacy sanitized PolyBridge-shaped Search and Forecast fixtures plus the single-leg thesis.
- `examples/sample_holdings.csv` is a local, fake portfolio input for the portfolio tier.
- `assets/` contains sanitized committed sample outputs.
- `outputs/` is the default runtime output directory and is ignored by git.
- `tests/` contains stdlib `unittest` coverage.

## Output Files

Runtime outputs are written to `agentic-finance/outputs/` by default:

- `evidence-packet.json`
- `gate-decision.json`
- `decision-result.json`
- `decision-memo.md`
- `decisions.jsonl`
- `audit-log.jsonl`
- `alpaca-order-preview.json`, only when the evidence gate clears
- `alpaca-paper-account-check.json`, only when explicit paper account validation is requested
- `alpaca-paper-submission-result.json`, only when explicit guarded paper submission is requested and all guardrails pass
- portfolio risk map JSON from the portfolio tier
- portfolio risk memo Markdown from the portfolio tier

The committed examples in `assets/` are sanitized samples. Runtime audit logs should not be committed.

## Schema Summary

See `SCHEMA.md` for the full schema contract.

`EvidencePacket` includes:

- `packet_id`
- `created_at`
- `question`
- `probability`
- `confidence`
- `confidence_interval`
- `evidence_profile`
- `source_markets`
- `reasoning_summary`
- `quality_flags`
- `allowed_use`
- `raw_response_sha256`

The allowed-use value is always:

```text
research_only_not_financial_advice
```

## Agent Prompt Pack

`PROMPT.md` is the index for workflow prompts. The prompt files are:

- `prompts/claude-mcp.md`
- `prompts/cursor.md`
- `prompts/custom-agent.md`
- `prompts/broker-neutral-workflow.md`
- `prompts/portfolio-risk-map.md`

They are documentation-only workflow contracts. They require evidence first, Forecast as the probability surface, Search relevance as metadata only, `EvidencePacket` as the adapter boundary, memo and audit outputs, and a human approval boundary before any broker-format paper-preview object.

## Gate Rules

Default deterministic gate config:

- `min_confidence = 0.55`
- `max_interval_width = 0.35`
- `min_source_markets = 1`
- `allow_proxy_only = false`

Possible decisions:

- `cleared_for_paper_preview`
- `memo_only`
- `watchlist_only`
- `blocked_weak_evidence`
- `blocked_insufficient_evidence`
- `blocked_api_error`

The gate does not provide investment advice. A cleared result only means the local demo may create a broker-format paper-preview object for human review.

## Live PolyBridge Mode

`--live-polybridge` on Tier 1 uses `fixtures/thesis.json` for the thesis, Search query, and Forecast question, then fetches live Search and Forecast evidence. `--live-polybridge` on Tier 2 uses the local holdings CSV and deterministic exposure mapping, then fetches live Search and Forecast evidence per exposure. Search relevance is stored only as search metadata; Forecast remains the only probability source. Raw PolyBridge responses are normalized into `EvidencePacket` before gate evaluation.

This mode does not call Alpaca, does not submit broker orders, and does not create a real-money trading path.

## Portfolio Event-Risk Map

The portfolio tier reads a local holdings CSV and maps holdings to deterministic event-risk exposures. The built-in sample maps broad equity, technology, rates, energy, and gold holdings to rates/inflation, volatility/geopolitical, AI regulation/export-control, and energy/shipping-disruption exposures.

The portfolio memo is a risk review artifact only. It does not connect to a broker, does not create an order object, does not submit anything, and does not tell a reader to change a portfolio.

## Audit Log Notes

Audit records are JSONL and are redacted before write. The runtime record includes:

- `run_id`
- timestamp
- scenario ID
- evidence packet
- gate decision
- memo path
- optional paper preview path
- guardrails showing offline/live evidence mode, no live broker calls, no broker submission, and paper-preview-only behavior

Portfolio audit records include:

- tier name
- sanitized holdings source path
- deterministic exposures
- normalized evidence packets
- gate decisions
- portfolio output paths
- guardrails showing read-only mode, local holdings input, no live broker calls, no broker submission, no real-money path, and no persisted raw PolyBridge responses

Guarded paper submission audit records include:

- `tier = alpaca_paper_submission`
- `paper_only = true`
- `human_approval_confirmed = true`
- `no_live_trading = true`
- relative or sanitized output paths
- no raw broker response
- no account data

Redaction covers authorization headers, bearer tokens, known PolyBridge and Alpaca env names, and obvious token-like strings.

## Alpaca Paper Preview, Account Check, And Guarded Submission

`agentic_finance/brokers/alpaca.py` does not import the Alpaca SDK. It creates a local `PaperOrderPreview` object when the evidence gate clears, can optionally validate an Alpaca paper account with sanitized metadata only, and can optionally submit a guarded paper order when all submission guardrails pass. It does not support live Alpaca endpoints or real-money trading.

The preview always includes:

- `broker = "alpaca"`
- `mode = "paper_preview_only"`
- `human_approval_required = true`
- `submit_supported = false`
- `allowed_use = "research_only_not_financial_advice"`

Optional paper account validation supports standard Alpaca paper environment variables:

- `APCA_API_KEY_ID`
- `APCA_API_SECRET_KEY`
- `APCA_API_BASE_URL=https://paper-api.alpaca.markets`

It also supports cookbook aliases:

- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `ALPACA_PAPER_TRADE=true`

If `ALPACA_PAPER_TRADE` is set to anything other than `true`, validation is blocked. If the base URL looks live, validation is blocked. Account IDs, buying power, headers, keys, and raw account payloads are not written to committed assets.

Guarded paper submission adds stricter requirements:

- `ALPACA_PAPER_TRADE=true` is mandatory.
- `APCA_API_BASE_URL` must be exactly `https://paper-api.alpaca.markets`.
- All confirmation flags are mandatory.
- The Evidence Gate must clear before a preview can be submitted.
- The symbol must be in the allowlist.
- The notional must be within the demo cap.
- The request uses a market notional paper order with `time_in_force=day`.
- Runtime output is sanitized before write.

Never use live Alpaca keys with this cookbook.

## Run Tests

```bash
python3 -m unittest discover agentic-finance/tests
```

## Disclaimer

This cookbook is research/demo software. It is not financial advice, does not place live trades, does not support real-money execution, and does not submit by default. Optional Alpaca paper account validation is metadata-only. Optional guarded Alpaca paper submission is simulated-paper-mode only. See `DISCLAIMER.md`.
