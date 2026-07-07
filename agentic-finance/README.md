# Market Foresight Before Trading

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb)

This cookbook shows a finance agent checking a trading idea before it acts. The agent uses PolyBridge to get probabilities for the events behind the idea, then only proceeds if the evidence passes a simple gate. The default demo uses SimBroker, a local pretend broker that records a simulated SPY paper trade. No account, API key, or real trading is required.

The gate can stop the workflow before any simulated paper trade is recorded.

PolyBridge is the probability-and-evidence layer before an agent acts. PolyBridge does not trade, move money, or give financial advice. SimBroker records only local simulated fills after human approval.

## Main Example

- Thesis: US labor market stays resilient through July 2026
- Instrument: SPY
- Direction: long
- Notional: 1000
- Questions:
  1. Will the US lose jobs in July 2026?
  2. Will the US unemployment rate for July 2026 be above 4.3%?
  3. Will the Fed cut rates at its September 2026 meeting?
- Recorded verdict: PROCEED
- Simulated paper trade: BUY SPY, 1000 notional

## Quickstart

One command runs the recorded demo. No setup, no pip, no API key, no account, no real trading. It needs only Python 3.9+ (on Windows, use WSL or Git Bash):

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/agentic-finance
bash demo.sh
```

`demo.sh` runs the Tier 1 Evidence Gate replay, then the Tier 3 SimBroker paper trader, which asks for y/N confirmation before recording a simulated fill.

To run the tiers individually:

```bash
python3 tier1_evidence_gate.py --thesis labor-resilience-jul2026 --replay examples/recorded_run_2026-07-04.json
python3 tier3_paper_trader.py --thesis labor-resilience-jul2026 --replay examples/recorded_run_2026-07-04.json
```

Expected preview:

```text
VERDICT: PROCEED

PAPER ORDER PREVIEW
BROKER: SimBroker
SYMBOL: SPY
SIDE: BUY
NOTIONAL: $1,000

Confirm simulated paper trade? y/N
```

If you enter `y`, the runner appends a simulated fill and audit event. Any other input records `human_declined` and writes no simulated fill.

Expected runtime outputs:

- `outputs/decision-memo.md`
- `outputs/decisions.jsonl`
- `outputs/paper_portfolio.jsonl`

Runtime outputs are ignored by git.

## Live Mode And Custom Theses

The recorded demo needs nothing beyond stock Python. Live mode asks PolyBridge fresh and uses one optional dependency. Install it once with:

```bash
bash setup.sh
```

Run the shipped thesis live by dropping the --replay flag:

```bash
python3 tier1_evidence_gate.py --thesis labor-resilience-jul2026
python3 tier3_paper_trader.py --thesis labor-resilience-jul2026
```

To run your own idea, add a thesis to examples/sample_theses.json with a new thesis_id and run it the same way. Custom theses always run live; no recorded data is needed.

Live answers take 30 to 50 seconds per question. Live mode remains read-only evidence fetching; it does not add any real trading path. Tier 3 still previews and asks y/N before any simulated fill.

## SimBroker

SimBroker is intentionally small:

- no signup
- no API keys
- no network broker dependency
- no market data
- no prices or profit/loss
- simulated fills only
- human approval required before fill recording

The CLI runner writes simulated fills to `outputs/paper_portfolio.jsonl`.

The MCPB package lives in `simbroker-mcpb/` and exposes SimBroker as a local demo paper broker for agent workflows. Build it with:

```bash
python3 simbroker-mcpb/build.py
```

The generated bundle path is:

```text
simbroker-mcpb/dist/simbroker-demo-paper-broker.mcpb
```

The bundle file is intended as a release artifact and is not committed.

## Notebook

Open the notebook from the badge above or run it locally:

```bash
jupyter notebook agentic-finance.ipynb
```

The notebook follows the same offline story: labor-resilience replay, Evidence Gate memo, and SimBroker simulated fill.

## Safety

This cookbook is research/demo software, not financial advice. It does not place real trades, move money, connect to brokerage accounts, or recommend market action. The recorded replay and sample assets are sanitized examples for software review.
