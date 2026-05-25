# Agent prompt: portfolio allocation cookbook

Build or update a PolyBridge cookbook that uses Forecast probabilities in an asset allocation workflow.

Requirements:
- Use `POLYBRIDGE_API_KEY` from the environment.
- Do not print or commit API keys.
- Call `POST https://api.polybridge.ai/v1/forecast`.
- Use retry/backoff for 429/503 and honor `Retry-After`.
- Save generated charts and snapshot outputs to `assets/`.
- Keep all outputs framed as market-implied snapshots, not financial advice.
