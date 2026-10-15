"""v2 budget policy, approvals and ledger — SYNTHETIC fixtures only (logic tests; no real investments)."""
import datetime as dt
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml

from prospective import ledger
from prospective.core import Ctx
from prospective.ledger import add_years, budget_state, cents, check_commitment, load_budget_policy, period_of

CFG = Path(__file__).resolve().parents[2] / "prospective" / "config.yaml"
POL = load_budget_policy()


@pytest.fixture
def ctx(tmp_path):
    cfg = yaml.safe_load(CFG.read_text())
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg))
    c = Ctx(tmp_path / "config.yaml", "test", now="2027-03-01T15:00:00+00:00", offline=True)
    c.tmp = tmp_path
    return c


def offering(c, oid, cik, deadline="2030-12-31"):
    c.con.execute("""INSERT INTO offerings(offering_id, issuer_id, offering_file_number, legal_name, initial_accession, cohort,
        eligibility, first_observed_utc, availability_status, closing_status, deadline_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                  (oid, cik, oid[-9:], "Synthetic " + oid, "acc-" + oid, "inception", "eligible", c.now(), "unknown",
                   "none_reported", deadline))
    c.con.commit()


def analysis(c, oid, status="passes_research_screen", cutoff=None):
    pid = f"pack-{oid}"
    c.con.execute("INSERT OR IGNORE INTO evidence_packs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (pid, oid, "v1", cutoff or c.now(), c.now(), "sha", "p", "[]", 0, "[]", "{}"))
    cur = c.con.execute("""INSERT INTO analysis_runs(offering_id, pack_id, pack_sha256, version_id, prompt_version, schema_version,
        policy_version, adapter, started_utc, finished_utc, status, split) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (oid, pid, "sha", "v", "p1", "s1", "screening_policy_v1", "fixture", c.now(), c.now(), status, "evaluation"))
    c.con.commit()
    return cur.lastrowid


def ready(c, oid, cik):
    offering(c, oid, cik)
    ledger.confirm_issuer(c, cik, f"CIK{int(cik)}", "synthetic")
    if not ledger.policy_acknowledged(c, "screening", "screening_policy_v1", ledger.SCREENING_POLICY):
        ledger.acknowledge_policy(c, "screening", "screening_policy_v1", ledger.SCREENING_POLICY, "synthetic test ack")
    return analysis(c, oid)


def approve(c, oid, cik, amount, fee="0", **kw):
    a = kw.pop("analysis_id", None) or ready(c, oid, cik)
    args = dict(offering_id=oid, amount_usd=amount, fee_usd=fee, fee_basis="confirmed", issuer_key_confirmed=f"CIK{int(cik)}",
                analysis_id=a, min_investment_usd="100", applicable_terms="Crowd SAFE, $10M post-money cap (synthetic)",
                availability_note="synthetic: page checked", contract_document_id=1)
    args.update(kw)
    return ledger.approve(c, **args)


def st(c, at=None):
    return ledger.current_state(c, at)


# ---- limits, fees and simultaneous reservations -------------------------------------------------------
def test_issuer_limit_with_fees_and_simultaneous_reservations(ctx):
    r1 = approve(ctx, "O1", "0000000001", "600", fee="10")
    assert r1["status"] == "executable"
    r2 = approve(ctx, "O1", "0000000001", "590", fee="0.01", analysis_id=analysis(ctx, "O1"))   # 610 + 590.01 > 1200
    assert r2["status"] == "blocked" and not r2["budget"]["issuer_ok"]
    r3 = approve(ctx, "O1", "0000000001", "590", fee="0", analysis_id=analysis(ctx, "O1"))      # exactly 1200 allowed
    assert r3["status"] == "executable"
    assert st(ctx).issuer_used_cents["CIK1"] == cents("1200")


def test_annual_limit_across_issuers(ctx):
    for i in range(10):
        assert approve(ctx, f"A{i}", f"00000001{i:02d}", "1200")["status"] == "executable"
    assert st(ctx).annual_used_cents == cents("12000") and st(ctx).period_label == "pre_start"
    r = approve(ctx, "A99", "0000000199", "1")
    assert r["status"] == "blocked" and not r["budget"]["annual_ok"]


def test_settlement_does_not_double_count(ctx):
    a = approve(ctx, "O1", "0000000001", "1000", fee="20")
    e = ledger.record_event(ctx, event_type="investment_submitted", offering_id="O1", effective_date="2027-03-02",
                            amount_usd="1000", fee_usd="20", approval_id=a["approval_id"], external_ref="CONF-1")
    s = st(ctx, "2027-03-03T15:00:00+00:00")
    assert e["flags"] == "" and s.annual_used_cents == cents("1020") and s.issuer_used_cents["CIK1"] == cents("1020")
    assert s.active_reservation_cents == 0 and s.period_label == "P1" and s.anchor == dt.date(2027, 3, 2)


# ---- periods ---------------------------------------------------------------------------------------------
def test_anniversary_rollover_pre_start_and_leap_day():
    assert add_years(dt.date(2028, 2, 29), 1) == dt.date(2029, 2, 28) and add_years(dt.date(2028, 2, 29), 4) == dt.date(2032, 2, 29)
    a = dt.date(2027, 3, 15)
    assert period_of(None, dt.date(2027, 1, 1))[0] == "pre_start"
    assert period_of(a, dt.date(2027, 3, 14))[0] == "pre_start"
    assert period_of(a, dt.date(2027, 3, 15))[:2] == ("P1", a)
    assert period_of(a, dt.date(2028, 3, 14))[0] == "P1" and period_of(a, dt.date(2028, 3, 15))[0] == "P2"


def test_pending_reservation_counts_in_new_period_and_settles_once(ctx):
    a1 = approve(ctx, "O1", "0000000001", "1000")
    ledger.record_event(ctx, event_type="investment_submitted", offering_id="O1", effective_date="2027-03-02",
                        amount_usd="1000", approval_id=a1["approval_id"], external_ref="C1")
    ctx._now = "2028-02-28T15:00:00+00:00"   # late in P1: approve a second issuer, still pending at the anniversary
    a2 = approve(ctx, "O2", "0000000002", "500", expiry_days=30)
    s = st(ctx, "2028-03-05T15:00:00+00:00")   # P2 started 2028-03-02; reservation still pending
    assert s.period_label == "P2" and s.annual_funded_cents == 0 and s.annual_used_cents == cents("500")
    ctx._now = "2028-03-05T15:00:00+00:00"
    ledger.record_event(ctx, event_type="investment_submitted", offering_id="O2", effective_date="2028-03-05",
                        amount_usd="500", approval_id=a2["approval_id"], external_ref="C2")
    s = st(ctx, "2028-03-06T15:00:00+00:00")
    assert s.annual_used_cents == cents("500") and s.active_reservation_cents == 0   # counted once, in P2
    assert st(ctx, "2028-03-01T15:00:00+00:00").annual_funded_cents == cents("1000")  # P1 unchanged


# ---- refunds, distributions, losses, sales -----------------------------------------------------------------
def test_refund_restores_only_refunded_cost_in_original_period(ctx):
    a = approve(ctx, "O1", "0000000001", "1000", fee="30")
    inv = ledger.record_event(ctx, event_type="investment_submitted", offering_id="O1", effective_date="2027-03-02",
                              amount_usd="1000", fee_usd="30", approval_id=a["approval_id"], external_ref="C1")
    ledger.record_event(ctx, event_type="investment_canceled", offering_id="O1", effective_date="2027-03-10",
                        related_event_id=inv["event_id"])
    assert st(ctx, "2027-03-11T15:00:00+00:00").issuer_used_cents["CIK1"] == cents("1030")   # cancellation alone: still counted
    ledger.record_event(ctx, event_type="refund_verified", offering_id="O1", effective_date="2028-04-01", amount_usd="1000",
                        related_event_id=inv["event_id"], external_ref="R1", verification_status="document_verified")
    s1 = st(ctx, "2027-06-01T15:00:00+00:00")
    s2 = st(ctx, "2028-04-02T15:00:00+00:00")
    assert s1.issuer_used_cents["CIK1"] == cents("30")      # non-refunded fee stays counted
    assert s1.annual_funded_cents == cents("30")           # refund attributed to the original period P1
    assert s2.period_label == "P2" and s2.annual_funded_cents == 0   # no extra P2 capacity


def test_distributions_sales_and_writeoffs_do_not_restore_budget(ctx):
    a = approve(ctx, "O1", "0000000001", "1200")
    inv = ledger.record_event(ctx, event_type="investment_submitted", offering_id="O1", effective_date="2027-03-02",
                              amount_usd="1200", approval_id=a["approval_id"], external_ref="C1")
    for t, amt in [("cash_distribution", "300"), ("sale_proceeds", "2000"), ("sale_fee", "20"), ("write_off_observed", "0")]:
        ledger.record_event(ctx, event_type=t, offering_id="O1", effective_date="2028-01-01", amount_usd=amt,
                            related_event_id=inv["event_id"], external_ref=f"X-{t}")
    s = st(ctx, "2028-01-02T15:00:00+00:00")
    assert s.issuer_used_cents["CIK1"] == cents("1200") and s.annual_funded_cents == cents("1200")
    r = approve(ctx, "O1b", "0000000001", "1", analysis_id=None)   # issuer limit not reset after sale/write-off
    assert r["status"] == "blocked"
    p = [x for x in ledger.positions(ctx) if x["offering_id"] == "O1"][0]
    assert p["distributions_cents"] == cents("300") and p["sale_proceeds_net_cents"] == cents("1980")


def test_same_issuer_across_rounds_and_spv(ctx):
    approve(ctx, "R1", "0000000005", "800")
    offering(ctx, "SPV1", "0000000777")
    ledger.confirm_issuer(ctx, "0000000777", "CIK5", "SPV holds only issuer CIK5 securities (synthetic)")
    r = approve(ctx, "SPV1", "0000000777", "500", issuer_key_confirmed="CIK5", analysis_id=analysis(ctx, "SPV1"))
    assert r["status"] == "blocked" and r["budget"]["issuer_after"] == cents("1300")


# ---- imports, expiry, changed terms, out-of-policy -----------------------------------------------------------
def test_duplicate_confirmation_import_is_idempotent(ctx):
    a = approve(ctx, "O1", "0000000001", "500")
    kw = dict(event_type="investment_submitted", offering_id="O1", effective_date="2027-03-02", amount_usd="500",
              approval_id=a["approval_id"], external_ref="REPUBLIC-TX-123")
    e1, e2 = ledger.record_event(ctx, **kw), ledger.record_event(ctx, **kw)
    assert e2["duplicate"] and e1["event_id"] == e2["event_id"]
    assert ctx.con.execute("SELECT COUNT(*) FROM ledger_events WHERE event_type='investment_submitted'").fetchone()[0] == 1


def test_expired_approval_releases_and_late_execution_is_flagged(ctx):
    a = approve(ctx, "O1", "0000000001", "500", expiry_days=3)
    assert st(ctx, "2027-03-02T15:00:00+00:00").active_reservation_cents == cents("500")
    assert st(ctx, "2027-03-05T15:00:00+00:00").active_reservation_cents == 0
    ctx._now = "2027-03-06T15:00:00+00:00"
    e = ledger.record_event(ctx, event_type="investment_submitted", offering_id="O1", effective_date="2027-03-06",
                            amount_usd="500", approval_id=a["approval_id"], external_ref="C1")
    assert "APPROVAL_EXPIRED" in e["flags"]


def test_changed_terms_since_analysis_block_and_original_is_preserved(ctx):
    aid = ready(ctx, "O1", "0000000001")
    ctx.con.execute("INSERT INTO events(offering_id, event_type, observed_utc, accession) VALUES (?,?,?,?)",
                    ("O1", "offering_amendment_filed", "2027-03-02T00:00:00+00:00", "acc-amend"))
    ctx._now = "2027-03-03T15:00:00+00:00"
    r = approve(ctx, "O1", "0000000001", "500", analysis_id=aid)
    assert r["status"] == "blocked" and any("fresh review" in b for b in r["blockers"])
    assert ctx.con.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0] == 0
    assert ctx.con.execute("SELECT status FROM approvals WHERE approval_id=?", (r["approval_id"],)).fetchone()[0] == "blocked"


def test_unknown_fee_makes_approval_incomplete_without_reservation(ctx):
    r = approve(ctx, "O1", "0000000001", "500", fee=None, fee_basis=None)
    assert r["status"] == "incomplete" and ctx.con.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0] == 0


def test_out_of_policy_actual_transaction_is_recorded_and_flagged(ctx):
    offering(ctx, "O1", "0000000001")
    e = ledger.record_event(ctx, event_type="investment_submitted", offering_id="O1", effective_date="2027-03-02",
                            amount_usd="5000", fee_usd="50", external_ref="C-OUT")
    row = ctx.con.execute("SELECT amount_cents, fee_cents, policy_flags FROM ledger_events WHERE event_id=?", (e["event_id"],)).fetchone()
    assert row["amount_cents"] == 500000 and "OUT_OF_POLICY:issuer_limit" in row["policy_flags"] and "NO_APPROVAL" in row["policy_flags"]


# ---- AI cannot approve or move money; ledger immutability ---------------------------------------------------
def test_ai_assessment_cannot_create_approval_or_money(ctx):
    offering(ctx, "O1", "0000000001")
    analysis(ctx, "O1", "passes_research_screen")
    assert ctx.con.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
    assert ctx.con.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0] == 0
    with pytest.raises(sqlite3.IntegrityError):   # an approval row must be user-confirmed
        ctx.con.execute("INSERT INTO approvals(offering_id, issuer_key, amount_cents, terms, availability_note, approved_utc, "
                        "expires_utc, status, checks, budget_policy_version, user_confirmed) VALUES "
                        "('O1','CIK1',100,'{}','x','t','t','executable','{}','v',0)")
    # without a policy acknowledgment even a user approval cannot reserve budget
    ledger.confirm_issuer(ctx, "0000000001", "CIK1", "synthetic")
    r = ledger.approve(ctx, offering_id="O1", amount_usd="100", fee_usd="0", fee_basis="confirmed", issuer_key_confirmed="CIK1",
                       analysis_id=1, min_investment_usd="100", applicable_terms="x", availability_note="x", contract_document_id=1)
    assert r["status"] == "blocked" and ctx.con.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0] == 0


def test_failed_screen_requires_override_rationale_and_records_conditions(ctx):
    aid = ready(ctx, "O1", "0000000001")
    bad = analysis(ctx, "O1", "needs_information")
    ctx.con.execute("INSERT INTO analysis_gates(analysis_id, gate, result, source) VALUES (?,?,?,?)", (bad, "evidence_sufficiency", "unknown", "llm"))
    assert approve(ctx, "O1", "0000000001", "100", analysis_id=bad)["status"] == "blocked"
    r = approve(ctx, "O1", "0000000001", "100", analysis_id=bad, override_rationale="read the contract myself (synthetic)")
    row = ctx.con.execute("SELECT override_failed_conditions, override_rationale FROM approvals WHERE approval_id=?",
                          (r["approval_id"],)).fetchone()
    assert r["status"] == "executable" and "evidence_sufficiency" in row[0] and row[1]


def test_ledger_and_approvals_are_append_only(ctx):
    a = approve(ctx, "O1", "0000000001", "100")
    for sql in ["UPDATE ledger_events SET amount_cents=0", "DELETE FROM ledger_events", "UPDATE approvals SET status='blocked'"]:
        with pytest.raises(sqlite3.IntegrityError):
            ctx.con.execute(sql)
    e = ledger.record_event(ctx, event_type="investment_submitted", offering_id="O1", effective_date="2027-03-02",
                            amount_usd="100", approval_id=a["approval_id"], external_ref="C1")
    ledger.void_event(ctx, e["event_id"], "entered against the wrong offering (synthetic)")
    s = st(ctx, "2027-03-03T15:00:00+00:00")
    # the mistaken investment no longer counts; the approval's reservation is active again (not counted twice)
    assert s.annual_funded_cents == 0 and s.active_reservation_cents == cents("100") and s.issuer_used_cents["CIK1"] == cents("100")
    assert ctx.con.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0] == 3   # history kept


def test_realized_multiple_only_when_exited(ctx):
    a = approve(ctx, "O1", "0000000001", "1000")
    inv = ledger.record_event(ctx, event_type="investment_submitted", offering_id="O1", effective_date="2027-03-02",
                              amount_usd="1000", approval_id=a["approval_id"], external_ref="C1", security="safe")
    ledger.record_event(ctx, event_type="security_conversion", offering_id="O1", effective_date="2028-01-01", quantity="400",
                        security="safe", external_ref="CONV1", related_event_id=inv["event_id"])
    p = [x for x in ledger.positions(ctx) if x["offering_id"] == "O1"][0]
    assert p["realized_multiple"] is None and "conversion is not cash" in p["realized_note"]


def test_migration_backup_preserves_prior_records(tmp_path):
    from prospective import db
    from prospective.db import SCHEMA, TRIGGERS
    v1 = tmp_path / "v1.sqlite"
    con = sqlite3.connect(v1)
    con.executescript(SCHEMA + TRIGGERS)   # a database created by v1 (no schema_migrations table)
    con.execute("INSERT INTO pilot_clock VALUES ('pilot_start_utc','2026-10-14T15:16:34+00:00','t','r')")
    con.execute("INSERT INTO decisions(offering_id, decision_utc, kind, evidence_cutoff_utc, status, analyst, user_confirmed) "
                "VALUES ('O','2026-10-15T00:00:00+00:00','prospective','2026-10-15T00:00:00+00:00','pass','user',1)")
    con.commit()
    con.close()
    c2 = db.connect(v1, tmp_path / "backups")
    assert c2.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 1
    assert [r[0] for r in c2.execute("SELECT version FROM schema_migrations ORDER BY 1")] == [1, 2, 3]
    b = list((tmp_path / "backups").glob("*.sqlite"))
    assert len(b) == 1 and sqlite3.connect(b[0]).execute("SELECT status FROM decisions").fetchone()[0] == "pass"
    with pytest.raises(sqlite3.IntegrityError):
        c2.execute("UPDATE pilot_clock SET value='2025-01-01'")
