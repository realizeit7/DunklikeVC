# DunklikeVC — Prospective Research Pilot v1.0 (+ v2 LLM analyst and personal ledger)

> **v2:** LLM analysis, Korean briefs, user approvals, the budget policy and the investment ledger are described in
> [`V2_GUIDE.md`](V2_GUIDE.md).

This is a 90-day **data-collection and workflow pilot** for Republic US Reg CF offerings. It records what was
knowable when, and the decisions made at that time, and it follows outcomes equally for every offering.

It is **not**:
* a test of investment profitability;
* an investment adviser;
* an authorization to invest.

No investment is needed to take part.

The closed historical study (`../README.md`, `../reports/phase4_decision_memo.md`) is unchanged. This package reuses
these pieces of it:
* `Fetcher`: HTTP cache, retrieval manifest, rate limits, request budget, SEC User-Agent.
* `Config`.
* `classify_security`: the security and eligibility rules.
* `classify_filing`: filing-to-event mapping.
* `text_quality`: text-layer screening.

## Setup

```bash
cd personal_vc_research
pip install -r requirements.txt
export SEC_USER_AGENT="personal_vc_research your.email@example.com"   # required by SEC fair-access policy; never committed
python -m prospective init        # creates data/pilot.sqlite; restores the committed pilot clock if present
```

## Pilot clock

The pilot clock was set by the first successful live discovery: **2026-10-14T15:16:34Z (2026-10-14, New York)**. It
ends 90 days later, on **2027-01-12T15:16:34Z**. The clock is stored in `pilot_clock.json` (committed) and in the
database, and it can never be reset or backdated.

## Commands (run from `personal_vc_research/`)

| Command | What it does |
|---|---|
| `python -m prospective discover` | Scans the EDGAR daily form index for every new initial Form C and keeps Republic ones (intermediary CIK 0001751525 / 0001672732, files 007-00167 / 007-00046) by reading each Form C's XML intermediary block |
| `python -m prospective capture [--limit N]` | Full snapshot at first discovery: filing index, Form C XML (structured facts) and attachments (term candidates, contract markers) |
| `python -m prospective followup` | Change and follow-up checks that are due: weekly while open or unknown, monthly after a close or withdrawal. The same rule applies whatever the decision |
| `python -m prospective run` | The daily job: discover + capture + followup + public export |
| `python -m prospective import-evidence FILE.csv` | Imports dated user captures (see `templates/evidence_import_template.csv`) |
| `python -m prospective queue --week 2026-W43 [--pick ID]` | This week's review queue (oldest unreviewed first); `--pick` records a discretionary review |
| `python -m prospective packet OFFERING_ID` | Review packet with an evidence cutoff (`--retrospective-as-of` labels a reconstruction) |
| `python -m prospective decide OFFERING_ID --status pass --analyst me --user-confirmed --packet reports/packets/<file>.md --reasons "..." --counterarguments "..." --unresolved "..."` | Records a decision; `decide-csv templates/decision_template.csv` does the same in bulk |
| `python -m prospective forecast-add ID --event "..." --kind disclosure --horizon-months 12 --probability 0.3 --resolution-rule "..." --reporting-lag-days 60 --missing-evidence "remains unresolved" --forecaster me` | Optional 6- or 12-month milestone forecast; also `forecast-revise`, `forecast-resolve` |
| `python -m prospective log-effort --minutes 45 --activity weekly_review --date 2026-10-19` | Records user time |
| `python -m prospective report-weekly` / `report-monthly` | Markdown reports in `reports/` |
| `python -m prospective export` / `status` | Public-only CSV exports in `data/exports/` (NULL written as `\N`) / current state |
| `python -m prospective restore` | Rebuilds an **empty** database from the committed exports and `pilot_clock.json` (for example, on a new machine). Snapshot blobs and private rows are not in git; missing blobs are counted |

## One weekly review (target: at most 6 hours of user time per week)

1. Read the latest `reports/weekly_<week>.md`. It lists new offerings, changes, due follow-ups, access problems and
   last week's effort.
2. Run `python -m prospective queue --week <ISO week>`. The default is 3 detailed reviews, oldest unreviewed first.
   If you also review a deal outside the queue, record it with `--pick`.
3. For each queued offering:
   * Run `packet <id>`.
   * Read the packet and the Form C sections it points to, especially the contract pages it lists.
   * Write down: what the company sells and who pays; the evidence behind the claims; the main risks and
     counterarguments; the contract and price considerations; what is missing; and what future evidence would
     change your judgment.
4. Record the decision with `decide ... --user-confirmed --packet <that packet>`.
   * Status is `select`, `pass` or `defer`. A selection may carry `--paper-amount-usd`, a hypothetical amount: no
     fill is assumed and no return is computed.
   * Drafts by an AI are recorded only as `--status unreviewed --draft-recommendation ...` without
     `--user-confirmed`.
5. Optional: add explicit 6- or 12-month forecasts (see `templates/` and the data dictionary for the required
   fields).
6. Run `log-effort` with the minutes you spent.

Optionally, save campaign pages or updates from your own browser and import them with `import-evidence`.
* Their observation time is the import time, so they can never enter an earlier decision.
* Investor notices are always private: they are stored under `data/imports/private/` (gitignored) and excluded from
  exports.

## Activating recurring collection (not installed automatically)

Collection happens **only when the job actually runs**. A missed day is not backfilled silently. The next run
re-scans every day whose index was not yet scanned, and every run is recorded in `runs`.

```bash
crontab -e
# add (07:15 New York time, daily):
CRON_TZ=America/New_York
15 7 * * * SEC_USER_AGENT="personal_vc_research your.email@example.com" /path/to/DunklikeVC/personal_vc_research/prospective/run_daily.sh >> $HOME/prospective_cron.log 2>&1
```

`run_daily.sh` runs `run` every day, `report-weekly` on Mondays and `report-monthly` on the 1st. Run it on a
machine that keeps `data/pilot.sqlite` and `data/blobs/`; a cloud container is reclaimed after inactivity.

**Back up `data/` regularly.** Blobs are not in git.

To move to a new machine:
1. Check out the branch and run `python -m prospective restore`.
2. Copy `data/blobs/` from the backup, if you have it.
3. Run `run`. With no scan history it resumes the daily-index scan from the pilot start date, so no day is skipped.

## Data integrity rules (enforced in code, tested on synthetic fixtures)

* **Immutable records.**
  * Snapshots, facts, decisions, decision evidence, predictions, resolutions, events and the clock are
    append-only (SQLite triggers).
  * Identical bytes share a blob, and every retrieval keeps its own row.
  * A changed page is a new snapshot; old bytes are never overwritten.
* **No leakage.** A decision's evidence is exactly the documents retrieved at or before its cutoff. A trigger
  rejects later documents even when their claimed publication date is earlier. Retrospective reconstructions are
  labelled separately and never replace the original.
* **Offering identity.** Offering = issuer CIK + offering file number. Amendments attach to the same offering;
  separate rounds stay separate.
* **Missing and unknown values.**
  * Missing facts are NULL with a reason, never 0. A reported "0.00" is a reported value.
  * Unknown outcomes stay unknown. A forecast cannot be resolved `false` before its deadline plus the reporting
    lag, and missing evidence leaves it unadjudicated.
  * Brier scores use only adjudicated original forecasts, and the resolved and unresolved denominators are shown
    beside every score.
* **Availability** stays `unknown` unless it is verified. A future deadline is not proof that an offering is open.
  The Republic platform is probed at most once per run and is not retried within the 7-day cooldown after a block.
* **Separation of evidence.**
  * Source statements (Form C XML fields), extracted facts (text-regex candidates, always "unreviewed"), analyst
    interpretations (the decision journal) and predictions are stored separately.
  * Summary text is not treated as reading the contract.

## Known limitations (v1)

* **Republic platform pages are inaccessible** from this environment (HTTP 403 / Cloudflare). Live availability,
  campaign updates and Q&A require user imports. Platform coverage is flagged as missing.
* **EDGAR daily indexes.**
  * An index appears only after the day ends, so first observation lags filing by up to about one day plus the
    cron interval.
  * A missing index for a past business day is logged as `index_unavailable` (a holiday or an outage).
* **Startup watchlist.** It came from EDGAR full-text search. Its completeness was not verified; it is
  left-truncated and is never pooled with the inception cohort.
* **What is extracted.**
  * Extraction covers structured Form C XML fields and bounded regex term candidates only.
  * Team, traction, use of proceeds, valuation basis and investor rights require reading the documents (the
    packet points to the pages).
  * OCR is off by default (`capture.ocr_enabled`); unreadable text layers are logged as gaps.
  * Documents over 30 MB are stored but not parsed.
* **Outcomes.** The follow-up checks observe EDGAR filings only (C/A, C-U, C-W, C-AR, C-TR, Form D, later Form C,
  Reg A, IPO filings). Distributions and conversions need issuer or user documents. No proportional allocation is
  ever inferred, and Republic's commission-holding returns are never treated as retail returns.

## Day-90 review (workflow sustainability, not returns)

Assess:
* **Coverage and timeliness:** inception-cohort counts and acceptance-to-observation delay, from the monthly reports.
* **Snapshot integrity:** append-only checks and blobs present for every document row.
* **Usability of contract and company information:** contract-coverage counts and the packet review experience.
* **Follow-up visibility:** due checks completed, failures, unknown status.
* **User effort** against 6 h per week, from `effort_log`.
* **Whether the evidence collected justifies continuing.**

Recommend one of: continue, narrow scope, change sources, or stop. Forecasts that extend past day 90 stay pending;
their horizons are never shortened. Any continued monitoring must be an explicit later decision.
