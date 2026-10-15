# SYNTHETIC approval/ledger demonstration (isolated demo database)

All offerings, amounts and confirmations are fictional. The live pilot database is not touched.

### 2026-11-02 — approval attempted BEFORE policy acknowledgment (must be blocked)

```json
{
 "approval_id": 1,
 "status": "blocked",
 "expires_utc": "2026-11-16T15:00:00+00:00",
 "blockers": [
  "screening policy not acknowledged (run `ack-policy`)",
  "issuer aggregation not confirmed (stored key CIK9000001, confirmed=False; run `confirm-issuer`)"
 ],
 "budget": {
  "annual_ok": true,
  "issuer_ok": true,
  "ok": true,
  "period": "pre_start",
  "annual_used_before": 0,
  "annual_after": 51000,
  "annual_limit": 1200000,
  "issuer_used_before": 0,
  "issuer_after": 51000,
  "issuer_limit": 120000
 }
}
```

### 2026-11-02 — user acknowledges screening policy

```json
1
```

### 2026-11-02 — approve $500 + $10 fee upper bound in DEMO-A (pre-start reservation)

```json
{
 "approval_id": 2,
 "status": "executable",
 "expires_utc": "2026-11-16T15:00:00+00:00",
 "blockers": [],
 "budget": {
  "annual_ok": true,
  "issuer_ok": true,
  "ok": true,
  "period": "pre_start",
  "annual_used_before": 0,
  "annual_after": 51000,
  "annual_limit": 1200000,
  "issuer_used_before": 0,
  "issuer_after": 51000,
  "issuer_limit": 120000
 }
}
```

### 2026-11-02 — approve $900 in DEMO-B

```json
{
 "approval_id": 3,
 "status": "executable",
 "expires_utc": "2026-11-16T15:00:00+00:00",
 "blockers": [],
 "budget": {
  "annual_ok": true,
  "issuer_ok": true,
  "ok": true,
  "period": "pre_start",
  "annual_used_before": 51000,
  "annual_after": 141000,
  "annual_limit": 1200000,
  "issuer_used_before": 0,
  "issuer_after": 90000,
  "issuer_limit": 120000
 }
}
```

### 2026-11-02 — approve $400 in the SPV of the same issuer (shares Beta's $1,200 limit: must be blocked)

```json
{
 "approval_id": 4,
 "status": "blocked",
 "expires_utc": "2026-11-16T15:00:00+00:00",
 "blockers": [
  "budget limit would be exceeded (limits cannot be overridden at approval)"
 ],
 "budget": {
  "annual_ok": true,
  "issuer_ok": false,
  "ok": false,
  "period": "pre_start",
  "annual_used_before": 141000,
  "annual_after": 181000,
  "annual_limit": 1200000,
  "issuer_used_before": 90000,
  "issuer_after": 130000,
  "issuer_limit": 120000
 }
}
```

### 2026-11-02 — budget after two reservations

```json
{
 "as_of": "2026-11-02",
 "anchor": null,
 "period_label": "pre_start",
 "period_start": null,
 "period_end_exclusive": null,
 "annual_funded_cents": 0,
 "active_reservation_cents": 141000,
 "annual_used_cents": 141000,
 "annual_limit_cents": 1200000,
 "issuer_used_cents": {
  "CIK9000001": 51000,
  "CIK9000002": 90000
 },
 "issuer_limit_cents": 120000,
 "active_reservations": "omitted"
}
```

### 2026-11-05 — user invested manually on the platform; confirmation imported (starts the annual clock)

```json
{
 "event_id": 3,
 "duplicate": false,
 "flags": ""
}
```

### 2026-11-05 — same confirmation imported twice (idempotent)

```json
{
 "event_id": 3,
 "duplicate": true,
 "flags": ""
}
```

### 2026-11-05 — finalized

```json
{
 "event_id": 4,
 "duplicate": false,
 "flags": ""
}
```

### 2026-11-05 — budget: reservation consumed, no double count

```json
{
 "as_of": "2026-11-05",
 "anchor": "2026-11-05",
 "period_label": "P1",
 "period_start": "2026-11-05",
 "period_end_exclusive": "2027-11-05",
 "annual_funded_cents": 50850,
 "active_reservation_cents": 90000,
 "annual_used_cents": 140850,
 "annual_limit_cents": 1200000,
 "issuer_used_cents": {
  "CIK9000001": 50850,
  "CIK9000002": 90000
 },
 "issuer_limit_cents": 120000
}
```

### 2026-11-25 — DEMO-B reservation canceled by the user (released)

```json
5
```

### 2026-11-25 — out-of-policy actual transaction (no approval, above issuer limit) recorded truthfully and flagged

```json
{
 "event_id": 6,
 "duplicate": false,
 "flags": "OUT_OF_POLICY:issuer_limit;NO_APPROVAL"
}
```

### 2027-12-01 — cash distribution (does not restore budget)

```json
{
 "event_id": 7,
 "duplicate": false,
 "flags": ""
}
```

### 2027-12-01 — budget in the second period (P2 starts 2027-11-05)

```json
{
 "as_of": "2027-12-01",
 "anchor": "2026-11-05",
 "period_label": "P2",
 "period_start": "2027-11-05",
 "period_end_exclusive": "2028-11-05",
 "annual_funded_cents": 0,
 "active_reservation_cents": 0,
 "annual_used_cents": 0,
 "annual_limit_cents": 1200000,
 "issuer_used_cents": {
  "CIK9000001": 50850,
  "CIK9000002": 150000
 },
 "issuer_limit_cents": 120000
}
```

### 2027-12-01 — positions

```json
[
 {
  "position_id": "POS-DEMO-A-crowd_safe",
  "issuer_key": "CIK9000001",
  "offering_id": "DEMO-A",
  "funded_cost_cents": 50850,
  "refunds_cents": 0,
  "distributions_cents": 0,
  "sale_proceeds_net_cents": 0,
  "holding": "",
  "status": "submitted",
  "flags": "",
  "written_off_observed": false,
  "realized_multiple": null,
  "realized_note": "not computed: position open, incomplete, or fully refunded (conversion is not cash)"
 },
 {
  "position_id": "POS-DEMO-A-security",
  "issuer_key": "CIK9000001",
  "offering_id": "DEMO-A",
  "funded_cost_cents": 0,
  "refunds_cents": 0,
  "distributions_cents": 2500,
  "sale_proceeds_net_cents": 0,
  "holding": "",
  "status": "finalized",
  "flags": "",
  "written_off_observed": false,
  "realized_multiple": null,
  "realized_note": "not computed: position open, incomplete, or fully refunded (conversion is not cash)"
 },
 {
  "position_id": "POS-DEMO-B-crowd_safe",
  "issuer_key": "CIK9000002",
  "offering_id": "DEMO-B",
  "funded_cost_cents": 150000,
  "refunds_cents": 0,
  "distributions_cents": 0,
  "sale_proceeds_net_cents": 0,
  "holding": "",
  "status": "submitted",
  "flags": "NO_APPROVAL;OUT_OF_POLICY:issuer_limit",
  "written_off_observed": false,
  "realized_multiple": null,
  "realized_note": "not computed: position open, incomplete, or fully refunded (conversion is not cash)"
 }
]
```
