# VIX forecast cookbook prompt

Build or adapt the PolyBridge VIX cookbook in `vix-forecast/` without publishing article content.

## Requirements

- Call `POST https://api.polybridge.ai/v1/forecast` without Authorization.
- If auth fails with `401` or `403`, stop and fix or remove the configured key. Do not silently retry anonymously after auth failure.
- Never print, persist, or commit API keys, bearer tokens, headers, or `.env` contents.
- Use a two-month traditional-index horizon: approximately 42 trading days. Forecast question strings should say `next 42 trading days`; prose may say `next 2 months (~42 trading days)`.
- Use five total forecast calls: one headline VIX signal and four highlighted macro drivers.
- Use this headline question exactly:
  - Will VIX close above 30 at least once in the next 42 trading days?
- Use these driver questions exactly:
  - Will crude oil settle above $90 in June 2026?
  - Will SPX draw down more than 10% at any point in the next 42 trading days?
  - Will gold rise more than 10% from its current price at any point in the next 42 trading days?
  - Will the Strait of Hormuz reopen to regular traffic by June 30, 2026?
- Keep live calls sequential.
- Use a safe timeout around 75 seconds.
- Retry on `429` and `503`, and honor `Retry-After` when it is present.
- Do not reintroduce the old fixed-delay rate-limit assumption.
- Handle missing fields safely:
  - `markets_used` may be missing or empty.
  - Market probability may be missing.
  - URLs may appear as `platform_url`, `platformUrl`, or `url`.
  - Market question labels may appear as `question`, `title`, or `name`.
  - `confidence_interval` may be missing.
  - `reasoning` may be missing.
- Public API docs and examples should use `markets_used` and `confidence_interval`; do not present `source_market_count` or `probability_range` as direct top-level fields from `POST /v1/forecast`.
- A sanitized cookbook snapshot may include `source_market_count` only when derived from `len(markets_used)`.
- Save sanitized outputs to:
  - `assets/snapshot.json`
  - `assets/market-stress-monitor.png`
- `snapshot.json` must not contain headers, authorization data, or secrets.
- The PNG should use a dark theme and remain readable as a website hero image.
- Use the Colab link:
  - `https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/vix-forecast/vix-forecast.ipynb`
- Include a clear note that the results are market-implied snapshots and can change as source markets update.
