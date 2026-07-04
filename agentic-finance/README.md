# Agentic Finance Evidence Gate

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb)

> Safety banner: this cookbook is research/demo software, not financial advice. Offline mode is the default; optional live PolyBridge mode is read-only, paper-preview-only, and does not place trades or call broker APIs.

## Quick Links

- Colab: https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb
- GitHub folder: https://github.com/crowdvector/polybridge-cookbooks/tree/main/agentic-finance
- Disclaimer: `DISCLAIMER.md`

## What This Is

This cookbook shows a broker-neutral pre-action evidence workflow for financial agents:

```text
financial thesis
  -> offline fixtures or optional live PolyBridge Search/Forecast evidence
  -> normalized EvidencePacket
  -> deterministic Evidence Gate
  -> decision memo
  -> redacted JSONL audit log
  -> optional Alpaca-style paper order preview object
```

The demo is designed for teams evaluating agentic finance guardrails. It uses fake, sanitized fixtures by default to model how evidence can be normalized before any broker-format object is created. Optional live PolyBridge mode fetches Search and Forecast evidence, remains read-only, and still writes only local review artifacts.

## What This Is Not

- Not financial advice.
- Not an investment recommendation system.
- Not a trading bot.
- Not connected to live PolyBridge APIs unless `--live-polybridge` is explicitly selected.
- Not connected to Alpaca or any broker API.
- Not capable of submitting orders.
- Not a real-money workflow.

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

Optional live PolyBridge mode is available but is never the default:

```bash
python3 agentic-finance/evidence_gate.py --live-polybridge
```

If `POLYBRIDGE_API_KEY` is unset, live mode omits the `Authorization` header entirely and uses anonymous PolyBridge limits. If a configured key is rejected with `401` or `403`, the run fails clearly and does not retry anonymously. Live mode is still read-only and is not financial advice.

## Files

- `evidence_gate.py` is the runnable entry point.
- `agentic_finance/` contains the offline workflow package and optional live PolyBridge adapter.
- `fixtures/` contains sanitized PolyBridge-shaped Search and Forecast fixtures plus the thesis.
- `assets/` contains sanitized committed sample outputs.
- `outputs/` is the default runtime output directory and is ignored by git.
- `tests/` contains stdlib `unittest` coverage.

## Output Files

Runtime outputs are written to `agentic-finance/outputs/` by default:

- `evidence-packet.json`
- `decision-memo.md`
- `audit-log.jsonl`
- `alpaca-order-preview.json`, only when the evidence gate clears

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

`--live-polybridge` uses `fixtures/thesis.json` for the thesis, Search query, and Forecast question, then fetches live Search and Forecast evidence. Search relevance is stored only as search metadata; Forecast remains the only probability source. Raw PolyBridge responses are normalized into `EvidencePacket` before gate evaluation.

This mode does not call Alpaca, does not submit broker orders, and does not create a real-money trading path.

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
