# Long/short portfolio from prediction market intelligence

Use PolyBridge MCP with Claude to turn market-implied probabilities into a dry-run long/short portfolio plan.

## What this cookbook will build

A Claude/MCP workflow that:

- starts with a human thesis
- queries PolyBridge Forecast through MCP
- compares prediction-market evidence to the thesis
- produces a sized dry-run position table
- optionally produces order JSON for review

## Safety note

This cookbook must stay dry-run by default. It should not place live orders without explicit user review and confirmation.

## Files

- `longshort-portfolio.ipynb` - optional notebook, coming later.
- `setup.sh` - local setup.
- `PROMPT.md` - Claude/MCP prompt.
- `assets/` - screenshots and generated outputs.

## Status

Draft skeleton. The MCP prompt and dry-run example output will be added in the next pass.
