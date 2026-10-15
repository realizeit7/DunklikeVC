# v2 — LLM analyst, Korean briefs, user approvals and the personal investment ledger

v2 extends the prospective pilot. It does not change collection, the frozen historical study, or the pilot dates.

This is a **decision-support system**:
* Passing a screen does **not** establish investment quality or profitability.
* The system **never** places orders or moves money.
* Actual investments are made **manually by the user** on the platform after explicit approval, then recorded here.

## What is new

| Part | Files |
|---|---|
| Versioned migrations; the database is backed up before any migration | `migrations.py`; backups in `data/backups/` (gitignored) |
| Budget policy (user-established) | `policies/budget_policy_v1.yaml`, `ledger.py` |
| Screening policy (initial, **unvalidated**) | `policies/screening_policy_v1.md` |
| Prompt and schemas | `llm/prompts/analyst_prompt_v1.md`, `llm/schemas_v1.py` (`analysis_schema_v1`) |
| Frozen evidence packs | `packs.py`; `data/packs/*.json` (public SEC text, hash-checked) |
| 4-stage analysis, validation, status | `analysis.py`; raw outputs in `data/analyses/` |
| Korean brief | `brief.py`; `reports/briefs/` |
| Approvals, reservations, ledger | `ledger.py` |
| Evaluation tracks and version comparison | `evaluation.py` |
| Monthly v2 report | `portfolio_report.py` (live: written privately; demo: `reports/demo/`) |
| Synthetic demo | `python -m prospective.demo_ledger` → `reports/demo/` |

## LLM route

The default route uses the user's authenticated **Claude Code CLI**, called only with documented print-mode flags:

```
claude -p --tools "" --strict-mcp-config --no-session-persistence --output-format json \
       --system-prompt <analyst_prompt_v1> --json-schema <stage schema> [--model M] [--max-budget-usd 5]
```

* **No tools, no browsing.** All tools are disabled and the run happens in an empty temporary directory.
* **Pack as data.** The evidence pack is sent on stdin as data, never on the command line.
* **Recorded per run:** model and provider (as reported), cost, prompt, schema and policy versions, pack hash, and
  timestamps.
* **No API key.** It uses the existing Claude Code login; no paid API key is assumed.

**Manual or interactive route.** Use this if the CLI is unavailable, or if you prefer another session:
1. Run `python -m prospective analysis-export <PACK_ID> --out <dir>`. This writes the system prompt, the stage
   schemas and the stage-A payload.
2. Save each stage's JSON output as `<dir>/A_extraction.json` and so on. Re-run the export to get the next stage's
   payload.
3. Run `python -m prospective analyze <OFFERING> --version <V> --pack <PACK_ID> --adapter files --dir <dir>`.
   Validation is identical to the CLI route.

**The four stages** are run in sequence by one model:
1. A — evidence extraction.
2. B — business and investment analysis.
3. C — critical review. The same model reviews its own work, which is not independent verification.
4. D — final: gates, Korean briefing and forecasts.

**Validation is mechanical.** An output fails validation if any of the following holds:
* It breaks the schema; extra fields are rejected.
* A quote is not found verbatim on the cited pack page, or cites a document or page outside the pack.
* A sourced claim has no valid citation, or a calculation does not recompute.
* An inference lacks its basis, or an unverified assertion is used to support a gate.
* A statistic in a forecast's basis appears in none of the cited claims.

A failed output is stored with status `analysis_failed`.

**Status is derived by software** (`derive_status`), never by the LLM. If any critical item is not confirmed with
valid citations, the result is at best `needs_information`.

## Weekly use (about 6 h/week at most; 3 briefs is a ceiling, not a quota)

```bash
cd personal_vc_research
python -m prospective run                      # collection (or the scheduled job)
python -m prospective queue --week 2026-W43    # oldest eligible unreviewed first; --pick records discretionary reviews
python -m prospective analyze <OFFERING_ID> --version analyst_v1_baseline       # builds a frozen pack, runs 4 stages
python -m prospective brief <ANALYSIS_ID>      # Korean brief -> reports/briefs/
```

Read the brief, especially the header (dates, versions, availability, contract status, staleness), section 7
(gates), "unknowns", and the requested action. Then do one of the following.

* **Pass or defer.** Run `python -m prospective decide <ID> --status pass --analyst me --user-confirmed --reasons "..."`.
* **Approve an amount for manual investment.**

  First, once only, acknowledge the policy and confirm the issuer key:

  ```bash
  python -m prospective ack-policy screening --statement "I read screening_policy_v1; it is unvalidated."
  python -m prospective confirm-issuer <ISSUER_CIK> --issuer-key CIK<number> --basis "same legal issuer; no affiliated SPV"
  ```

  Then record the approval:

  ```bash
  python -m prospective approve <OFFERING_ID> --i-am-the-user --amount-usd 250 --fee-usd 5 --fee-basis upper_bound \
      --issuer-key CIK<number> --analysis-id <ANALYSIS_ID> --min-investment-usd 150 \
      --terms "Crowd SAFE, standard-tier $15M pre-money cap" --availability "campaign page open on 2026-10-20, checked by me" \
      --contract-doc <DOC_ID>
  ```

  **Every approval:**
  * needs an explicit amount (there is no default);
  * needs a confirmed fee or a fee upper bound; without one it is `incomplete` and reserves nothing.

  **The approval is re-checked against:**
  * both budget limits, counting all active reservations;
  * the confirmed issuer aggregation;
  * any filings or documents newer than the analysis evidence cutoff, which block it until there is a fresh review;
  * the minimum investment and the tier or terms;
  * the expiry (14 days by default, never after the offering deadline).

  **Overrides:**
  * Overriding a failed or incomplete AI screen requires `--override-rationale`; the failed conditions are stored.
  * Budget limits can never be overridden.

* **Invest manually on the platform**, then record what actually happened:

  ```bash
  python -m prospective ledger-record --type investment_submitted --offering <ID> --approval <APPROVAL_ID> \
      --date 2026-10-21 --amount-usd 250 --fee-usd 4.50 --ref <platform transaction id> \
      --doc-file ~/Downloads/confirmation.pdf --verification platform_confirmation
  python -m prospective ledger-record --type investment_finalized --offering <ID> --related <EVENT_ID> --date 2026-11-10 --ref <id>
  ```

  * The confirmation file is stored **privately** (`data/imports/private/`, gitignored) and never exported.
  * Importing the same `--ref` twice does nothing.
  * A transaction outside policy is recorded truthfully, with flags such as `OUT_OF_POLICY:issuer_limit`,
    `NO_APPROVAL` or `APPROVAL_EXPIRED`.
* **Later updates** use the same command, with the matching type:
  * `investment_canceled`, then `refund_verified --related <investment event>`;
  * `investor_fee_paid`;
  * `security_conversion --quantity`;
  * `corporate_action`;
  * `cash_distribution`;
  * `sale_proceeds`, `sale_fee`;
  * `write_off_observed`;
  * `residual_holding_update`.

  Use `ledger-void <EVENT_ID> --reason` for corrections. Nothing is ever edited or deleted.

## Budget semantics (`budget_policy_v1`, integer cents)

* **Limits:**
  * USD 12,000 committed per budget period.
  * USD 1,200 committed per underlying issuer for life. This is a fixed dollar limit equal to 10% of the annual
    budget, not a portfolio weight.
  * Direct investor-paid fees count toward both limits.
* **Periods:**
  * The anchor is the America/New_York effective date of the **first actual investment** submission. Installing the
    software, analysing a company or recording a paper decision does not start the clock.
  * Periods run between consecutive anniversaries. An anchor of Feb 29 has Feb 28 anniversaries in non-leap years.
* **Before the first investment**, active reservations are checked against USD 12,000 in a `pre_start` bucket.
* **Annual usage** = funded cost (principal + fees) of investments effective in the period, less verified refunds
  attributed to the original investment's period, plus **all** active reservations.
  * Reservations are counted conservatively: a reservation still pending at a rollover counts in whichever period a
    new commitment is checked. When it settles, it is consumed and counted once, in the period of its investment's
    effective date.
* **Issuer usage (lifetime)** = funded cost + fees + active reservations − verified refunds of canceled or reversed
  investments (the refunded amount only; non-refunded fees stay counted).
  * Sales, losses, write-offs, distributions and conversions never restore capacity.
* **Reservations stop counting** when the investment is submitted, when the user confirms a cancellation
  (`release`), or when the approval expires unexecuted.
* **Issuer aggregation.** Rounds, securities, brands and SPVs of the same underlying issuer share one user-confirmed
  `issuer_key`.
* The annual limit is a **ceiling, not a target**. There is no borrowing, no leverage and no automatic reinvestment.

**Reporting.** `positions` and `report-monthly-v2` keep funded cost, refunds, distributions, net sale proceeds and
holdings separate.
* A realized multiple is computed only for a position documented as fully exited or written off.
* A conversion is not cash.
* There is no tax treatment.

## Private evidence and backups

* **What is private.** Confirmations, signed contracts, bank details, tax documents, position-level reports,
  approvals and the ledger.
* **Where it lives.** Private documents are stored under `data/imports/private/` (gitignored). Approvals and the
  ledger live in the local SQLite database (gitignored). None of them are in the CSV exports, and live monthly v2
  reports are written to `data/imports/private/reports/`.
* **What to back up.** `data/pilot.sqlite`, `data/blobs/` and `data/imports/private/` (for example, an encrypted
  external drive). Migrations also create automatic backups in `data/backups/`.
* **Restoring from git.** `restore` rebuilds only the public research tables from the exports. The personal ledger
  must come from your own backup.

## Evaluation (tracks kept separate; no auto-promotion)

There are five tracks:
1. Extraction and citation validity: automatic validation plus `citation_checks` spot checks.
2. Forecasting: Brier score only on adjudicated forecasts, with resolved and unresolved counts, grouped by issuer.
3. Research-screen behaviour.
4. User selection.
5. Actual investment outcomes.

**Comparing versions** (`evaluation.comparison`):
* Register the challenger **before** it runs (`analyst-register`).
* Run it on the **same frozen packs**, excluding its development cases.
* Count only outcomes resolved after both registrations.
* Below 30 resolved outcomes, the verdict is "insufficient evidence"; that threshold is a proposed convention.
* Do not tune prompts on resolved examples and call the result out-of-sample.

**Equal follow-up.** All offerings follow the same follow-up schedule: AI-passed, AI-failed, needs-information,
approved, passed, deferred and unreviewed. Investors may receive private updates that non-investors do not; that
difference in visibility is not better company performance.
