"""Prospective pilot failure-mode tests on SYNTHETIC fixtures only (fake EDGAR responses, no network).

They verify logic, not the accuracy of any live record.
"""
import csv
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
import yaml

from personal_vc_research.http import FetchResult
from prospective import collect, discover, journal, outputs
from prospective.core import Ctx, next_check_due, start_clock
from prospective.extract import form_c_facts, parse_xml

CFG = Path(__file__).resolve().parents[2] / "prospective" / "config.yaml"
REPUBLIC = "0001751525"


def form_c_xml(name="Synthetic Widgets Inc", inter_cik=REPUBLIC, sec_type="Other", desc="Crowd SAFE", revenue="12000.00",
               deadline="12-31-2030") -> bytes:
    rev = f"<revenueMostRecentFiscalYear>{revenue}</revenueMostRecentFiscalYear>" if revenue is not None else ""
    return f"""<edgarSubmission><formData><issuerInformation><issuerInfo><nameOfIssuer>{name}</nameOfIssuer>
      <issuerWebsite>https://example.invalid</issuerWebsite></issuerInfo>
      <companyName>OpenDeal Portal LLC</companyName><commissionCik>{inter_cik}</commissionCik>
      <commissionFileNumber>007-00167</commissionFileNumber></issuerInformation>
      <offeringInformation><securityOfferedType>{sec_type}</securityOfferedType>
      <securityOfferedOtherDesc>{desc}</securityOfferedOtherDesc><deadlineDate>{deadline}</deadlineDate></offeringInformation>
      <annualReportDisclosureRequirements>{rev}</annualReportDisclosureRequirements></formData></edgarSubmission>""".encode()


class FakeFetcher:
    """Serves synthetic bytes per URL; unknown URLs return 404; `fail` maps URL -> status."""

    def __init__(self, tmp: Path, pages: dict, fail: dict | None = None, clock=lambda: "2030-01-01T00:00:00+00:00"):
        self.tmp, self.pages, self.fail, self.clock = tmp, pages, fail or {}, clock
        self.network_requests = 0

    def get(self, url, source_kind="", use_cache=True):
        self.network_requests += 1
        if url in self.fail:
            return FetchResult(url, None, None, self.fail[url], self.clock(), False)
        keys = [k for k in self.pages if k == url] + [k for k in self.pages if k.endswith("*") and url.startswith(k[:-1])]
        for k in keys[:1]:
            v = self.pages[k]
            if True:
                p = self.tmp / f"f{abs(hash(url))}"
                p.write_bytes(v() if callable(v) else v)
                return FetchResult(url, p, "x", 200, self.clock(), False, "")
        return FetchResult(url, None, None, 404, self.clock(), False)


def submissions(rows):
    keys = ["accessionNumber", "form", "filingDate", "fileNumber", "acceptanceDateTime"]
    return json.dumps({"filings": {"recent": {k: [r[i] for r in rows] for i, k in enumerate(keys)}}}).encode()


@pytest.fixture
def ctx(tmp_path):
    cfg = yaml.safe_load(CFG.read_text())
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg))
    c = Ctx(tmp_path / "config.yaml", "test", now="2030-01-01T00:00:00+00:00", offline=True)
    c.tmp = tmp_path
    return c


def set_now(c, t):
    c._now = t
    if c.fetcher:
        c.fetcher.clock = lambda: c.now()


def add_offering(c, oid="RCF-1-020-1", cik="0000000001", fno="020-1", acc="0000000001-30-000001", cohort="inception"):
    c.con.execute("""INSERT INTO offerings(offering_id, issuer_id, offering_file_number, legal_name, initial_accession,
        initial_filing_date, initial_acceptance_utc, cohort, eligibility, first_observed_utc, availability_status, closing_status,
        next_check_due_utc, amendment_accessions) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (oid, cik, fno, "Synthetic Co", acc, "2030-01-01", "2030-01-01T00:00:00+00:00", cohort, "eligible",
                   c.now(), "unknown", "none_reported", c.now(), ""))
    c.con.commit()
    return oid


# ---- 1. late evidence cannot leak into an earlier decision -----------------------------------------
def test_late_document_cannot_enter_earlier_decision(ctx):
    oid = add_offering(ctx)
    early = ctx.record_document(url="u1", source_type="sec_primary_xml", offering_id=oid, data=b"a",
                                retrieved_utc="2030-01-02T00:00:00+00:00")
    set_now(ctx, "2030-01-03T00:00:00+00:00")
    pkt, _ = journal.build_packet(ctx, oid)
    did = journal.record_decision(ctx, oid, "pass", "user", True, reasons="synthetic", packet=pkt)
    # discovered later, although it claims an earlier publication date
    late = ctx.record_document(url="u2", source_type="user_import", offering_id=oid, data=b"b",
                               retrieved_utc="2030-01-05T00:00:00+00:00", claimed_publication_date="2029-12-01")
    ev = {r[0] for r in ctx.con.execute("SELECT document_id FROM decision_evidence WHERE decision_id=?", (did,))}
    assert ev == {early}
    with pytest.raises(sqlite3.IntegrityError):
        ctx.con.execute("INSERT INTO decision_evidence VALUES (?,?)", (did, late))
    # a retrospective reconstruction may use it, labelled separately, without replacing the original
    set_now(ctx, "2030-01-06T00:00:00+00:00")
    rid = journal.record_decision(ctx, oid, "pass", "user", True, retrospective_as_of="2030-01-05T00:00:00+00:00")
    assert ctx.con.execute("SELECT kind FROM decisions WHERE decision_id=?", (rid,)).fetchone()[0] == "retrospective_reconstruction"
    assert ctx.con.execute("SELECT COUNT(*) FROM decision_evidence WHERE decision_id=?", (did,)).fetchone()[0] == 1


def test_packet_with_later_cutoff_rejected_for_earlier_decision(ctx):
    oid = add_offering(ctx)
    set_now(ctx, "2030-01-10T00:00:00+00:00")
    pkt, _ = journal.build_packet(ctx, oid)
    set_now(ctx, "2030-01-09T00:00:00+00:00")
    with pytest.raises(ValueError):
        journal.record_decision(ctx, oid, "pass", "user", True, packet=pkt)


# ---- 2. immutability --------------------------------------------------------------------------------
def test_snapshots_and_decisions_are_append_only(ctx):
    oid = add_offering(ctx)
    d = ctx.record_document(url="u", source_type="sec_attachment", offering_id=oid, data=b"v1")
    did = journal.record_decision(ctx, oid, "defer", "user", True)
    start_clock(ctx, "2030-01-01T00:00:00+00:00")
    for sql in ["UPDATE documents SET sha256='x' WHERE document_id=%d" % d, "DELETE FROM documents",
                "UPDATE decisions SET status='select' WHERE decision_id=%d" % did, "DELETE FROM decisions",
                "UPDATE pilot_clock SET value='x'"]:
        with pytest.raises(sqlite3.IntegrityError):
            ctx.con.execute(sql)
    # identical content shares bytes but every retrieval is its own record
    d2 = ctx.record_document(url="u", source_type="sec_attachment", offering_id=oid, data=b"v1",
                             retrieved_utc="2030-02-01T00:00:00+00:00")
    r1, r2 = [ctx.con.execute("SELECT * FROM documents WHERE document_id=?", (i,)).fetchone() for i in (d, d2)]
    assert r1["blob_path"] == r2["blob_path"] and r2["first_observed_utc"] == r1["retrieved_utc"]
    # a changed page never overwrites the earlier snapshot
    d3 = ctx.record_document(url="u", source_type="sec_attachment", offering_id=oid, data=b"v2")
    assert ctx.con.execute("SELECT blob_path FROM documents WHERE document_id=?", (d3,)).fetchone()[0] != r1["blob_path"]
    assert (ctx.root / r1["blob_path"]).read_bytes() == b"v1"


def test_ai_draft_cannot_be_a_user_selection(ctx):
    oid = add_offering(ctx)
    with pytest.raises(ValueError):
        journal.record_decision(ctx, oid, "select", "claude-draft", False)
    with pytest.raises(sqlite3.IntegrityError):
        ctx.con.execute("INSERT INTO decisions(offering_id, decision_utc, kind, evidence_cutoff_utc, status, analyst, user_confirmed)"
                        " VALUES (?,?,?,?,?,?,0)", (oid, ctx.now(), "prospective", ctx.now(), "select", "claude-draft"))
    with pytest.raises(sqlite3.IntegrityError):   # paper amount only for a user-confirmed selection
        journal.record_decision(ctx, oid, "pass", "user", True, paper_amount_usd=100.0)
    did = journal.record_decision(ctx, oid, "unreviewed", "claude-draft", False, draft_recommendation="pass (draft)")
    assert ctx.con.execute("SELECT status FROM decisions WHERE decision_id=?", (did,)).fetchone()[0] == "unreviewed"
    assert oid in [o["offering_id"] for o in journal.unreviewed(ctx)]


# ---- 3/4. amendments vs separate rounds ----------------------------------------------------------------
def _discovery_ctx(ctx, sub_rows, extra=None):
    cik = "0000000007"
    pages = {f"https://data.sec.gov/submissions/CIK{cik}.json": lambda: submissions(sub_rows),
             "https://www.sec.gov/Archives/edgar/data/7/*": form_c_xml()}
    pages.update(extra or {})
    ctx.fetcher = FakeFetcher(ctx.tmp, pages, clock=lambda: ctx.now())
    return cik


def test_amendment_does_not_create_duplicate_and_rounds_stay_distinct(ctx):
    rows = [["0000000007-30-000001", "C", "2030-01-01", "020-100", "2030-01-01T15:00:00.000Z"],
            ["0000000007-30-000002", "C/A", "2030-01-02", "020-100", "2030-01-02T15:00:00.000Z"],
            ["0000000007-31-000001", "C", "2031-01-01", "020-200", "2031-01-01T15:00:00.000Z"]]
    cik = _discovery_ctx(ctx, rows, {"https://www.sec.gov/Archives/edgar/data/7/000000000730000002/index.json":
                                     json.dumps({"directory": {"item": [{"name": "primary_doc.xml"}]}}).encode()})
    clock = {"pilot_start_utc": "2029-12-31T00:00:00+00:00"}
    a = discover.register_initial_form_c(ctx, cik, "0000000007-30-000001", "test", clock, False)
    b = discover.register_initial_form_c(ctx, cik, "0000000007-31-000001", "test", clock, False)
    assert a != b and a.endswith("020-100") and b.endswith("020-200")       # separate rounds
    assert discover.register_initial_form_c(ctx, cik, "0000000007-30-000001", "test", clock, False) is None  # idempotent
    o = ctx.con.execute("SELECT * FROM offerings WHERE offering_id=?", (a,)).fetchone()
    collect.check_offering(ctx, o)
    assert ctx.con.execute("SELECT COUNT(*) FROM offerings").fetchone()[0] == 2
    assert ctx.con.execute("SELECT amendment_accessions FROM offerings WHERE offering_id=?", (a,)).fetchone()[0] == "0000000007-30-000002"
    assert ctx.con.execute("SELECT event_type FROM events WHERE offering_id=? AND accession='0000000007-30-000002'",
                           (a,)).fetchone()[0] == "offering_amendment_filed"
    # the other round's Form C is an issuer-level financing event for the first offering, not an amendment
    assert ctx.con.execute("SELECT event_type FROM events WHERE offering_id=? AND accession='0000000007-31-000001'",
                           (a,)).fetchone()[0] == "follow_on_reg_cf_offering_filed"


def test_non_republic_and_excluded_securities(ctx):
    cik = "0000000007"
    ctx.fetcher = FakeFetcher(ctx.tmp, {"https://www.sec.gov/Archives/edgar/data/7/*": form_c_xml(inter_cik="0009999999")})
    ctx.cfg.raw["platform"]["intermediary_file_numbers"] = []
    assert discover.register_initial_form_c(ctx, cik, "0000000007-30-000001", "t", {}, False) is None
    rows = [["0000000007-30-000003", "C", "2030-01-01", "020-300", "2030-01-01T15:00:00.000Z"]]
    _discovery_ctx(ctx, rows, {"https://www.sec.gov/Archives/edgar/data/7/*": form_c_xml(desc="Revenue Share Agreement")})
    oid = discover.register_initial_form_c(ctx, cik, "0000000007-30-000003", "t", {"pilot_start_utc": "2029-01-01T00:00:00+00:00"}, False)
    assert ctx.con.execute("SELECT eligibility, security_class FROM offerings WHERE offering_id=?", (oid,)).fetchone()[:] == \
        ("excluded", "revenue_share")   # kept in the ledger, not dropped


def test_inception_vs_watchlist_cohorts(ctx):
    rows = [["0000000007-30-000001", "C", "2030-01-01", "020-100", "2030-01-01T15:00:00.000Z"],
            ["0000000007-30-000009", "C", "2030-01-01", "020-900", "2030-01-01T09:00:00.000Z"]]
    cik = _discovery_ctx(ctx, rows)
    clock = {"pilot_start_utc": "2030-01-01T12:00:00+00:00"}
    a = discover.register_initial_form_c(ctx, cik, "0000000007-30-000001", "t", clock, False)
    b = discover.register_initial_form_c(ctx, cik, "0000000007-30-000009", "t", clock, True)
    c = {r[0]: r[1] for r in ctx.con.execute("SELECT offering_id, cohort FROM offerings")}
    assert c[a] == "inception" and c[b] == "initial_watchlist"


# ---- 5. missing facts are not zeros --------------------------------------------------------------------
def test_missing_fact_is_null_not_zero(ctx):
    facts = form_c_facts(parse_xml(form_c_xml(revenue=None)))
    rev = [f for f in facts if f["field"] == "revenue" and f["financial_period"] == "most_recent_fiscal_year"][0]
    assert rev["value"] is None and rev["verification_status"] == "missing" and rev["missing_reason"]
    oid = add_offering(ctx)
    d = ctx.record_document(url="x", source_type="sec_primary_xml", offering_id=oid, data=b"x")
    collect._add_facts(ctx, oid, d, facts, ctx.now())
    pkt, _ = journal.build_packet(ctx, oid)
    assert "| revenue | missing |" in pkt.read_text()
    assert ctx.con.execute("SELECT COUNT(*) FROM facts WHERE field='revenue' AND value='0'").fetchone()[0] == 0


# ---- 6. unknown outcomes are not failures; forecasts ----------------------------------------------------
def test_forecast_deadlines_revisions_and_unresolved(ctx):
    oid = add_offering(ctx)
    pid = journal.add_forecast(ctx, oid, "C-AR for FY2030 reports revenue > $100,000", "disclosure", 6, 0.3,
                               "resolve true on a C-AR showing revenue > 100000", 60, "remains unresolved", "user")
    rid = journal.add_forecast(ctx, oid, "x", "disclosure", 12, 0.5, "x", 60, "x", "user", revises=pid)
    p, r = [ctx.con.execute("SELECT * FROM predictions WHERE prediction_id=?", (i,)).fetchone() for i in (pid, rid)]
    assert r["deadline_utc"] == p["deadline_utc"] and p["probability"] == 0.3     # revision keeps deadline; original kept
    with pytest.raises(ValueError):
        journal.resolve_forecast(ctx, pid, "false", "no filing found", "user")      # before deadline + lag
    with pytest.raises(sqlite3.IntegrityError):
        ctx.con.execute("UPDATE predictions SET probability=0.9")
    set_now(ctx, "2031-01-01T00:00:00+00:00")                                        # past deadline + lag, no evidence
    st = {s["prediction_id"]: s["state"] for s in journal.forecast_status(ctx)}
    assert st[pid] == "due_unadjudicated"                                            # not 'false'
    b = journal.brier(journal.forecast_status(ctx))
    assert b["brier"] is None and b["n_resolved"] == 0 and b["n_unresolved"] == 1
    journal.resolve_forecast(ctx, pid, "true", "C-AR accession 0000000001-31-000001 revenue 150000", "user")
    b = journal.brier(journal.forecast_status(ctx))
    assert b["n_resolved"] == 1 and abs(b["brier"] - 0.49) < 1e-9


# ---- 7. equal follow-up for selected and rejected -------------------------------------------------------
def test_follow_up_schedule_ignores_decisions(ctx):
    rows = [["0000000001-30-000001", "C", "2030-01-01", "020-1", "2030-01-01T00:00:00.000Z"]]
    pages = {"https://data.sec.gov/submissions/CIK0000000001.json": submissions(rows),
             "https://data.sec.gov/submissions/CIK0000000002.json": submissions(rows)}
    ctx.fetcher = FakeFetcher(ctx.tmp, pages, clock=lambda: ctx.now())
    a = add_offering(ctx, "RCF-1-020-1", "0000000001", "020-1", "0000000001-30-000001")
    b = add_offering(ctx, "RCF-2-020-1", "0000000002", "020-1", "0000000002-30-000001")
    journal.record_decision(ctx, a, "select", "user", True, paper_amount_usd=250.0)
    journal.record_decision(ctx, b, "pass", "user", True)
    for oid in (a, b):
        collect.check_offering(ctx, ctx.con.execute("SELECT * FROM offerings WHERE offering_id=?", (oid,)).fetchone())
    due = [ctx.con.execute("SELECT next_check_due_utc FROM offerings WHERE offering_id=?", (o,)).fetchone()[0] for o in (a, b)]
    assert due[0] == due[1]
    assert next_check_due("closed_reported", "close_reported_c_u", "2030-01-01T00:00:00+00:00", ctx.cfg) == "2030-01-31T00:00:00+00:00"


# ---- 8. idempotent repeat runs; 9. outages visible -----------------------------------------------------
def test_repeat_discovery_is_idempotent_and_outage_visible(ctx):
    import datetime as dt
    day = dt.date(2030, 1, 2)
    idx = "Form Type   Company Name   CIK   Date Filed   File Name\n" + \
          "C                Synthetic Widgets Inc                                0000000007  20300102    edgar/data/7/0000000007-30-000001.txt\n"
    rows = [["0000000007-30-000001", "C", "2030-01-02", "020-100", "2030-01-02T15:00:00.000Z"]]
    cik = _discovery_ctx(ctx, rows, {discover.index_url(day): idx.encode()})
    set_now(ctx, "2030-01-03T12:00:00+00:00")
    s1 = discover.scan_days(ctx, [day], {"pilot_start_utc": "2030-01-01T00:00:00+00:00"}, False)
    s2 = discover.scan_days(ctx, [day], {"pilot_start_utc": "2030-01-01T00:00:00+00:00"}, False)
    assert s1["republic_new"] == 1 and s2 == {"days_complete": 0, "days_pending": 0, "form_c_seen": 0, "republic_new": 0}
    assert ctx.con.execute("SELECT COUNT(*) FROM offerings").fetchone()[0] == 1
    # an outage on a follow-up check stays visible and the offering is retried (due date unchanged)
    ctx.fetcher.fail[f"https://data.sec.gov/submissions/CIK{cik}.json"] = 503
    o = ctx.con.execute("SELECT * FROM offerings").fetchone()
    res = collect.check_offering(ctx, o)
    o2 = ctx.con.execute("SELECT * FROM offerings").fetchone()
    assert not res["ok"] and o2["last_check_ok"] == 0 and o2["next_check_due_utc"] == o["next_check_due_utc"]
    assert ctx.con.execute("SELECT COUNT(*) FROM gaps WHERE kind='http_error'").fetchone()[0] == 1


def test_pilot_clock_set_once_never_reset(ctx):
    c1 = start_clock(ctx, "2030-01-01T05:00:00+00:00")
    c2 = start_clock(ctx, "2029-06-01T00:00:00+00:00")
    assert c1 == c2 and c1["pilot_start_local_date"] == "2030-01-01" and c1["pilot_end_utc"].startswith("2030-04-01")


# ---- 10. private evidence excluded from exports and git ------------------------------------------------
def test_private_import_excluded_from_export_and_git(ctx):
    oid = add_offering(ctx)
    (ctx.tmp / "notice.pdf").write_bytes(b"%PDF private")
    # v2.1: captures are screened before storage; a near-empty page would now be refused, so the fixture has content
    (ctx.tmp / "page.html").write_bytes(b"<html><body><p>" + b"Public campaign page text. " * 20 + b"</p></body></html>")
    with open(ctx.tmp / "imp.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["offering_id", "file", "url", "source_type", "visibility", "claimed_publication_date",
                                "captured_utc", "description"])
        w.writeheader()
        w.writerow({"offering_id": oid, "file": "notice.pdf", "source_type": "investor_notice", "description": "conversion notice"})
        w.writerow({"offering_id": oid, "file": "page.html", "url": "https://example.invalid/c", "source_type": "campaign_page"})
    s = outputs.import_evidence(ctx, ctx.tmp / "imp.csv")
    assert {k: s[k] for k in ("imported", "private", "rejected")} == {"imported": 2, "private": 1, "rejected": 0}
    outputs.export_public(ctx)
    docs = list(csv.DictReader(open(ctx.root / "data/exports/documents.csv")))
    assert [d["visibility"] for d in docs] == ["public"]
    repo = Path(__file__).resolve().parents[3]
    for rel in ["personal_vc_research/prospective/data/imports/private/x.pdf", "personal_vc_research/prospective/data/pilot.sqlite",
                "personal_vc_research/prospective/data/blobs/ab/abc"]:
        assert subprocess.run(["git", "check-ignore", "-q", rel], cwd=repo).returncode == 0, rel


def test_term_candidates_do_not_cross_lines():
    from prospective.extract import text_terms
    f, _ = text_terms(["Valuation cap of $15,000,000\nMaterial Terms"])   # regression: 'M' of the next line
    assert [x["value"] for x in f] == ["15,000,000"] and f[0]["verification_status"] == "text_regex_unreviewed"


def test_restore_round_trip_keeps_nulls(ctx, tmp_path):
    oid = add_offering(ctx)
    d = ctx.record_document(url="x", source_type="sec_primary_xml", offering_id=oid, data=b"x")
    collect._add_facts(ctx, oid, d, form_c_facts(parse_xml(form_c_xml(revenue=None))), ctx.now())
    outputs.export_public(ctx)
    cfg = yaml.safe_load((ctx.tmp / "config.yaml").read_text())
    cfg["paths"]["db"] = "data/restored.sqlite"
    (ctx.tmp / "config2.yaml").write_text(yaml.safe_dump(cfg))
    c2 = Ctx(ctx.tmp / "config2.yaml", "restore", now=ctx.now(), offline=True)
    outputs.restore_from_exports(c2)
    q = "SELECT field, value, financial_period, verification_status FROM facts ORDER BY fact_id"
    assert ctx.con.execute(q).fetchall() == c2.con.execute(q).fetchall()
    assert c2.con.execute("SELECT COUNT(*) FROM facts WHERE value IS NULL").fetchone()[0] > 0


def test_fresh_database_resumes_scan_from_pilot_start(ctx, monkeypatch):
    import datetime as dt
    start_clock(ctx, "2030-01-01T05:00:00+00:00")
    seen = []
    monkeypatch.setattr(discover, "scan_days", lambda c, days, clock, startup: seen.extend(days) or {})
    set_now(ctx, "2030-01-20T00:00:00+00:00")
    discover.cmd_discover(ctx)
    assert seen[0] == dt.date(2030, 1, 1) and seen[-1] == dt.date(2030, 1, 20)   # no silently skipped days
