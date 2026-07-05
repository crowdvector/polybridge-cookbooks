# Agentic Finance Evidence Gate

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb)

> Safety banner: this cookbook is research/demo software, not financial advice. Offline mode is the default. Optional live PolyBridge evidence mode is read-only. Optional Alpaca paper account validation is explicit, paper-only, and metadata-only. No tier places trades or submits orders.

## Quick Links

- Colab: https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb
- GitHub folder: https://github.com/crowdvector/polybridge-cookbooks/tree/main/agentic-finance
- Disclaimer: `DISCLAIMER.md`

## What This Is

This cookbook has two read-only research tiers for financial-agent guardrails.

Tier 1 is the Evidence Gate:

```text
financial thesis
  -> offline fixtures or optional live PolyBridge Search/Forecast evidence
  -> normalized EvidencePacket
  -> deterministic Evidence Gate
  -> decision memo
  -> redacted JSONL audit log
  -> optional Alpaca-style paper order preview object
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

The cookbook also includes an optional Alpaca paper validation adapter. Preview-only mode still requires no credentials and does not call Alpaca. Paper account validation must be requested explicitly, requires paper credentials, validates the paper endpoint, fetches only sanitized account metadata, and does not submit orders.

## What This Is Not

- Not financial advice.
- Not an investment recommendation system.
- Not a trading bot.
- Not connected to live PolyBridge APIs unless `--live-polybridge` is explicitly selected.
- Not connected to Alpaca unless the explicit paper account validation command is run.
- Not capable of submitting orders.
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
python3 evidence_gate.py --offline
```

From the repository root:

```bash
python3 agentic-finance/evidence_gate.py --offline
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

This runs the offline Evidence Gate and writes a local Alpaca-style paper preview if the gate clears. It requires no Alpaca credentials and does not call Alpaca:

```bash
python3 agentic-finance/run_alpaca_paper_check.py --preview-only
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

### Open In Colab

Use the badge at the top of this README or open:

```text
https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb
```

The notebook runs offline fixtures by default, does not require API keys, and previews generated local artifacts.

### Prompt Pack

Use `PROMPT.md` as the prompt index. Copy-paste workflow prompts live in `prompts/`.

## Files

- `evidence_gate.py` is the Tier 1 runnable entry point.
- `run_portfolio_risk_map.py` is the Tier 2 runnable entry point.
- `run_alpaca_paper_check.py` runs preview-only mode or explicit Alpaca paper account validation.
- `agentic_finance/` contains the offline workflow package and optional live PolyBridge adapter.
- `prompts/` contains copy-paste prompts for Claude, Cursor, MCP-style agents, broker-neutral workflows, custom agents, and portfolio review agents.
- `fixtures/` contains sanitized PolyBridge-shaped Search and Forecast fixtures plus the thesis.
- `examples/sample_holdings.csv` is a local, fake portfolio input for the portfolio tier.
- `assets/` contains sanitized committed sample outputs.
- `outputs/` is the default runtime output directory and is ignored by git.
- `tests/` contains stdlib `unittest` coverage.

## Output Files

Runtime outputs are written to `agentic-finance/outputs/` by default:

- `evidence-packet.json`
- `decision-memo.md`
- `audit-log.jsonl`
- `alpaca-order-preview.json`, only when the evidence gate clears
- `alpaca-paper-account-check.json`, only when explicit paper account validation is requested
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

Redaction covers authorization headers, bearer tokens, known PolyBridge and Alpaca env names, and obvious token-like strings.

## Alpaca Paper Preview And Account Check

`agentic_finance/brokers/alpaca.py` does not import the Alpaca SDK. It creates a local `PaperOrderPreview` object when the evidence gate clears and can optionally validate an Alpaca paper account with sanitized metadata only. It does not define any submission function.

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

## Run Tests

```bash
python3 -m unittest discover agentic-finance/tests
```

## Disclaimer

This cookbook is research/demo software. It is not financial advice, does not place trades, does not support real-money execution, and does not submit orders. Optional Alpaca paper account validation is metadata-only and simulated-paper-mode only. See `DISCLAIMER.md`.
