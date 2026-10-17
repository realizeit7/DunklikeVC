"""Versioned, non-destructive schema migrations with a pre-migration backup.

* Migration 1 is the v1 pilot schema (unchanged). A database created by v1 (without `schema_migrations`) adopts it
  as already applied.
* Migration 2 adds the v2 tables: analysis, screening, approvals, ledger and evaluation.
* Migration 3 (v2.1) adds: access_attempts, source_checks, assessments, criterion_results, calculations,
  support_checks, forecast_definitions, forecast_lineage and stage_usage. Existing rows (v2 analyses, forecasts 1-5)
  are untouched; v2.1 records reference them instead of rewriting them.
* Migration 4 (v2.2) adds: policy_activations (user-only activation of a specific policy version + hash),
  rule_findings (the decision chain per rule), assessments_v3 and thesis_answers. Nothing earlier is rewritten.

Migrations only CREATE tables, triggers and indexes; they never drop or rewrite existing rows. Before any pending
migration is applied to a database that already holds data, the file is copied with SQLite's online backup API to
`data/backups/`.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import sqlite3
from pathlib import Path

V2_APPEND_ONLY = ["policy_acknowledgments", "issuer_groups", "evidence_packs", "analyst_versions", "analysis_runs",
                  "analysis_claims", "analysis_gates", "prediction_meta", "approvals", "ledger_events",
                  "citation_checks"]

V2_SQL = """
CREATE TABLE IF NOT EXISTS policy_acknowledgments (
  ack_id INTEGER PRIMARY KEY AUTOINCREMENT, policy_kind TEXT NOT NULL, policy_version TEXT NOT NULL,
  policy_sha256 TEXT NOT NULL, acknowledged_utc TEXT NOT NULL, statement TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS issuer_groups (      -- user-confirmed aggregation of CIKs/brands/SPVs to one issuer
  row_id INTEGER PRIMARY KEY AUTOINCREMENT, member_cik TEXT NOT NULL, issuer_key TEXT NOT NULL,
  basis TEXT NOT NULL, user_confirmed INTEGER NOT NULL, created_utc TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS evidence_packs (
  pack_id TEXT PRIMARY KEY, offering_id TEXT NOT NULL, pack_version TEXT NOT NULL, cutoff_utc TEXT NOT NULL,
  created_utc TEXT NOT NULL, sha256 TEXT NOT NULL, path TEXT NOT NULL, document_ids TEXT NOT NULL,
  n_pages INTEGER, gaps TEXT, critical_checklist TEXT);

CREATE TABLE IF NOT EXISTS analyst_versions (
  version_id TEXT PRIMARY KEY, role TEXT NOT NULL, prompt_version TEXT NOT NULL, schema_version TEXT NOT NULL,
  policy_version TEXT NOT NULL, model_requested TEXT, settings TEXT, description TEXT NOT NULL,
  registered_utc TEXT NOT NULL, development_offering_ids TEXT NOT NULL DEFAULT '[]');

CREATE TABLE IF NOT EXISTS analysis_runs (
  analysis_id INTEGER PRIMARY KEY AUTOINCREMENT, offering_id TEXT NOT NULL, pack_id TEXT NOT NULL,
  pack_sha256 TEXT NOT NULL, version_id TEXT NOT NULL, prompt_version TEXT NOT NULL, schema_version TEXT NOT NULL,
  policy_version TEXT NOT NULL, adapter TEXT NOT NULL, model_reported TEXT, provider_reported TEXT, settings TEXT,
  started_utc TEXT NOT NULL, finished_utc TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('passes_research_screen','fails_research_screen','needs_information','analysis_failed')),
  split TEXT NOT NULL CHECK (split IN ('development','evaluation')),
  output_path TEXT, output_sha256 TEXT, validation_errors TEXT, cost_usd REAL, notes TEXT);

CREATE TABLE IF NOT EXISTS analysis_claims (
  row_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER NOT NULL, claim_id TEXT NOT NULL, stage TEXT,
  claim_text TEXT NOT NULL, claim_type TEXT, evidence_status TEXT NOT NULL, citations TEXT NOT NULL,
  observed_cutoff_utc TEXT NOT NULL, financial_period TEXT, calculation_inputs TEXT, contradictions TEXT, missing TEXT);

CREATE TABLE IF NOT EXISTS analysis_gates (
  row_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER NOT NULL, gate TEXT NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('pass','fail','unknown')), source TEXT NOT NULL,
  criteria TEXT, supporting TEXT, counterevidence TEXT, uncertainty TEXT);

CREATE TABLE IF NOT EXISTS prediction_meta (
  prediction_id INTEGER PRIMARY KEY, analysis_id INTEGER, pack_sha256 TEXT, version_id TEXT, model_reported TEXT,
  probability_label TEXT NOT NULL DEFAULT 'model_judgment_uncalibrated');

CREATE TABLE IF NOT EXISTS citation_checks (    -- spot checks of extraction/citations (evaluation track 1)
  row_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER NOT NULL, claim_id TEXT NOT NULL, checked_utc TEXT NOT NULL,
  checker TEXT NOT NULL, method TEXT NOT NULL, result TEXT NOT NULL, note TEXT);

CREATE TABLE IF NOT EXISTS approvals (
  approval_id INTEGER PRIMARY KEY AUTOINCREMENT, offering_id TEXT NOT NULL, issuer_key TEXT NOT NULL,
  analysis_id INTEGER, pack_sha256 TEXT, contract_document_id INTEGER,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0), fee_cents INTEGER, fee_basis TEXT,
  terms TEXT NOT NULL, availability_note TEXT NOT NULL, approved_utc TEXT NOT NULL, expires_utc TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('executable','incomplete','blocked')),
  checks TEXT NOT NULL, ai_status_at_approval TEXT, override_failed_conditions TEXT, override_rationale TEXT,
  screening_policy_version TEXT, budget_policy_version TEXT NOT NULL, supersedes_approval_id INTEGER,
  user_confirmed INTEGER NOT NULL CHECK (user_confirmed = 1));

CREATE TABLE IF NOT EXISTS ledger_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, approval_id INTEGER, position_id TEXT,
  issuer_key TEXT NOT NULL, offering_id TEXT, security TEXT, effective_date TEXT NOT NULL, observed_utc TEXT NOT NULL,
  amount_cents INTEGER NOT NULL DEFAULT 0 CHECK (amount_cents >= 0), fee_cents INTEGER NOT NULL DEFAULT 0 CHECK (fee_cents >= 0),
  currency TEXT NOT NULL DEFAULT 'USD', quantity TEXT, related_event_id INTEGER, document_id INTEGER,
  external_ref TEXT, verification_status TEXT NOT NULL, policy_flags TEXT NOT NULL DEFAULT '', note TEXT,
  budget_policy_version TEXT NOT NULL,
  CHECK (event_type IN ('reservation_created','reservation_released','investment_submitted','investment_finalized',
    'investor_fee_paid','investment_canceled','refund_verified','security_conversion','corporate_action',
    'cash_distribution','sale_proceeds','sale_fee','write_off_observed','residual_holding_update','correction_void')),
  UNIQUE (event_type, external_ref));
"""


V3_APPEND_ONLY = ["access_attempts", "source_checks", "assessments", "criterion_results", "calculations",
                  "support_checks", "forecast_definitions", "forecast_lineage", "stage_usage"]

V3_SQL = """
CREATE TABLE IF NOT EXISTS access_attempts (     -- Workstream A: every platform access attempt, success or not
  attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, attempted_utc TEXT NOT NULL, url TEXT NOT NULL, method TEXT NOT NULL,
  http_status INTEGER, final_url TEXT, result TEXT NOT NULL, content_available TEXT NOT NULL, visibility TEXT NOT NULL,
  challenge_state TEXT NOT NULL, login_state TEXT NOT NULL, capture TEXT NOT NULL, content_sha256 TEXT,
  n_bytes INTEGER, markers TEXT, note TEXT);

CREATE TABLE IF NOT EXISTS source_checks (       -- freshness: a source counts as checked only when the check succeeded
  check_id INTEGER PRIMARY KEY AUTOINCREMENT, offering_id TEXT, source TEXT NOT NULL, checked_utc TEXT NOT NULL,
  success INTEGER NOT NULL CHECK (success IN (0,1)), covers_from_utc TEXT, covers_to_utc TEXT, detail TEXT);

CREATE TABLE IF NOT EXISTS assessments (         -- four separate dimensions; one row per (analysis, classifier version)
  assessment_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER NOT NULL, classifier_version TEXT NOT NULL,
  policy_version TEXT NOT NULL, created_utc TEXT NOT NULL,
  assessment TEXT NOT NULL CHECK (assessment IN ('fails_current_screen','passes_current_screen','indeterminate','analysis_failed')),
  evidence_completeness TEXT NOT NULL CHECK (evidence_completeness IN ('sufficient_for_current_conclusion','material_gaps','extraction_incomplete')),
  operational_readiness TEXT NOT NULL CHECK (operational_readiness IN ('available_verified','availability_unknown','unavailable_or_closed','not_checked')),
  budget_status TEXT NOT NULL CHECK (budget_status IN ('eligible','ineligible','incomplete_cost_information')),
  decisive_criteria TEXT NOT NULL, reasons TEXT NOT NULL, unresolved_criteria TEXT, freshness TEXT, notes TEXT);

CREATE TABLE IF NOT EXISTS criterion_results (
  row_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER NOT NULL, criterion_id TEXT NOT NULL, gate TEXT NOT NULL,
  required INTEGER NOT NULL, model_result TEXT NOT NULL, final_result TEXT NOT NULL
  CHECK (final_result IN ('pass','fail','unresolved')), support TEXT NOT NULL, claim_ids TEXT, reason_ko TEXT,
  validator_notes TEXT);

CREATE TABLE IF NOT EXISTS calculations (        -- deterministic, in code; provenance for every input
  calc_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER, pack_id TEXT, calc_type TEXT NOT NULL,
  formula TEXT NOT NULL, inputs TEXT NOT NULL, assumptions TEXT, included_instruments TEXT, excluded_instruments TEXT,
  units TEXT NOT NULL, result_value REAL, result_kind TEXT NOT NULL CHECK (result_kind IN ('computed','illustrative','withheld')),
  withheld_reason TEXT, calculator_version TEXT NOT NULL, created_utc TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS support_checks (      -- structured claim-support checks (model judgment or human)
  row_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER NOT NULL, claim_id TEXT NOT NULL, checker TEXT NOT NULL,
  judgment_label TEXT NOT NULL, citation_exists INTEGER, passage_supports TEXT NOT NULL, omitted_qualifications TEXT,
  evidence_type TEXT, conflicts TEXT, overstatement TEXT, verdict TEXT NOT NULL, note TEXT, checked_utc TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS forecast_definitions (-- v2.1 structured definition for a prediction row (originals untouched)
  prediction_id INTEGER PRIMARY KEY, analysis_id INTEGER, schema_version TEXT NOT NULL,
  target_type TEXT NOT NULL CHECK (target_type IN ('event_occurs','issuer_announces','independently_corroborated')),
  target_scope TEXT NOT NULL, deadline_utc TEXT NOT NULL, reporting_lag_days INTEGER NOT NULL, allowed_evidence TEXT NOT NULL,
  rationale TEXT NOT NULL, assumptions TEXT NOT NULL, unknown_treatment TEXT NOT NULL, cancellation_treatment TEXT NOT NULL,
  early_true_allowed INTEGER NOT NULL DEFAULT 1, silence_is_false INTEGER NOT NULL DEFAULT 0 CHECK (silence_is_false = 0));

CREATE TABLE IF NOT EXISTS forecast_lineage (    -- a later, separate, timestamped record; the original stays scorable
  row_id INTEGER PRIMARY KEY AUTOINCREMENT, original_prediction_id INTEGER NOT NULL, successor_prediction_id INTEGER,
  relation TEXT NOT NULL CHECK (relation IN ('redefined_by','split_into','flagged_compound','superseded_definition')),
  created_utc TEXT NOT NULL, reason TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS stage_usage (
  row_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER, run_dir TEXT NOT NULL, stage TEXT NOT NULL,
  attempt TEXT NOT NULL, seconds REAL, input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER,
  cache_creation_tokens INTEGER, cost_estimate_usd REAL,
  cost_label TEXT NOT NULL DEFAULT 'cli_estimated_list_price_equivalent_not_billed', outcome TEXT, n_errors INTEGER);
"""


V4_APPEND_ONLY = ["policy_activations", "rule_findings", "assessments_v3", "thesis_answers"]

V4_SQL = """
CREATE TABLE IF NOT EXISTS policy_activations (   -- a policy becomes ACTIVE only through a user-confirmed row here
  activation_id INTEGER PRIMARY KEY AUTOINCREMENT, policy_kind TEXT NOT NULL, policy_version TEXT NOT NULL,
  policy_sha256 TEXT NOT NULL, activated_utc TEXT NOT NULL, statement TEXT NOT NULL,
  actor TEXT NOT NULL CHECK (actor = 'user'), user_confirmed INTEGER NOT NULL CHECK (user_confirmed = 1));

CREATE TABLE IF NOT EXISTS rule_findings (
  row_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER NOT NULL, rule_id TEXT NOT NULL, rule_text TEXT NOT NULL,
  policy_version TEXT NOT NULL, policy_sha256 TEXT NOT NULL, policy_state TEXT NOT NULL,
  model_result TEXT NOT NULL, final_result TEXT NOT NULL
  CHECK (final_result IN ('adverse_decisive','adverse_contributing','not_adverse','unknown','not_applicable')),
  scope TEXT, independently_decisive INTEGER NOT NULL, facts TEXT NOT NULL, interpretation_ko TEXT, counterevidence TEXT,
  unresolved_ko TEXT, what_would_change_ko TEXT, validator_notes TEXT);

CREATE TABLE IF NOT EXISTS assessments_v3 (
  assessment_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER NOT NULL, classifier_version TEXT NOT NULL,
  policy_version TEXT NOT NULL, policy_sha256 TEXT NOT NULL, policy_state TEXT NOT NULL CHECK (policy_state IN ('proposed','active')),
  screening TEXT NOT NULL CHECK (screening IN ('provisional_reject','provisional_eligible_for_review','provisional_unresolved',
                                               'reject','eligible_for_review','unresolved','analysis_failed')),
  evidence_status TEXT NOT NULL CHECK (evidence_status IN ('sufficient_for_named_decision','insufficient','conflicting')),
  evidence_scope TEXT NOT NULL, thesis_status TEXT NOT NULL CHECK (thesis_status IN ('supported','incomplete','contradicted')),
  thesis_notes TEXT, execution TEXT NOT NULL, budget TEXT NOT NULL, decisive TEXT NOT NULL, created_utc TEXT NOT NULL, notes TEXT);

CREATE TABLE IF NOT EXISTS thesis_answers (
  row_id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER NOT NULL, question_id TEXT NOT NULL, status TEXT NOT NULL,
  answer_ko TEXT NOT NULL, claim_ids TEXT NOT NULL, validator_notes TEXT);
"""


def _append_only(tables: list[str]) -> str:
    return "\n".join(
        f"""CREATE TRIGGER IF NOT EXISTS {t}_no_update BEFORE UPDATE ON {t}
            BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS {t}_no_delete BEFORE DELETE ON {t}
            BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END;""" for t in tables)


def _v2_triggers() -> str:
    return _append_only(V2_APPEND_ONLY)


def migrations() -> list[tuple[int, str, str]]:
    from .db import SCHEMA, TRIGGERS
    return [(1, "v1 prospective pilot schema (baseline)", SCHEMA + TRIGGERS),
            (2, "v2 LLM analyst, screening, approvals, ledger, evaluation", V2_SQL + _v2_triggers()),
            (3, "v2.1 access log, assessments, calculations, support checks, forecast definitions, usage",
             V3_SQL + _append_only(V3_APPEND_ONLY)),
            (4, "v2.2 policy activations, rule findings (decision chain), assessments_v3, thesis answers",
             V4_SQL + _append_only(V4_APPEND_ONLY))]


def migrate(con: sqlite3.Connection, db_path: str | Path, backup_dir: str | Path | None) -> dict:
    con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, description TEXT, "
                "applied_utc TEXT NOT NULL, script_sha256 TEXT NOT NULL, backup_path TEXT)")
    applied = {r[0] for r in con.execute("SELECT version FROM schema_migrations")}
    pending = [m for m in migrations() if m[0] not in applied]
    if not pending:
        return {"applied": [], "backup": None}
    has_data = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT IN "
                           "('schema_migrations','sqlite_sequence')").fetchone()[0] > 0
    backup = None
    if has_data and backup_dir and str(db_path) != ":memory:":
        bdir = Path(backup_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = bdir / f"{Path(db_path).stem}_before_v{pending[0][0]}_{stamp}.sqlite"
        dst = sqlite3.connect(str(backup))
        con.backup(dst)
        dst.close()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    for version, desc, script in pending:
        con.executescript(script)
        con.execute("INSERT INTO schema_migrations VALUES (?,?,?,?,?)",
                    (version, desc, now, hashlib.sha256(script.encode()).hexdigest(), str(backup) if backup else None))
    con.commit()
    return {"applied": [m[0] for m in pending], "backup": str(backup) if backup else None}
