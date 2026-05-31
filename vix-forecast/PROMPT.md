# Agent prompt: VIX forecast cookbook

Build or adapt the PolyBridge VIX cookbook in `vix-forecast/` without publishing article content.

Requirements:
- Use `POLYBRIDGE_API_KEY` from the environment in script mode.
- In notebook mode, check the environment first and fall back to `getpass()` only if the variable is missing.
- Call `POST https://api.polybridge.ai/v1/forecast` with `Authorization: Bearer <API key>`.
- Never print, persist, or commit API keys, bearer tokens, headers, or `.env` contents.
- Use these questions exactly:
  - Will VIX close above 30 in the next 42 days?
  - Will crude oil settle above $90 in June 2026?
  - Will SPX draw down more than 10% in the next 42 days?
  - Will gold rise more than 10% in the next 42 days?
  - Will the Strait of Hormuz reopen to regular traffic by June 30, 2026?
- Keep live calls sequential or at most two concurrent.
- Use a safe timeout around 75 seconds.
- Retry on `429` and `503`, and honor `Retry-After` when it is present.
- Do not reintroduce the old fixed-delay rate-limit assumption.
- Handle missing fields safely:
  - `markets_used` may be missing or empty
  - market probability may be missing
  - URLs may appear as `platform_url`, `platformUrl`, or `url`
  - market question labels may appear as `question`, `title`, or `name`
  - `confidence_interval` or `probability_range` may be missing
  - `reasoning` may be missing
- Save sanitized outputs to:
  - `assets/snapshot.json`
  - `assets/market-stress-monitor.png`
- `snapshot.json` must not contain headers, authorization data, or secrets.
- The PNG should use a dark theme and remain readable as a website hero image.
- Use the Colab link:
  - `https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/vix-forecast/vix-forecast.ipynb`
- Mention that the Colab link will work after the repo exists and has been pushed.
- Include a clear note that the results are market-implied snapshots and can change as source markets update.
