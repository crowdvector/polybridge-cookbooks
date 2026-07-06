# Disclaimer

This cookbook is research and demonstration software.

It is not financial advice, investment advice, trading advice, tax advice, legal advice, or a recommendation to take any market action. The included theses, evidence fixtures, probabilities, memos, audit logs, and paper-preview objects are fake or sanitized examples for software-engineering review. The primary recorded replay, `labor-resilience-jul2026`, demonstrates a deterministic gate that may prepare an SPY paper preview; it is not a recommendation, advice, or live-trading workflow.

Offline workflows do not call live PolyBridge APIs, do not call Alpaca APIs, do not connect to any broker, do not access accounts, and do not submit orders. The Alpaca-style preview object is a local paper-preview data structure only. It has `submit_supported=false` and requires explicit human approval.

Optional Alpaca paper account validation and optional guarded Alpaca paper submission are explicit commands. They require paper credentials and must use `https://paper-api.alpaca.markets`. Guarded paper submission requires all confirmation flags, a cleared Evidence Gate, `ALPACA_PAPER_TRADE=true`, an allowlisted symbol, and the demo notional cap. This is simulated paper trading only. Do not use live Alpaca keys.

Do not use this cookbook to make real-money decisions. Any production financial workflow requires independent compliance review, security review, broker integration review, model-risk review, monitoring, and human authorization controls.
