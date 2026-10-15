"""Versioned, non-destructive schema migrations with a pre-migration backup.

* Migration 1 is the v1 pilot schema (unchanged). A database created by v1 (without `schema_migrations`) adopts it
  as already applied.
* Migration 2 adds the v2 tables: analysis, screening, approvals, ledger and evaluation.

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


def _v2_triggers() -> str:
    return "\n".join(
        f"""CREATE TRIGGER IF NOT EXISTS {t}_no_update BEFORE UPDATE ON {t}
            BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS {t}_no_delete BEFORE DELETE ON {t}
            BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END;""" for t in V2_APPEND_ONLY)


def migrations() -> list[tuple[int, str, str]]:
    from .db import SCHEMA, TRIGGERS
    return [(1, "v1 prospective pilot schema (baseline)", SCHEMA + TRIGGERS),
            (2, "v2 LLM analyst, screening, approvals, ledger, evaluation", V2_SQL + _v2_triggers())]


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
