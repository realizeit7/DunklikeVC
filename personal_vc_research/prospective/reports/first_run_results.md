# First run — results, source checks and what still needs scheduling or user input

Run date: 2026-10-14 (UTC). Branch `prospective-pilot-v1`. All commands were run from `personal_vc_research/` with
`SEC_USER_AGENT` set in the environment (not stored). The JSON output of each step is in `reports/run_log_*.json`.

## Pilot clock

* **Start:** 2026-10-14T15:16:34Z (2026-10-14, America/New_York). This is the start of the first successful live
  discovery run (`discover-20261014T151634Z-296b79`).
* **End:** 2027-01-12T15:16:34Z (2027-01-12, New York).
* **Not backdated.** The 7-day look-back scan only feeds the startup watchlist; it does not extend the inception
  cohort into the past.

## Commands executed

| # | Command | Result |
|---|---|---|
| 0 | `init` (15:14Z) | Smoke test before the run logs existed: created the database; no clock |
| 1 | `init` | Clock "not started" |
| 2 | `discover` (live) | Daily-index days 2026-10-07 → 10-14 scanned: 4 business days complete (10-07, 10-08, 10-09, 10-13), 2 weekend days with no index, and 2 pending (10-12 Columbus Day, 10-14 not yet published). 7 initial Form Cs seen from all portals, **0 from Republic**. Clock started. Startup watchlist by full-text search (120 days): 10 Republic offerings registered. 37 network requests, 11 s |
| 3 | `capture` (live, bounded batch of up to 10) | 6 eligible watchlist offerings captured: 18 documents (index, Form C XML, Form C PDF) and 292 facts. 12 network requests plus 6 cache hits; 6 min 40 s, mostly PDF text parsing |
| 4 | `queue --week 2026-W42` | Oldest-unreviewed-first queue: Hope-Neuron Therapeutx, Yakuru, Sherpa Healthy |
| 5 | `packet RCF-2114933-020-37299` | Review packet `reports/packets/RCF-2114933-020-37299_2026-10-14T152452Z_prospective.md`. A first version had a bug (contract coverage shown as "not assessed"); it was fixed and the packet regenerated. No decision references the deleted first version |
| 6 | `report-weekly` | `reports/weekly_2026-W42.md` |
| 7 | `run` (repeat, live) | **Idempotent.** 0 new ledger rows, offerings, documents, facts or events. Completed index days and captured offerings were skipped, and the 2 pending days were re-checked. The Republic page probe was blocked (HTTP 403) and logged once. 4 network requests, 2.5 s |
| 8 | Follow-up smoke check (live) | 2 watchlist offerings checked ahead of schedule through the real submissions-JSON path: 0 new filings; next check 2026-10-21 |
| 9 | `report-monthly`, `export` | `reports/monthly_2026-10-14.md`; public CSVs in `data/exports/` |

## Live-data counts (as of the end of the first run)

| Item | Count |
|---|---|
| Inception-cohort offerings (accepted on EDGAR after the pilot start) | **0**. A valid result: nothing could have been indexed yet |
| Initial watchlist, eligible (startup only, left-truncated) | 6 (4 SAFE, 2 equity) |
| Initial watchlist, excluded | 1 (revenue share: Optimistic Productions LLC) |
| Pre-start, not watchlisted (deadline passed or withdrawn) | 3 (Cognivix, ShredPay; Musicow US Vol. 1, which is excluded and withdrawn) |
| Discovery ledger rows | 10 |
| Documents / blobs | 18 / 18 (104 MB, not in git) |
| Facts | 298, including 6 contract-coverage summaries |
| Contract text present in the capture (unreviewed) / summary or unreadable only | 5 / 1 (TradeFunded: 61 MB PDF, above the parse limit) |
| Decisions / forecasts / events | 0 / 0 / 0 |
| Gaps | 2: an oversized PDF not parsed; the Republic page blocked (HTTP 403) |

All 6 watchlist offerings have availability **unknown**. Their Form C deadlines run from 2026-10-30 to
2027-01-15, but a deadline is not proof an offering is open, and the Republic pages could not be checked.

## Source checks on live records

The checks re-read the stored snapshot bytes and compared them with the database facts:

* **Form C XML fields** for Mightylicious and Hope-Neuron: revenue (both fiscal years), cash, security description,
  deadline, intermediary CIK and target amount. **14/14 matched the source XML.** Hope-Neuron's missing security
  description is absent in the source too, so it is stored as NULL with a reason.
* **Every value is issuer-reported** and unaudited unless the attached statements say otherwise. Hope-Neuron reports
  revenue of $0.00 (a reported value, not a missing one).
* **Intermediary.** All 10 ledger offerings carry commissionCik 0001751525 (OpenDeal Portal LLC, 007-00167) in their
  own XML.
* **Valuation-cap candidates were located in the contract text:**
  * Mightylicious: "The 'Pre-Money Valuation Cap' is $15,000,000" (page 55).
  * Yakuru: **tiered caps**, "early investors … pre-money valuation cap of $7,500,000" vs "standard investors …
    $15,000,000" (page 10). A regex cannot capture such conditions, so term candidates stay "unreviewed" until the
    contract is read.
* **Defect found and fixed.** The cap pattern let "M" match across a line break ("$15,000,000\nMaterial Terms"
  became "15,000,000 M", which could be misread as millions). The pattern is fixed and a regression test added.
  The 6 facts already captured keep their original values (append-only), and their locators show the context.
* **Interest-rate and maturity candidates are noisy.** They often come from the financial-statement notes (for
  example, a related-party note at 4.19%), not from the offered security. The packet shows the locator for each.

## Tests

* `pytest tests/prospective`: **14 passed**. They use synthetic fixtures with a fake EDGAR; they verify logic, not
  live accuracy. They cover:
  * late evidence leakage (trigger plus packet cutoff), and a retrospective reconstruction kept separate;
  * append-only snapshots, decisions and clock, with shared blobs and no overwrite;
  * amendments not duplicating an offering, and rounds staying distinct;
  * missing values as NULL, never 0;
  * unknown outcomes not becoming failures, and forecast deadlines, revisions and the Brier denominators;
  * equal follow-up for selected and passed offerings;
  * idempotent repeat discovery;
  * outage visibility;
  * a clock that is never reset;
  * private imports excluded from exports and git;
  * AI drafts never becoming selections;
  * the regex regression.
* Full repository suite: see the handoff.

## What requires future scheduling or user input

* **Scheduling.** Install the cron entry in `README.md` (`run_daily.sh`) on a persistent machine. Collection only
  happens when the job runs; until then, no inception offerings are being observed.
* **Weekly user review.** Work the queue (3 packets per week by default), record decisions with `--user-confirmed`,
  and log effort.
* **Optional user imports.** Campaign pages, Q&A and updates (Republic is not reachable from here); contract
  documents; and investor notices if voluntarily supplied (kept private).
* **Backups** of `data/pilot.sqlite` and `data/blobs/`, which are not in git. `data/exports/` and
  `pilot_clock.json` are committed.
