# Agent prompt: long/short MCP cookbook

Use Claude with the PolyBridge MCP extension to evaluate a directional long/short thesis.

Requirements:
- Use PolyBridge MCP tools only for market intelligence.
- Keep execution dry-run by default.
- Do not place live trades automatically.
- If order JSON is generated, clearly label it as review-only.
- Include a note that outputs are market-implied snapshots, not financial advice.
