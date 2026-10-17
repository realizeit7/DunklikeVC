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

## v2 tables (migration 2; see `V2_GUIDE.md`)

`schema_migrations` records each migration's version, description, script hash and the automatic backup taken
before it. All v2 tables are append-only.

**Personal tables** — never exported:
* `policy_acknowledgments` (kind, version, sha256, statement).
* `issuer_groups`: user-confirmed mapping of a member CIK to an `issuer_key`, so that rounds, brands and SPVs share
  one issuer limit.
* `approvals`: a user approval with an explicit amount, plus:
  * the fee and its basis (`confirmed` | `upper_bound`), and the applicable terms (minimum investment, tier);
  * the availability note, the contract document, and the analysis and pack hash;
  * the expiry, the check results (budget, issuer, material changes, minimum, policy acknowledgment);
  * `status` (`executable` | `incomplete` | `blocked`), the AI status at approval, and any failed conditions with the
    override rationale;
  * `user_confirmed`, which is always 1.
* `ledger_events`: actual events in integer cents.
  * `event_type` is one of: reservation_created / reservation_released, investment_submitted / investment_finalized,
    investor_fee_paid, investment_canceled, refund_verified, security_conversion, corporate_action,
    cash_distribution, sale_proceeds, sale_fee, write_off_observed, residual_holding_update, correction_void.
  * Each row also has `effective_date` (New York), `observed_utc`, `amount_cents`, `fee_cents`, `quantity`,
    `related_event_id`, `document_id` (a private document), `external_ref` (unique per type, so duplicate imports are
    ignored), `verification_status`, and `policy_flags` (e.g. `OUT_OF_POLICY:issuer_limit`, `NO_APPROVAL`,
    `APPROVAL_EXPIRED`).

**Research tables** — public-safe, exported:
* `evidence_packs`: pack id, cutoff, sha256, path, document ids, page count, gaps, critical checklist.
* `analyst_versions`: prompt, schema and policy versions, requested model, settings (tools disabled, repair rounds),
  registration time, development offerings.
* `analysis_runs`:
  * the pack and its hash, the versions, the adapter, and the model and provider as reported;
  * timestamps, status (`passes_research_screen` | `fails_research_screen` | `needs_information` |
    `analysis_failed`), and split (`development` | `evaluation`);
  * the output path and hash, validation errors, cost, the critical-item status and the stage metadata.
* `analysis_claims`: claim id and text, type, evidence status, citations, observed cutoff, financial period,
  calculation inputs, contradictions.
* `analysis_gates`: the three LLM gates plus the software budget gate, each with result, criteria, supporting and
  counterevidence claim ids, and uncertainty.
* `prediction_meta`: links forecasts to an analysis, pack hash, version and model. The label is always
  `model_judgment_uncalibrated`.
* `citation_checks`: spot checks (`independent_extractor_recheck`, `reviewer_semantic`).

## v2.1 tables (migration 3; see `V2_1_GUIDE.md`)

All v2.1 tables are append-only (UPDATE/DELETE triggers abort). They reference v2 rows; they never rewrite them.

| Table | One row per | Key fields |
|---|---|---|
| `access_attempts` | platform/website access attempt | `attempted_utc` (retrieval time), `method` (http_get_single / headless_chromium_single / wayback_availability_api_single), `http_status`, `final_url`, `result` (public_content / challenge / login_required / http_error / empty_or_script_only / network_error), `content_available`, `visibility` (public / authenticated / not_determined), `challenge_state`, `login_state`, `capture` (complete_html_snapshot / none), `content_sha256`, `markers` (JSON), `note`. Mirrored to `reports/republic_access_attempts.csv`. Cookies are never stored. |
| `source_checks` | change check of a source | `source` (sec_edgar_submissions), `checked_utc`, `success` 0/1, `covers_from_utc`/`covers_to_utc` (interval for which "no new filings" may be stated; only when success=1) |
| `assessments` | analysis × classifier version | `assessment`, `evidence_completeness`, `operational_readiness`, `budget_status`, `decisive_criteria`, `reasons` (Korean), `unresolved_criteria`, `freshness` (JSON snapshot), `policy_version` = `screening_policy_v1_1_proposed_unacknowledged`, `notes` (legacy v1 status) |
| `criterion_results` | analysis × criterion (BT1–BT5, PC1–PC3) | `model_result` (pass/fail/unknown, from Stage D), `final_result` (pass/fail/unresolved, after code support rules), `support` (why), `claim_ids`, `reason_ko`, `validator_notes` |
| `calculations` | deterministic calculation (K-id) | `calc_type` (`K1:implied_pre_money_equity`, …), `formula`, `inputs` (value, unit, as_of, claim id, citations), `assumptions`, `included_instruments`, `excluded_instruments`, `units`, `result_value`, `result_kind` (computed / illustrative / withheld), `withheld_reason`, `calculator_version` |
| `support_checks` | claim × checker | `checker` (`model:<id>` or `human:<name>`), `judgment_label` (model_judgment_not_verification / human_spot_check_against_source_page), `citation_exists`, `passage_supports`, `omitted_qualifications`, `evidence_type`, `conflicts`, `overstatement`, `verdict` |
| `forecast_definitions` | v2 prediction | `target_type` (event_occurs / issuer_announces / independently_corroborated), `target_scope`, `deadline_utc`, `reporting_lag_days`, `allowed_evidence`, `rationale`, `assumptions`, `unknown_treatment`, `cancellation_treatment`, `early_true_allowed`=1, `silence_is_false`=0 (CHECK) |
| `forecast_lineage` | note about an existing prediction | `original_prediction_id`, `relation` (flagged_compound / split_into / redefined_by / superseded_definition), `successor_prediction_id`, `reason`. The original prediction stays scorable exactly as written. |
| `stage_usage` | stage × attempt of a v2 run | `attempt` (original / repairN), `seconds`, token counts, `cost_estimate_usd`, `cost_label` = `cli_estimated_list_price_equivalent_not_billed`, `outcome`, `n_errors` |

`analysis_runs.status` for v2 runs is the policy-v1 mapping, which is still the policy of record. The four
dimensions live in `assessments`. Packs built with targeted OCR have `pack_version` = `pack_v1_targeted_ocr` and list
the unprocessed pages as gaps.

## v2.2 tables (migration 4; see `V2_2_GUIDE.md`)

All four tables are append-only.

| Table | One row per | Key fields |
|---|---|---|
| `policy_activations` | user activation of a policy | `policy_version`, `policy_sha256`, `actor` (CHECK = 'user'), `statement`. A policy is **active** only if a row matches the version AND the file's current hash. **Personal: never exported.** |
| `rule_findings` | analysis × policy rule | `rule_text`, `policy_version`/`policy_sha256`/`policy_state`, `model_result`, `final_result` (adverse_decisive / adverse_contributing / not_adverse / unknown / not_applicable), `scope`, `independently_decisive`, `facts` (JSON: claim, role, generic trigger, evidence kind, citations, date, attribution, support verdict), interpretation / counterevidence / unresolved / what would change (Korean), `validator_notes` |
| `assessments_v3` | analysis × classifier | `screening` (provisional_* unless the policy is active), `evidence_status` + `evidence_scope`, `thesis_status`, `execution`, `budget` (remaining capacity, fee status, check time), `decisive` |
| `thesis_answers` | analysis × question Q1–Q7 | `status`, `answer_ko`, `claim_ids` |

For v3 runs, `analysis_runs.status` is a placeholder (`needs_information` / `analysis_failed`); v3 results never feed
approvals.
