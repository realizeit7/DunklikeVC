"""SQLite schema for the prospective pilot.

Append-only tables (documents, facts, decisions, decision_evidence, predictions, prediction_resolutions,
events, pilot_clock) are protected by triggers: UPDATE/DELETE aborts. Corrections are new rows.
`offerings` is the discovery ledger's current-state table; every state change is also logged in
`offering_status_log`.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS pilot_clock (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, set_utc TEXT NOT NULL, run_id TEXT);

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY, command TEXT NOT NULL, started_utc TEXT NOT NULL, finished_utc TEXT,
  config_sha TEXT, network_requests INTEGER DEFAULT 0, cache_hits INTEGER DEFAULT 0, errors INTEGER DEFAULT 0,
  status TEXT, notes TEXT);

CREATE TABLE IF NOT EXISTS gaps (
  gap_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, utc TEXT NOT NULL, offering_id TEXT,
  kind TEXT NOT NULL,      -- access_blocked | http_error | index_unavailable | parse_failure | budget_exhausted | not_disclosed
  url TEXT, detail TEXT);

CREATE TABLE IF NOT EXISTS index_days (   -- which EDGAR daily-index days were scanned completely
  day TEXT PRIMARY KEY, scanned_utc TEXT NOT NULL, run_id TEXT, n_form_c INTEGER, n_republic INTEGER, status TEXT);

CREATE TABLE IF NOT EXISTS discovery_ledger (  -- every Republic Reg CF filing seen (incl. withdrawn/excluded)
  accession TEXT PRIMARY KEY, form TEXT, issuer_cik TEXT, offering_file_number TEXT, filing_date TEXT,
  acceptance_utc TEXT, intermediary_cik TEXT, intermediary_file_number TEXT, first_observed_utc TEXT,
  run_id TEXT, source TEXT, offering_id TEXT);

CREATE TABLE IF NOT EXISTS offerings (
  offering_id TEXT PRIMARY KEY,           -- RCF-{issuer_cik}-{offering_file_number}
  issuer_id TEXT NOT NULL,                -- issuer CIK (10 digits)
  offering_file_number TEXT NOT NULL,
  legal_name TEXT, aliases TEXT, platform_ids TEXT,
  intermediary_cik TEXT, intermediary_file_number TEXT,
  initial_accession TEXT, initial_filing_date TEXT, initial_acceptance_utc TEXT,
  amendment_accessions TEXT DEFAULT '',
  cohort TEXT NOT NULL,                   -- inception | initial_watchlist | pre_start_not_watchlisted
  eligibility TEXT NOT NULL,              -- eligible | excluded
  eligibility_reason TEXT,
  security_class TEXT, security_evidence TEXT,
  deadline_date TEXT,
  first_observed_utc TEXT NOT NULL, first_observed_run TEXT, discovery_source TEXT,
  availability_status TEXT NOT NULL DEFAULT 'unknown',   -- unknown | open_verified | closed_reported | withdrawn
  availability_evidence TEXT,
  closing_status TEXT NOT NULL DEFAULT 'none_reported', -- none_reported | close_reported_c_u | withdrawn_c_w
  captured_utc TEXT,
  last_check_utc TEXT, last_check_ok INTEGER, next_check_due_utc TEXT,
  UNIQUE (issuer_id, offering_file_number));

CREATE TABLE IF NOT EXISTS offering_status_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT, offering_id TEXT, utc TEXT, run_id TEXT, field TEXT,
  old_value TEXT, new_value TEXT, evidence TEXT);

CREATE TABLE IF NOT EXISTS documents (   -- one row per retrieval/check record (immutable)
  document_id INTEGER PRIMARY KEY AUTOINCREMENT,
  offering_id TEXT, issuer_cik TEXT, accession TEXT, source_url TEXT NOT NULL,
  source_type TEXT NOT NULL,   -- sec_filing_index | sec_primary_xml | sec_attachment | sec_submissions_json | platform_page | user_import
  visibility TEXT NOT NULL DEFAULT 'public',   -- public | private
  description TEXT,
  claimed_publication_date TEXT,     -- e.g. SEC filing date, or date displayed on a page
  verified_public_date TEXT,         -- e.g. EDGAR acceptance timestamp (public dissemination)
  economic_period TEXT,
  retrieved_utc TEXT NOT NULL,       -- this retrieval/check (also "observed" time for leakage rules)
  first_observed_utc TEXT NOT NULL,  -- first retrieval of identical content from this URL
  sha256 TEXT, blob_path TEXT, bytes INTEGER, content_type TEXT, http_status INTEGER,
  extraction_method TEXT, parse_status TEXT, access_error TEXT, run_id TEXT);

CREATE TABLE IF NOT EXISTS facts (       -- append-only; corrections supersede
  fact_id INTEGER PRIMARY KEY AUTOINCREMENT, offering_id TEXT NOT NULL, document_id INTEGER,
  fact_kind TEXT NOT NULL,           -- source_statement | extracted_fact
  field TEXT NOT NULL, value TEXT,   -- NULL value => missing (never 0)
  unit TEXT, currency TEXT, financial_period TEXT, locator TEXT,
  extraction_method TEXT,
  verification_status TEXT NOT NULL, -- structured_form_field_issuer_reported | text_regex_unreviewed | user_verified_against_source | missing
  missing_reason TEXT, observed_utc TEXT NOT NULL, supersedes_fact_id INTEGER, run_id TEXT);

CREATE TABLE IF NOT EXISTS decisions (
  decision_id INTEGER PRIMARY KEY AUTOINCREMENT, offering_id TEXT NOT NULL,
  decision_utc TEXT NOT NULL,                 -- immutable decision timestamp
  kind TEXT NOT NULL,                         -- prospective | retrospective_reconstruction
  evidence_cutoff_utc TEXT NOT NULL,          -- = decision_utc for prospective decisions
  status TEXT NOT NULL,                       -- select | pass | defer | unreviewed
  draft_recommendation TEXT,                  -- AI/analyst draft (never a user selection)
  reasons TEXT, counterarguments TEXT, unresolved_questions TEXT,
  analyst TEXT NOT NULL, user_confirmed INTEGER NOT NULL DEFAULT 0,
  paper_amount_usd REAL, packet_path TEXT, packet_sha256 TEXT,
  CHECK (status IN ('select','pass','defer','unreviewed')),
  CHECK (kind IN ('prospective','retrospective_reconstruction')),
  CHECK (user_confirmed = 1 OR status = 'unreviewed'),
  CHECK (paper_amount_usd IS NULL OR (status = 'select' AND user_confirmed = 1)),
  CHECK (kind = 'retrospective_reconstruction' OR evidence_cutoff_utc = decision_utc));

CREATE TABLE IF NOT EXISTS decision_evidence (
  decision_id INTEGER NOT NULL, document_id INTEGER NOT NULL, PRIMARY KEY (decision_id, document_id));

CREATE TABLE IF NOT EXISTS predictions (
  prediction_id INTEGER PRIMARY KEY AUTOINCREMENT, offering_id TEXT NOT NULL, decision_id INTEGER,
  created_utc TEXT NOT NULL, forecaster TEXT NOT NULL,
  target_event TEXT NOT NULL, event_kind TEXT NOT NULL,   -- business | disclosure
  horizon_months INTEGER NOT NULL, deadline_utc TEXT NOT NULL, probability REAL NOT NULL,
  resolution_rule TEXT NOT NULL, reporting_lag_days INTEGER NOT NULL, missing_evidence_treatment TEXT NOT NULL,
  permitted_evidence TEXT, revises_prediction_id INTEGER,
  CHECK (probability >= 0 AND probability <= 1), CHECK (event_kind IN ('business','disclosure')));

CREATE TABLE IF NOT EXISTS prediction_resolutions (
  resolution_id INTEGER PRIMARY KEY AUTOINCREMENT, prediction_id INTEGER NOT NULL, resolved_utc TEXT NOT NULL,
  outcome TEXT NOT NULL, evidence TEXT, adjudicator TEXT,
  CHECK (outcome IN ('true','false','unresolved_unknown')));

CREATE TABLE IF NOT EXISTS events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT, offering_id TEXT, issuer_cik TEXT, event_type TEXT NOT NULL,
  security TEXT, event_date TEXT, event_date_low TEXT, event_date_high TEXT, publication_date TEXT,
  observed_utc TEXT NOT NULL, source_document_id INTEGER, accession TEXT, source_claim TEXT,
  interpretation TEXT, conflict_status TEXT DEFAULT 'none', uncertainty TEXT, run_id TEXT,
  UNIQUE (offering_id, event_type, accession));

CREATE TABLE IF NOT EXISTS review_queue_log (
  entry_id INTEGER PRIMARY KEY AUTOINCREMENT, utc TEXT NOT NULL, week TEXT, offering_id TEXT,
  rule TEXT, position INTEGER, discretionary INTEGER DEFAULT 0, note TEXT);

CREATE TABLE IF NOT EXISTS effort_log (
  entry_id INTEGER PRIMARY KEY AUTOINCREMENT, entered_utc TEXT NOT NULL, activity_date TEXT NOT NULL,
  minutes REAL NOT NULL, activity TEXT NOT NULL, note TEXT, CHECK (minutes >= 0));
"""

APPEND_ONLY = ["documents", "facts", "decisions", "decision_evidence", "predictions", "prediction_resolutions",
               "events", "pilot_clock"]

TRIGGERS = "\n".join(
    f"""CREATE TRIGGER IF NOT EXISTS {t}_no_update BEFORE UPDATE ON {t}
        BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END;
        CREATE TRIGGER IF NOT EXISTS {t}_no_delete BEFORE DELETE ON {t}
        BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END;"""
    for t in APPEND_ONLY) + """
CREATE TRIGGER IF NOT EXISTS evidence_not_after_cutoff BEFORE INSERT ON decision_evidence
WHEN (SELECT retrieved_utc FROM documents WHERE document_id = NEW.document_id) >
     (SELECT evidence_cutoff_utc FROM decisions WHERE decision_id = NEW.decision_id)
  OR (SELECT document_id FROM documents WHERE document_id = NEW.document_id) IS NULL
BEGIN SELECT RAISE(ABORT, 'evidence observed after the decision evidence cutoff (or unknown document)'); END;
"""


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    con.executescript(TRIGGERS)
    con.commit()
    return con


def q(con: sqlite3.Connection, sql: str, *args) -> list[sqlite3.Row]:
    return con.execute(sql, args).fetchall()
