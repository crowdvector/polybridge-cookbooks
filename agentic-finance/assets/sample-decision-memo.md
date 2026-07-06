# Market Foresight Evidence Gate Memo

## Thesis
US labor market stays resilient through July 2026

## Scenario
- Thesis ID: `labor-resilience-jul2026`
- As of: `2026-07-04`
- Instrument: `SPY`
- Direction: `long`
- Notional: `$1,000.00`

## Verdict
`PROCEED`

## Gate Summary
- Weighted support: 3.0
- Direct-evidence legs: 3
- Full-weight contradictions: 0
- Confidence scalar used by gate: no

## Leg Classifications
- Will the US lose jobs in July 2026? -> probability 12%, threshold 25% when `NO`, profile `direct_mixed`, classification `SUPPORTS`, weight 1.0.
- Will the US unemployment rate for July 2026 be above 4.3%? -> probability 28%, threshold 40% when `NO`, profile `direct_only`, classification `SUPPORTS`, weight 1.0.
- Will the Fed cut rates at its September 2026 meeting? -> probability 6%, threshold 30% when `NO`, profile `direct_mixed`, classification `SUPPORTS`, weight 1.0.

## Reasons
- Weighted support, direct-evidence count, and contradiction checks passed.

## Allowed Use
`research_only_not_financial_advice`

## Disclaimer
This memo is research/demo software output, not financial advice. It does not place real trades,
does not support real-money execution, and permits only a local simulated paper-trade review by
a human when the gate says `PROCEED`.
