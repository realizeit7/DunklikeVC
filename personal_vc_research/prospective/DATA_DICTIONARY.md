# Data dictionary — prospective pilot v1.0

Storage is SQLite (`data/pilot.sqlite`, local and gitignored) plus content-addressed snapshot bytes
(`data/blobs/<sha[:2]>/<sha256>`, gitignored). Public-only CSV copies of every table are written to `data/exports/`
(committed) by `export` and `run`. Timestamps are UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SS+00:00`).

**Append-only tables.** These reject any UPDATE or DELETE; corrections are new rows:
`documents`, `facts`, `decisions`, `decision_evidence`, `predictions`, `prediction_resolutions`, `events`, `pilot_clock`.

## Time fields (never merged)

| Concept | Where |
|---|---|
| Economic period / event date | `facts.financial_period`; `events.event_date` (+ `event_date_low/high` when an interval) |
| Claimed publication date | `documents.claimed_publication_date` (SEC filing date; a date displayed on a page) |
| Verified public-availability date | `documents.verified_public_date` (EDGAR acceptance timestamp) |
| First observed | `documents.first_observed_utc` (first retrieval of identical content from that URL); `offerings.first_observed_utc` |
| Retrieval timestamp | `documents.retrieved_utc` (this retrieval or check). This is the time used for leakage rules |
| Decision timestamp | `decisions.decision_utc`; `decisions.evidence_cutoff_utc` (equal for prospective decisions) |

## Tables

* **`pilot_clock`**
  * `pilot_start_utc`, `pilot_start_local_date` (America/New_York), `pilot_end_utc`, `pilot_end_local_date`.
  * Set once, by the first successful live `discover`, and mirrored in `pilot_clock.json` (committed).
* **`runs`**: one row per CLI invocation.
  * `run_id`, `command`, `started_utc`, `finished_utc`, `config_sha` (config version), `network_requests`,
    `cache_hits`, `errors`, `status`, `notes` (JSON summary).
* **`gaps`**: processing failures and access problems, reported separately from nondisclosure.
  * `kind` is one of `access_blocked`, `http_error`, `index_unavailable`, `parse_failure`, `run_failure`.
  * Also `url`, `detail`, `offering_id`.
* **`index_days`**: EDGAR daily-index days scanned.
  * `status` is one of `complete`, `no_index_weekend`, `missing` (gap logged).
  * Days whose index is not yet published are not stored and are re-checked on the next run.
* **`discovery_ledger`**: every Republic initial Form C seen, including excluded and withdrawn ones.
  * `accession`, `issuer_cik`, `offering_file_number`, `filing_date`, `acceptance_utc`, `intermediary_cik`,
    `intermediary_file_number`, `first_observed_utc`, `source` (`edgar_daily_index` | `edgar_full_text_search`),
    `offering_id`.
* **`offerings`**: the current state of each offering. Every change is also logged in `offering_status_log`.
  * **Identity:** `offering_id` = `RCF-{issuer CIK}-{offering file number}`. `issuer_id` = issuer CIK. Amendments
    (C/A) attach to the same offering; a new Form C with a new 020- file number is a separate round.
  * **Cohort:** `cohort` is one of:
    * `inception`: EDGAR acceptance at or after the pilot start;
    * `initial_watchlist`: discovered at startup, deadline in the future, no C-W; left-truncated, never pooled
      with inception;
    * `pre_start_other`.
  * **Eligibility:** `eligibility`, `eligibility_reason`, `security_class`, `security_evidence` (from the reused
    historical classifier).
  * **Status:**
    * `availability_status` is one of `unknown`, `open_verified`, `closed_reported`, `withdrawn`. It stays
      `unknown` unless verified; a future deadline is not proof that an offering is open.
    * `availability_evidence`.
    * `closing_status` is one of `none_reported`, `close_reported_c_u` (the issuer's own C-U completion
      language), `withdrawn_c_w`.
  * **Checks:** `captured_utc`, `last_check_utc`, `last_check_ok`, `next_check_due_utc`.
* **`documents`**: one immutable row per retrieval or check.
  * `source_url`, `accession`, `source_type` (`sec_filing_index`, `sec_primary_xml`, `sec_attachment`,
    `sec_submissions_json`, `platform_page`, `user_import`), `visibility` (`public` | `private`), the time fields
    above, `sha256`, `blob_path`, `bytes`, `http_status`, `extraction_method`, `parse_status`, `access_error`.
  * Identical bytes share one blob; each retrieval keeps its own row.
* **`facts`**: one row per fact.
  * `fact_kind`: `source_statement` (what a document says, e.g. a Form C XML field) or `extracted_fact` (derived
    from document text by a rule).
  * `field`, `value`. A NULL value means missing (never 0), with `missing_reason`.
  * `unit`, `currency`, `financial_period`, `locator` (XML tag, or page plus snippet), `extraction_method`.
  * `verification_status`: `structured_form_field_issuer_reported`, `text_regex_unreviewed`,
    `user_verified_against_source`, or `missing`.
  * `supersedes_fact_id`.
  * Analyst interpretations are not facts. They live in `decisions`, and predictions live in `predictions`.
* **`decisions`**: the journal.
  * `kind`: `prospective` or `retrospective_reconstruction`.
  * `status`: `select`, `pass`, `defer` or `unreviewed`. Only `user_confirmed=1` rows may be
    select/pass/defer. AI or analyst drafts stay `unreviewed`, with a `draft_recommendation`.
  * Also `reasons`, `counterarguments`, `unresolved_questions`, `analyst`.
  * `paper_amount_usd`: allowed only on a user-confirmed `select`. It is a hypothetical amount: no fill is assumed
    and no return is computed.
  * `packet_path`, `packet_sha256`.
* **`decision_evidence`**: the exact snapshot IDs behind each decision. A trigger rejects any document retrieved
  after the decision's evidence cutoff.
* **`predictions`**:
  * `target_event`, `event_kind` (`business` | `disclosure`), `horizon_months` (6 or 12), `deadline_utc`,
    `probability`, `resolution_rule`, `reporting_lag_days`, `missing_evidence_treatment`, `permitted_evidence`,
    `decision_id`.
  * `revises_prediction_id`: a revision is a new row, and the deadline is never moved.
* **`prediction_resolutions`**:
  * `outcome` is one of `true`, `false`, `unresolved_unknown`.
  * `false` is refused before the deadline plus the reporting lag.
  * `true` and `false` require cited evidence.
* **`events`**: dated observations from filings.
  * `event_type` covers amendments, C-U progress, C-W, C-AR, C-TR, Form D, later Form C, Reg A, S-1/424B4/8-A12B,
    and others. Also `event_date` (+ interval fields), `publication_date`, `observed_utc`, `source_document_id`,
    `accession`.
  * `source_claim` (the exact filing claim), `interpretation`, `conflict_status`, `uncertainty`.
  * A reporting termination or a missing filing is never coded as failure.
* **`review_queue_log`**:
  * The weekly queue (`rule` = `oldest_unreviewed_first`).
  * User-chosen reviews are recorded with `discretionary=1`. Reviewing is not selecting.
* **`effort_log`**: user-entered review time (`minutes`, `activity`, `activity_date`, `note`).

## Templates

* `templates/evidence_import_template.csv`: dated campaign pages, founder Q&A, company updates, contract documents,
  investor notices. `investor_notice` is always private.
* `templates/decision_template.csv`: decisions (`decide-csv`).
