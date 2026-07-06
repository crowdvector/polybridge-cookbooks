# SimBroker (Demo Paper Broker)

SimBroker is a deliberately naive pretend broker for the PolyBridge agentic-finance cookbook. It records simulated fills to local JSONL files. It has no market connection, no credentials, no real trading, and no financial-advice role.

Use it alongside the PolyBridge read-only evidence tools when an agent needs a local paper-trade target after evidence has been checked.

Current version: `0.2.0`.

## Install

Download the released bundle:

```text
https://github.com/crowdvector/polybridge-cookbooks/releases/download/simbroker-mcpb-v0.2.0/simbroker-demo-paper-broker.mcpb
```

Or build it locally:

```bash
python build.py
```

The generated file is:

```text
dist/simbroker-demo-paper-broker.mcpb
```

Install the bundle in Claude Desktop using the normal MCPB flow, such as dragging or double-clicking the bundle if your desktop build supports it.

## Data

SimBroker uses `SIMBROKER_DATA_DIR` when set. Otherwise it writes under `~/.simbroker/`.

Each account has:

- `paper_portfolio.jsonl`
- `orders.jsonl`
- `account.json`

The default account always exists. State is derived by replaying JSONL records. Starting cash is `100000` simulated dollars.

## Starter Position

Every account begins with a simulated $1,000 SPY position tagged:

```text
starter position: labor-resilience thesis (see cookbook)
```

This gives the cookbook demo a position to add to, exit, or hold. Resetting an account restores the starter position. This is a simulated record only; there is no market connection, no real trading, and no financial advice.

After seeding, a fresh account shows `$99,000.00` cash and a `SPY $1,000.00` cost-basis position from the `sim_starter` fill.

## Tools

- `create_account(name, max_order_usd=None)`
- `list_accounts()`
- `get_account(account="default")`
- `preview_order(symbol, side, notional_usd, account="default", reason=None)`
- `place_simulated_order(preview_id, user_approved)`
- `get_portfolio(account="default")`
- `reset_account(account="default")`

Every tool response ends with:

```text
Simulated. No real trading. Not financial advice.
```

## Limits

- Symbol must be uppercase and at most 5 characters.
- Side must be `buy` or `sell`.
- Notional must be between `1` and `100000`.
- Account-level `max_order_usd` is enforced when configured.
- Buys require available simulated cash.
- Sells require an existing cost-basis position.
- Preview is required before placement.
- Placement requires `user_approved=true`.
- A preview can be used only once.
- No prices, quotes, market data, profit/loss, partial fills, short selling, or live execution are supported.

Use `reset_account` to archive JSONL files with a timestamp suffix and reset simulated cash.
