# Agentic Finance Evidence Gate

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb)

> Safety banner: this cookbook is research/demo software, not financial advice. Offline mode is the default. Optional live PolyBridge evidence mode is read-only, and no tier places trades or calls broker APIs.

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

## What This Is Not

- Not financial advice.
- Not an investment recommendation system.
- Not a trading bot.
- Not connected to live PolyBridge APIs unless `--live-polybridge` is explicitly selected.
- Not connected to Alpaca or any broker API.
- Not capable of submitting orders.
- Not a real-money workflow.
- Not a portfolio action engine.

## Quickstart

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/agentic-finance
bash setup.sh
python3 evidence_gate.py --offline
```

From the repository root:

```bash
python3 agentic-finance/evidence_gate.py --offline
```

Run the portfolio tier from the repository root:

```bash
python3 agentic-finance/run_portfolio_risk_map.py --offline --holdings agentic-finance/examples/sample_holdings.csv
```

Run the same tier from the cookbook folder:

```bash
python3 run_portfolio_risk_map.py --offline --holdings examples/sample_holdings.csv
```

Optional live PolyBridge mode is available but is never the default:

```bash
python3 agentic-finance/evidence_gate.py --live-polybridge
```

If `POLYBRIDGE_API_KEY` is unset, live mode omits the `Authorization` header entirely and uses anonymous PolyBridge limits. If a configured key is rejected with `401` or `403`, the run fails clearly and does not retry anonymously. Live mode is still read-only and is not financial advice.

## Files

- `evidence_gate.py` is the Tier 1 runnable entry point.
- `run_portfolio_risk_map.py` is the Tier 2 runnable entry point.
- `agentic_finance/` contains the offline workflow package and optional live PolyBridge adapter.
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

## Alpaca-Style Preview

`agentic_finance/brokers/alpaca.py` does not import the Alpaca SDK and does not define any submission function. It only creates a local `PaperOrderPreview` object when the evidence gate clears.

The preview always includes:

- `broker = "alpaca"`
- `mode = "paper_preview_only"`
- `human_approval_required = true`
- `submit_supported = false`
- `allowed_use = "research_only_not_financial_advice"`

## Run Tests

```bash
python3 -m unittest discover agentic-finance/tests
```

## Disclaimer

This cookbook is research/demo software. It is not financial advice, does not place trades, does not support real-money execution, and does not connect to live broker APIs. See `DISCLAIMER.md`.
