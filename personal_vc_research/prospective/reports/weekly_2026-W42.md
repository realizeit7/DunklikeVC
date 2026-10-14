# Weekly report 2026-W42 (2026-10-07 → 2026-10-14 UTC)

Pilot: start 2026-10-14T15:16:34+00:00 (2026-10-14 New York), end 2027-01-12T15:16:34+00:00. Collection only happens when the commands actually run; runs this week are listed below.

## Newly discovered eligible offerings — inception cohort (primary)

_none_

## Newly added to the initial watchlist (startup only; left-truncated; never pooled with inception)

| offering_id | legal_name | security_class | initial_filing_date | first_observed_utc |
|---|---|---|---|---|
| RCF-2147043-020-37424 | Mightylicious Inc | safe | 2026-09-28 | 2026-10-14T15:16:41+00:00 |
| RCF-2096055-020-37309 | Yakuru Inc | safe | 2026-08-05 | 2026-10-14T15:16:41+00:00 |
| RCF-2114933-020-37299 | Hope- Neuron Therapeutx, Inc | equity | 2026-07-30 | 2026-10-14T15:16:42+00:00 |
| RCF-2143343-020-37370 | Sherpa Healthy Inc. | safe | 2026-09-02 | 2026-10-14T15:16:42+00:00 |
| RCF-2128340-020-37393 | TradeFunded LLC | equity | 2026-09-16 | 2026-10-14T15:16:43+00:00 |
| RCF-2147987-020-37439 | FOSH Live, Inc. | safe | 2026-10-05 | 2026-10-14T15:16:43+00:00 |

Ledger only (not tracked): 2 excluded Republic offerings and 3 pre-start offerings outside the watchlist were first observed this week.

## Document and status changes (filings observed this week)

_none_

## Review queue (oldest_unreviewed_first, 3 of 6 unreviewed)

Reviewing a deal is not selecting it. Record any discretionary pick with `queue --pick OFFERING_ID`.

| offering_id | legal_name | cohort | initial_filing_date | availability_status |
|---|---|---|---|---|
| RCF-2114933-020-37299 | Hope- Neuron Therapeutx, Inc | initial_watchlist | 2026-07-30 | unknown |
| RCF-2096055-020-37309 | Yakuru Inc | initial_watchlist | 2026-08-05 | unknown |
| RCF-2143343-020-37370 | Sherpa Healthy Inc. | initial_watchlist | 2026-09-02 | unknown |

## Follow-ups due in the next 7 days (same rule for selected, passed, deferred and unreviewed)

| offering_id | legal_name | cohort | availability_status | closing_status | next_check_due_utc | last_check_ok |
|---|---|---|---|---|---|---|
| RCF-2114933-020-37299 | Hope- Neuron Therapeutx, Inc | initial_watchlist | unknown | none_reported | 2026-10-21T15:16:42+00:00 | 1 |
| RCF-2143343-020-37370 | Sherpa Healthy Inc. | initial_watchlist | unknown | none_reported | 2026-10-21T15:16:42+00:00 | 1 |
| RCF-2128340-020-37393 | TradeFunded LLC | initial_watchlist | unknown | none_reported | 2026-10-21T15:16:43+00:00 | 1 |
| RCF-2147987-020-37439 | FOSH Live, Inc. | initial_watchlist | unknown | none_reported | 2026-10-21T15:16:43+00:00 | 1 |
| RCF-2147043-020-37424 | Mightylicious Inc | initial_watchlist | unknown | none_reported | 2026-10-21T15:25:18+00:00 | 1 |
| RCF-2096055-020-37309 | Yakuru Inc | initial_watchlist | unknown | none_reported | 2026-10-21T15:25:18+00:00 | 1 |

## Missing evidence and access problems

Processing failures and access blocks (not the same as nondisclosure):

| kind | n | example |
|---|---|---|
| access_blocked | 1 | https://republic.com/companies |
| parse_failure | 1 | https://www.sec.gov/Archives/edgar/data/2128340/000212834026000005/tradef.pdf |

Most frequently absent structured Form C fields (nondisclosure or blank in the filing):

| field | n |
|---|---|
| security_description | 1 |

## Collection runs this week

| command | n | requests | cache_hits | errors |
|---|---|---|---|---|
| capture | 1 | 12 | 6 | 0 |
| discover | 1 | 37 | 0 | 0 |
| followup-live-smoke | 1 | 2 | 0 | 0 |
| init | 2 | 0 | 0 | 0 |
| packet | 2 | 0 | 0 | 0 |
| queue | 1 | 0 | 0 | 0 |
| report-weekly | 2 | 0 | 0 | 0 |
| run | 1 | 4 | 0 | 0 |

## User effort recorded this week

_none_

Total: 0 minutes (0.0 h of the 6 h weekly budget). No effort entries yet — record time with `log-effort`.
