# Agentic Finance Evidence Gate Memo

## Thesis
A research agent is evaluating whether evidence is strong enough to prepare a paper-only preview for a small AAPL exposure adjustment after a margin-resilience thesis.

## Forecast Question
Will Apple report gross margin above 45% for fiscal Q4 2026?

## Evidence Summary
- Probability: 66.0%
- Confidence: 72.0%
- Confidence interval: 56.0% to 78.0%
- Evidence profile: direct_and_proxy_market_evidence
- Quality flags: offline_fixture, sanitized_fixture

## Gate Decision
`cleared_for_paper_preview`

## Reasons
- Evidence meets the configured confidence, interval, and source-market thresholds.
- The result permits only a local paper-preview object for human review.

## Source Markets
- offline_fixture_market: Offline fixture: Apple gross margin above 45% for fiscal Q4 2026? (https://example.invalid/markets/apple-gross-margin-q4-2026); probability 68.0%; direct.
- offline_fixture_market: Offline fixture: Apple fiscal Q4 2026 earnings quality above baseline? (https://example.invalid/markets/apple-earnings-quality-q4-2026); probability 61.0%; proxy.

## Allowed Use
`research_only_not_financial_advice`

## Next Step
Create a paper-preview object for explicit human review.

## Disclaimer
This memo is research/demo software output, not financial advice. It does not place orders, does not support real-money execution, and permits only paper-preview review by a human.
