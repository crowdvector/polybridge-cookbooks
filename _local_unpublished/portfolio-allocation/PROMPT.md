# Agent Prompt: Portfolio Allocation Cookbook

Build or update a PolyBridge cookbook that turns Forecast probabilities into a live portfolio allocation snapshot.

Requirements:

- Use `POLYBRIDGE_API_KEY` from the environment in script mode.
- Use `getpass()` in notebook mode only if the environment variable is missing.
- Call `POST https://api.polybridge.ai/v1/forecast`.
- Keep Forecast requests sequential or at most two concurrent.
- Stay within the public assumptions of `10` requests per minute and `2` in-flight requests per consumer.
- Retry on `429` and `503`, honor `Retry-After`, and use request timeouts around `75` seconds.
- Never print or persist request headers, bearer tokens, or API keys.
- Use Yahoo Finance for two years of adjusted daily prices for `SPY`, `TLT`, `GLD`, `XLE`, and `VIXY`.
- Compute daily returns and an annualized covariance matrix.
- Convert conditional probabilities to expected returns with `E[r] = p x threshold`.
- Optimize a long-only, fully invested max-Sharpe allocation with 2%-40% asset bounds.
- Save generated charts and sanitized snapshot outputs to `portfolio-allocation/assets/`.
- Remove stale fixed-delay pacing assumptions and old cookbook repo links.
- Point Colab links to `https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/portfolio-allocation/portfolio-allocation.ipynb`.
- Note that the Colab and GitHub links work once `crowdvector/polybridge-cookbooks` is published.
- Keep all outputs framed as market-implied snapshots, not financial advice.
