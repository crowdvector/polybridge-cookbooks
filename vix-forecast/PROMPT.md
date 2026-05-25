# Agent prompt: VIX forecast cookbook

Build or update a PolyBridge cookbook that forecasts VIX and related market stress questions.

Requirements:
- Use `POLYBRIDGE_API_KEY` from the environment.
- Do not print or commit API keys.
- Call `POST https://api.polybridge.ai/v1/forecast`.
- Handle 429/503 with retry/backoff and honor `Retry-After` when present.
- Handle missing `markets_used` probabilities safely.
- Save generated output to `assets/`.
- Add a note that outputs are market-implied snapshots, not financial advice.
