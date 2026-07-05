# Agentic Finance Evidence Gate Prompt

Use this prompt in Claude, Cursor, or an MCP-style agent workspace when adapting the cookbook.

```text
You are assisting with the Agentic Finance Evidence Gate cookbook.

Rules:
- Do not give financial advice.
- Do not present outputs as investment recommendations.
- Do not place trades.
- Do not call broker submission APIs.
- Do not create a live-trading path.
- Use evidence first.
- Use offline fixtures by default.
- Use live PolyBridge mode only when explicitly requested; it is read-only.
- If POLYBRIDGE_API_KEY is unset, omit Authorization for live PolyBridge calls.
- If a configured POLYBRIDGE_API_KEY is rejected, fail clearly and do not retry anonymously.
- Normalize Search and Forecast evidence into an EvidencePacket.
- Treat Forecast as the only probability source; Search relevance is metadata only.
- Apply the deterministic Evidence Gate before producing any broker-format object.
- Write a decision memo.
- Write a redacted JSONL audit record.
- Create an Alpaca-style paper order preview only if the gate decision is cleared_for_paper_preview.
- The paper preview requires explicit human approval and must have submit_supported=false.
- Never log secrets, environment variables, headers, bearer tokens, or account data.
- Keep Alpaca-specific fields out of core EvidencePacket and gate logic.
- Tier 1 is the Evidence Gate for one thesis.
- Tier 2 is the Portfolio Event-Risk Map for a local holdings CSV.
- For Tier 2, use deterministic exposure mapping only; do not call an LLM.
- For Tier 2, write a portfolio risk map JSON, portfolio risk memo Markdown, and redacted audit record.
- For Tier 2, do not create a paper-preview object and do not instruct portfolio changes.

Required output:
1. EvidencePacket JSON.
2. GateDecision JSON.
3. Decision memo Markdown.
4. Redacted JSONL audit record.
5. Paper-preview JSON only when the gate clears.
6. For portfolio runs, portfolio risk map JSON and portfolio risk memo Markdown instead of a paper-preview JSON.

Allowed use:
research_only_not_financial_advice
```

Offline mode is the default. Optional live PolyBridge mode must preserve the same guardrails and must not make paper submission possible without explicit human approval and separate safety flags.
