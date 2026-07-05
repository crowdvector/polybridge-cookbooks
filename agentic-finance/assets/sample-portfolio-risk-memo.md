# Portfolio Event-Risk Map Memo

## Scope
This read-only memo summarizes event-risk evidence for a local holdings CSV. It is research/demo software output, does not place orders, does not support execution, and does not instruct portfolio changes.

## Portfolio Snapshot
- Holdings: 5
- Total notional: $13,350.00

- SPY: SPDR S&P 500 ETF Trust; sector `broad_equity`; notional $6,500.00.
- QQQ: Invesco QQQ Trust; sector `technology`; notional $2,800.00.
- TLT: iShares 20+ Year Treasury Bond ETF; sector `rates`; notional $1,800.00.
- XLE: Energy Select Sector SPDR Fund; sector `energy`; notional $1,300.00.
- GLD: SPDR Gold Shares; sector `gold`; notional $950.00.

## Deterministic Exposure Mapping
- Rates and inflation sensitivity: SPY, QQQ, TLT, GLD; drivers: rates, inflation, Fed policy, Treasury volatility, dollar/rates; portfolio weight 90.3%.
- Equity volatility and geopolitical risk: SPY, QQQ, GLD; drivers: volatility, tariff/geopolitical risk, geopolitical escalation; portfolio weight 76.8%.
- AI regulation and technology policy: QQQ; drivers: AI regulation, China/Taiwan, export controls, rates; portfolio weight 21.0%.
- Energy and shipping disruption: XLE; drivers: oil shock, Middle East escalation, sanctions, shipping disruption; portfolio weight 9.7%.

## Evidence Gate Results
- Rates and inflation sensitivity: probability 62.0%, confidence 70.0%, gate `cleared_for_paper_preview`, risk band `elevated_event_risk`.
- Equity volatility and geopolitical risk: probability 54.0%, confidence 67.0%, gate `watchlist_only`, risk band `monitor`.
- AI regulation and technology policy: probability 57.0%, confidence 66.0%, gate `cleared_for_paper_preview`, risk band `elevated_event_risk`.
- Energy and shipping disruption: probability 58.0%, confidence 68.0%, gate `cleared_for_paper_preview`, risk band `elevated_event_risk`.

## Methodology
- Holdings are mapped with deterministic local rules.
- Search relevance is retained only as metadata.
- Forecast output is the only probability source.
- Gate logic receives normalized EvidencePackets, not raw PolyBridge responses.

## Guardrails
- Read-only portfolio workflow.
- Local holdings CSV only.
- No broker connection.
- No order submission.
- No real-money execution path.
