# Monthly portfolio and research report — 2027-12-01 — **SYNTHETIC DEMO DATA**

No orders are placed and no money is moved by this system. Amounts are what the user recorded.

## Budget (budget_policy_v1; the annual limit is a ceiling, not a target)

* Budget period: P2: 2027-11-05 → 2028-11-05 (exclusive), anchor 2026-11-05
* Annual committed: $0.00 of $12,000.00 (funded in period $0.00 + active reservations $0.00); remaining $12,000.00
* Per-issuer lifetime committed (limit $1,200 each; does not reset after sales, losses or write-offs):

| issuer_key | committed | remaining |
|---|---|---|
| CIK9000001 | $508.50 | $691.50 |
| CIK9000002 | $1,500.00 | $-300.00 |

## Approvals and reservations

| approval_id | offering_id | issuer_key | amount | fee | fee_basis | status | expires_utc | reservation_active |
|---|---|---|---|---|---|---|---|---|
| 1 | DEMO-A | CIK9000001 | $500.00 | $10.00 | upper_bound | blocked | 2026-11-16T15:00:00+00:00 | False |
| 2 | DEMO-A | CIK9000001 | $500.00 | $10.00 | upper_bound | executable | 2026-11-16T15:00:00+00:00 | False |
| 3 | DEMO-B | CIK9000002 | $900.00 | $0.00 | confirmed | executable | 2026-11-16T15:00:00+00:00 | False |
| 4 | DEMO-B2 | CIK9000002 | $400.00 | $0.00 | confirmed | blocked | 2026-11-16T15:00:00+00:00 | False |

## Positions (funded cost, refunds, distributions and holdings kept separate)

| position_id | status | funded_cost | refunds | distributions | sale_proceeds_net | holding | realized_note | flags |
|---|---|---|---|---|---|---|---|---|
| POS-DEMO-A-crowd_safe | submitted | $508.50 | $0.00 | $0.00 | $0.00 |  | not computed: position open, incomplete, or fully refunded (conversion is not cash) |  |
| POS-DEMO-A-security | finalized | $0.00 | $0.00 | $25.00 | $0.00 |  | not computed: position open, incomplete, or fully refunded (conversion is not cash) |  |
| POS-DEMO-B-crowd_safe | submitted | $1,500.00 | $0.00 | $0.00 | $0.00 |  | not computed: position open, incomplete, or fully refunded (conversion is not cash) | NO_APPROVAL;OUT_OF_POLICY:issuer_limit |

## Policy flags on recorded transactions (recorded truthfully, never altered)

| event_id | event_type | offering_id | effective_date | policy_flags |
|---|---|---|---|---|
| 6 | investment_submitted | DEMO-B | 2026-11-25 | OUT_OF_POLICY:issuer_limit;NO_APPROVAL |

## Material new filings/contract events (last 30 days)

_none_

## Forecasts

_none_

Unknown outcomes are never scored as false. Probabilities are uncalibrated model judgments.

## Analyst versions and evaluation

```json
{}
```

_none_

## User time and operations

* User time recorded (30 days): 0 minutes (budget: about 6 h/week).
_none_
