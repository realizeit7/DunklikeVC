"""v2.1: access classification, manual-import screening, four-dimension assessment, deterministic calculations,
support checks, freshness, forecasts v2, bounded repair and preservation. SYNTHETIC fixtures only."""
import copy
import csv
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml

from prospective import access, analysis_v2, assess, calc, journal, outputs, packs
from prospective.brief_v2 import build_brief_v2
from prospective.core import Ctx
from prospective.llm.schemas_v2 import CRITERIA

CFG = Path(__file__).resolve().parents[2] / "prospective" / "config.yaml"
TEMPLATES = Path(__file__).resolve().parents[2] / "prospective" / "templates" / "republic_manual_import"
DOC = ("<nameOfIssuer>Synthetic Bio Inc</nameOfIssuer>\n<revenueMostRecentFiscalYear>0.00</revenueMostRecentFiscalYear>\n"
       "The price per share is $1.00 and was determined arbitrarily.\n"
       "As of December 31, 2029 the Company had 10,000,000 shares of Common Stock issued and outstanding.\n"
       "The Company is authorized to issue 50,000,000 shares of Common Stock.\n"
       "The Company is offering a minimum of 50,000 shares and a maximum of 1,000,000 shares.\n"
       "The Company has a convertible note of $100,000 whose conversion price has not been determined.\n"
       "Research and development expense was $0 for the year ended December 31, 2029.\n"
       "Investors irrevocably appoint the CEO as proxy and the Company may repurchase all shares at the original price at any time.\n"
       "THE SUBSCRIPTION AGREEMENT governs the purchase of the Securities.\n"
       "The minimum investment is $100.\n")
KO = "이 회사는 신경 질환 치료 기술을 개발하는 초기 단계 기업이며 아직 매출이 없습니다. "


def claim(cid, text, status, quote=None, basis=(), ctype="other", period=""):
    return {"claim_id": cid, "claim_text": text, "claim_type": ctype, "evidence_status": status,
            "citations": [{"doc_id": 0, "page": 1, "quote": quote}] if quote else [], "financial_period": period,
            "calculation": None, "basis_claim_ids": list(basis), "contradictions": ""}


def v2_outputs(doc_id: int, fees_confirmed=False):
    cl = [claim("A1", "Issuer is Synthetic Bio Inc", "document_supported_fact", "<nameOfIssuer>Synthetic Bio Inc", ctype="identity"),
          claim("A2", "Revenue $0", "document_supported_fact", "<revenueMostRecentFiscalYear>0.00", ctype="financial", period="FY2029"),
          claim("A3", "Price $1.00 per share, set arbitrarily", "document_supported_fact", "The price per share is $1.00 and was determined arbitrarily."),
          claim("A4", "10,000,000 common shares issued as of 2029-12-31", "document_supported_fact", "10,000,000 shares of Common Stock issued and outstanding"),
          claim("A5", "50,000,000 authorized", "document_supported_fact", "authorized to issue 50,000,000 shares"),
          claim("A6", "Offering 50,000 to 1,000,000 shares", "document_supported_fact", "offering a minimum of 50,000 shares and a maximum of 1,000,000 shares"),
          claim("A7", "Note with undetermined conversion price", "document_supported_fact", "convertible note of $100,000 whose conversion price has not been determined"),
          claim("A8", "R&D expense $0 in FY2029", "document_supported_fact", "Research and development expense was $0", ctype="financial", period="FY2029"),
          claim("A9", "Company may repurchase all shares at the original price at any time", "document_supported_fact",
                "the Company may repurchase all shares at the original price at any time", ctype="contract_provision"),
          claim("A10", "Subscription agreement present", "document_supported_fact", "THE SUBSCRIPTION AGREEMENT governs the purchase"),
          claim("A11", "Minimum investment $100", "document_supported_fact", "The minimum investment is $100.")]
    for c in cl:
        for x in c["citations"]:
            x["doc_id"] = doc_id
    items = [("issuer_and_offering_identity", ["A1"]), ("security_type", ["A3"]), ("operative_contract", ["A10"]),
             ("price_cap_and_conversion_terms", ["A3"]), ("financial_statements_and_dates", ["A2"])]
    ci = [{"item": i, "status": "confirmed_with_citation", "claim_ids": ids, "note": ""} for i, ids in items]
    ci.append({"item": "minimum_investment_and_fees", "status": "confirmed_with_citation" if fees_confirmed else "not_found_in_pack",
               "claim_ids": ["A11"] if fees_confirmed else [], "note": "investor fees not stated"})
    ci.append({"item": "closing_or_availability_evidence", "status": "not_found_in_pack", "claim_ids": [], "note": ""})
    a = {"claims": cl, "critical_items": ci, "missing_information": ["investor fees", "efficacy data"],
         "valuation_inputs": {"price_per_share_usd": 1.0, "price_claim_id": "A3",
                              "share_counts": [{"kind": "issued_outstanding", "share_class": "Common", "value": 10_000_000, "as_of": "2029-12-31", "claim_id": "A4"},
                                               {"kind": "authorized", "share_class": "Common", "value": 50_000_000, "as_of": "", "claim_id": "A5"},
                                               {"kind": "offered_minimum", "share_class": "Common", "value": 50_000, "as_of": "", "claim_id": "A6"},
                                               {"kind": "offered_maximum", "share_class": "Common", "value": 1_000_000, "as_of": "", "claim_id": "A6"}],
                              "convertible_instruments": [{"instrument": "convertible note", "principal_usd": 100000,
                                                           "conversion_terms_disclosed": False, "claim_ids": ["A7"], "note": ""}],
                              "note": ""},
         "financial_statements": {"period_end": "2029-12-31", "assurance": "audited", "claim_ids": ["A2"]}}
    sec = {"assessment": "x", "claim_ids": ["A2", "K1"]}
    b = {k: sec for k in ["business_model", "demand_evidence", "competition", "economics_and_funding", "execution_risks",
                          "team_evidence", "security_path_to_proceeds", "price_and_terms"]}
    b.update({"is_pre_revenue": True, "additional_claims": []})
    c = {"issues": [{"issue_type": "optimistic_assumption", "target": "B", "explanation": "x", "claim_ids": ["A8"], "severity": "low"}],
         "additional_claims": []}
    d = {"criteria": [{"criterion_id": k, "result": "pass", "failure_grounds": [], "claim_ids": ["A2"], "counter_claim_ids": [],
                       "reason_ko": "근거 문서에서 확인됩니다.", "what_would_change_ko": "새 재무제표가 나오면 바뀔 수 있습니다."} for k in CRITERIA],
         "critique_responses": [{"issue_index": 0, "accepted": True, "response": "ok"}],
         "forecasts": [{"event_kind": "disclosure", "target_type": "issuer_announces",
                        "event": "The issuer files a Form C-AR reporting revenue above $1,000", "target_scope": "Synthetic Bio Inc, FY2030",
                        "deadline_date": "2031-05-31", "reporting_lag_days": 30, "allowed_evidence": ["EDGAR Form C-AR"],
                        "probability": 0.2, "probability_label": "model_judgment_uncalibrated", "rationale": "pre-revenue",
                        "assumptions": ["company keeps filing"], "unknown_treatment": "unresolved",
                        "cancellation_treatment": "offering cancellation does not resolve this; dissolution before filing = unresolved",
                        "early_resolution": "true_may_resolve_before_deadline", "silence_treatment": "silence_is_not_false",
                        "basis_claim_ids": ["A2"]}]}
    f = {"business_one_liner_ko": "신경 질환 치료 기술을 개발하는 회사입니다.", "summary_ko": KO * 30 + " [A2] [K1]",
         "decisive_reasons_ko": ["결정적 이유입니다."], "material_missing_ko": ["투자자 수수료가 확인되지 않았습니다."],
         "what_would_change_ko": ["감사받은 새 재무제표"], "terms_explained_ko": [{"term": "SAFE", "explanation_ko": "나중에 주식으로 바뀌는 계약입니다."}]}
    return {"A_extraction": a, "B_analysis": b, "C_critical_review": c, "D_final": d, "F_brief_ko": f}


class DynAdapter:
    """Fixture adapter; Stage E answers exactly the requested claims with a configurable verdict."""
    name = "fixture"

    def __init__(self, outs, verdicts=None, broken_stage=None):
        self.outs, self.verdicts, self.broken, self.calls = outs, verdicts or {}, broken_stage, []

    def run(self, stage, system_prompt, payload, schema):
        self.calls.append(stage)
        meta = {"model_reported": "fixture-model", "usage": {"input_tokens": 10, "output_tokens": 5}, "cost_usd": 0.01, "seconds": 0.1}
        if stage == self.broken:
            return {"garbage": True}, meta
        if stage == "E_support_check":
            want = json.loads(payload).get("claims_to_check") or json.loads(payload)["original_request"]["claims_to_check"]
            return {"judgment_label": "model_judgment_not_verification",
                    "checks": [{"claim_id": c, "passage_supports": "yes", "omitted_qualifications": "", "evidence_type": "contract_text",
                                "conflicts": "", "overstatement": "none", "verdict": self.verdicts.get(c, "supported"),
                                "note_ko": "인용문이 주장을 뒷받침합니다."} for c in want]}, meta
        return copy.deepcopy(self.outs[stage]), meta


@pytest.fixture
def ctx(tmp_path):
    cfg = yaml.safe_load(CFG.read_text())
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg))
    c = Ctx(tmp_path / "config.yaml", "test", now="2030-01-10T00:00:00+00:00", offline=True)
    c.tmp = tmp_path
    return c


def setup_offering(ctx, oid="O1"):
    ctx.con.execute("""INSERT INTO offerings(offering_id, issuer_id, offering_file_number, legal_name, cohort, eligibility,
        first_observed_utc, availability_status, closing_status, security_class, initial_filing_date) VALUES
        (?,'0000000001','020-1','Synthetic Bio','inception','eligible','2030-01-01T00:00:00+00:00','unknown','none_reported','equity','2030-01-01')""", (oid,))
    ctx.record_document(url="x1", source_type="sec_primary_xml", offering_id=oid, data=DOC.encode(),
                        retrieved_utc="2030-01-02T00:00:00+00:00", description="primary_doc.xml")
    p = packs.build_pack(ctx, oid, "2030-01-05T00:00:00+00:00")
    doc_id = json.loads(Path(p["path"]).read_text())["documents"][0]["doc_id"]
    analysis_v2.register_v2(ctx, "v2test", "synthetic", ["O1"], repair_rounds=1)
    return p, doc_id


def run(ctx, outs, p, **kw):
    ad = DynAdapter(outs, **kw)
    return analysis_v2.run_v2(ctx, "O1", p["pack_id"], ad, "v2test"), ad


def set_fail(outs, cid, grounds, claim_ids):
    for c in outs["D_final"]["criteria"]:
        if c["criterion_id"] == cid:
            c.update(result="fail", failure_grounds=grounds, claim_ids=claim_ids)


# ---- assessment dimensions ------------------------------------------------------------------------------------
def test_supported_failure_with_missing_information_fails_screen(ctx):
    p, d = setup_offering(ctx)
    o = v2_outputs(d)
    set_fail(o, "PC3_investor_rights_and_dilution", ["documented_contract_term"], ["A9"])
    o["D_final"]["criteria"][0].update(result="unknown")            # an unknown elsewhere does not erase the failure
    r, _ = run(ctx, o, p)
    assert r["assessment"] == "fails_current_screen" and r["decisive"] == ["PC3_investor_rights_and_dilution"]
    assert r["evidence_completeness"] == "sufficient_for_current_conclusion"
    assert r["budget_status"] == "incomplete_cost_information"       # fees missing: a separate dimension
    acts = assess.next_actions({**r, "criteria": [], "extraction_gaps": []}, {"new_filings_since_cutoff": ""})
    assert "수수료" not in acts[0] and "우선순위가 낮" in acts[0]          # fee collection is not the primary next step


@pytest.mark.parametrize("grounds", [["arbitrary_price_disclosure"], ["absence_of_voting_rights"], ["pre_revenue_status"],
                                     ["missing_information"], ["comparable_valuation"]])
def test_unsupported_failure_becomes_unresolved(ctx, grounds):
    p, d = setup_offering(ctx)
    o = v2_outputs(d)
    set_fail(o, "PC2_price_vs_path_to_value", grounds, ["A3"])
    r, _ = run(ctx, o, p)
    row = ctx.con.execute("SELECT * FROM criterion_results WHERE analysis_id=? AND criterion_id='PC2_price_vs_path_to_value'",
                          (r["analysis_id"],)).fetchone()
    assert row["model_result"] == "fail" and row["final_result"] == "unresolved"
    assert r["assessment"] == "indeterminate"


def test_citation_exists_but_support_check_rejects_failure(ctx):
    p, d = setup_offering(ctx)
    o = v2_outputs(d)
    set_fail(o, "BT4_financial_condition_and_funding", ["documented_adverse_fact"], ["A8"])
    r, _ = run(ctx, o, p, verdicts={"A8": "not_supported"})            # quote is verbatim, but does not support the claim
    assert r["assessment"] == "indeterminate" and "BT4_financial_condition_and_funding" in r["unresolved"]
    sc = ctx.con.execute("SELECT * FROM support_checks WHERE analysis_id=? AND claim_id='A8'", (r["analysis_id"],)).fetchone()
    assert sc["citation_exists"] == 1 and sc["verdict"] == "not_supported" and sc["judgment_label"] == "model_judgment_not_verification"


def test_operational_unknown_is_separate_from_assessment(ctx):
    p, d = setup_offering(ctx)
    r, _ = run(ctx, v2_outputs(d, fees_confirmed=True), p)
    assert r["assessment"] == "passes_current_screen" and r["operational_readiness"] == "not_checked"
    ctx.con.execute("INSERT INTO gaps(run_id, utc, kind, url, detail) VALUES ('r','2030-01-09T00:00:00+00:00','access_blocked',"
                    "'https://republic.com/companies','HTTP 403')")
    r2, _ = run(ctx, v2_outputs(d, fees_confirmed=True), p)
    assert r2["assessment"] == "passes_current_screen" and r2["operational_readiness"] == "availability_unknown"
    assert r2["budget_status"] == "eligible"
    acts = assess.next_actions({**r2, "criteria": [], "extraction_gaps": []}, {"new_filings_since_cutoff": ""})
    assert any("실행 차단" in a for a in acts)


def test_parse_failure_is_incomplete_analysis_not_nondisclosure(ctx):
    p, d = setup_offering(ctx)
    r, ad = run(ctx, v2_outputs(d), p, broken_stage="D_final")
    assert r["assessment"] == "analysis_failed" and r["evidence_completeness"] == "extraction_incomplete"
    assert r["legacy_status"] == "analysis_failed" and r["forecasts"] == 0
    acts = assess.next_actions({**r, "criteria": [], "extraction_gaps": []}, {})
    assert "분석이 끝나지 않은 것" in acts[0] and "공개하지 않은 것이 아닙니다" in acts[0]
    o = v2_outputs(d)
    o["A_extraction"]["critical_items"][2].update(status="not_readable_in_pack", claim_ids=[])
    r2, _ = run(ctx, o, p)
    assert r2["evidence_completeness"] == "extraction_incomplete" and r2["assessment"] == "indeterminate"


def test_bounded_repair_preserves_original_and_repaired_outputs(ctx):
    p, d = setup_offering(ctx)
    r, ad = run(ctx, v2_outputs(d), p, broken_stage="B_analysis")
    assert ad.calls.count("B_analysis") == 2                          # original + cap (1) repair, then stop
    assert "C_critical_review" not in ad.calls
    out = Path(r["output_dir"])
    assert (out / "B_analysis.json").exists() and (out / "B_analysis_repair1.json").exists()
    rows = ctx.con.execute("SELECT stage, attempt, outcome FROM stage_usage WHERE analysis_id=?", (r["analysis_id"],)).fetchall()
    assert [(x[0], x[1], x[2]) for x in rows][-2:] == [("B_analysis", "original", "invalid"), ("B_analysis", "repair1", "invalid")]
    lab = ctx.con.execute("SELECT DISTINCT cost_label FROM stage_usage").fetchone()[0]
    assert lab == "cli_estimated_list_price_equivalent_not_billed"


# ---- calculations ----------------------------------------------------------------------------------------------
def test_authorized_vs_outstanding_and_calculation_provenance(ctx):
    p, d = setup_offering(ctx)
    r, _ = run(ctx, v2_outputs(d), p)
    rows = {x["calc_type"].split(":")[1]: dict(x) for x in ctx.con.execute("SELECT * FROM calculations WHERE analysis_id=?", (r["analysis_id"],))}
    pre = rows["implied_pre_money_equity"]
    assert pre["result_value"] == 10_000_000 and pre["result_kind"] == "computed"           # issued, not 50M authorized
    inputs = json.loads(pre["inputs"])
    assert {i["claim_id"] for i in inputs} == {"A3", "A4"} and all(i["citations"] for i in inputs)
    assert next(i for i in inputs if i["name"] == "issued_shares")["as_of"] == "2029-12-31"
    assert any("authorized" in e["instrument"] for e in json.loads(pre["excluded_instruments"]))
    assert rows["implied_post_money_equity_at_offering_maximum"]["result_value"] == 11_000_000
    fd = rows["implied_fully_diluted_equity"]
    assert fd["result_kind"] == "withheld" and "convertible note" in fd["withheld_reason"]


def test_calculation_withheld_or_illustrative_when_inputs_missing_or_conflicting():
    claims = {"P": {"citations": [{"doc_id": 1, "page": 1}]}, "S1": {"citations": []}, "S2": {"citations": []}, "AU": {"citations": []}}
    only_auth = {"price_per_share_usd": 1.0, "price_claim_id": "P", "convertible_instruments": [], "note": "",
                 "share_counts": [{"kind": "authorized", "share_class": "C", "value": 9e7, "as_of": "", "claim_id": "AU"}]}
    k = calc.implied_equity(only_auth, claims, {"P", "AU"})
    assert k[0]["result_kind"] == "withheld" and "authorized shares are never used" in k[0]["withheld_reason"]
    conflict = dict(only_auth, share_counts=[{"kind": "issued_outstanding", "share_class": "C", "value": 1, "as_of": "2029-12-31", "claim_id": "S1"},
                                             {"kind": "issued_outstanding", "share_class": "C", "value": 75_000_001, "as_of": "2030-06-18", "claim_id": "S2"}])
    k2 = calc.implied_equity(conflict, claims, {"P", "S1", "S2"})
    assert k2[0]["result_kind"] == "illustrative" and k2[0]["result_value"] == 75_000_001 and "conflicting" in k2[0]["assumptions"][0]
    assert calc.implied_equity(dict(only_auth, price_per_share_usd=None), claims, {"P"})[0]["result_kind"] == "withheld"


# ---- freshness ---------------------------------------------------------------------------------------------------
def test_fresh_analysis_with_stale_financials_and_failed_collection(ctx):
    p, d = setup_offering(ctx)
    o = v2_outputs(d)
    o["A_extraction"]["financial_statements"]["period_end"] = "2028-06-30"
    r, _ = run(ctx, o, p)
    pack, _ = packs.load_pack(ctx, p["pack_id"])
    fz = assess.freshness(ctx, "O1", ctx.now(), pack, o)
    assert fz["analysis_age_days"] == 0 and fz["financial_stale"] is True
    assert fz["new_filings_since_cutoff"].startswith("not established")
    ctx.con.execute("INSERT INTO source_checks(offering_id, source, checked_utc, success, covers_from_utc, covers_to_utc, detail) "
                    "VALUES ('O1','sec_edgar_submissions','2030-01-09T00:00:00+00:00',0,NULL,NULL,'timeout')")
    assert assess.freshness(ctx, "O1", ctx.now(), pack, o)["new_filings_since_cutoff"].startswith("not established")
    ctx.con.execute("INSERT INTO source_checks(offering_id, source, checked_utc, success, covers_from_utc, covers_to_utc, detail) "
                    "VALUES ('O1','sec_edgar_submissions','2030-01-10T00:00:00+00:00',1,'2030-01-01T00:00:00+00:00','2030-01-10T00:00:00+00:00','ok')")
    assert assess.freshness(ctx, "O1", ctx.now(), pack, o)["new_filings_since_cutoff"].startswith("no new filings")


# ---- forecasts ---------------------------------------------------------------------------------------------------
def test_forecast_event_vs_announcement_and_no_or_compounds(ctx):
    p, d = setup_offering(ctx)
    r, _ = run(ctx, v2_outputs(d), p)
    fd = ctx.con.execute("SELECT * FROM forecast_definitions").fetchone()
    pr = ctx.con.execute("SELECT * FROM predictions WHERE prediction_id=?", (fd["prediction_id"],)).fetchone()
    assert fd["target_type"] == "issuer_announces" and fd["silence_is_false"] == 0 and fd["early_true_allowed"] == 1
    assert pr["deadline_utc"].startswith("2031-05-31")
    with pytest.raises(sqlite3.IntegrityError):
        ctx.con.execute("INSERT INTO forecast_definitions(prediction_id, schema_version, target_type, target_scope, deadline_utc, "
                        "reporting_lag_days, allowed_evidence, rationale, assumptions, unknown_treatment, cancellation_treatment, "
                        "silence_is_false) VALUES (999,'s','event_occurs','x','2031-01-01',0,'[]','r','[]','u','c',1)")
    o = v2_outputs(d)
    o["D_final"]["forecasts"][0]["event"] = "The issuer obtains IRB approval or treats its first human patient"
    errs = analysis_v2.validate_stage("D_final", packs.load_pack(ctx, p["pack_id"])[0], {**o, "C_critical_review": o["C_critical_review"]}, {})
    assert any("joins alternatives" in e for e in errs)
    o["D_final"]["forecasts"][0]["event"] = "The offering closes at or above $75,000"
    errs = analysis_v2.validate_stage("D_final", packs.load_pack(ctx, p["pack_id"])[0], o, {})
    assert not any("joins alternatives" in e for e in errs)


def test_old_forecasts_and_analyses_are_preserved(ctx):
    p, d = setup_offering(ctx)
    old = journal.add_forecast(ctx, "O1", "IRB or FDA clearance or first human treated", "business", 12, 0.12, "rule", 120, "unresolved", "v1")
    r, _ = run(ctx, v2_outputs(d), p)
    lid = analysis_v2.forecast_lineage(ctx, old, "flagged_compound", "joins distinct regulatory events with 'or'")
    assert ctx.con.execute("SELECT target_event FROM predictions WHERE prediction_id=?", (old,)).fetchone()[0].startswith("IRB or FDA")
    for t, col in [("predictions", "probability"), ("forecast_lineage", "reason"), ("assessments", "assessment"),
                   ("analysis_runs", "status"), ("criterion_results", "final_result")]:
        with pytest.raises(sqlite3.IntegrityError):
            ctx.con.execute(f"UPDATE {t} SET {col}={col}")
    assert lid > 0


# ---- Korean output checks ----------------------------------------------------------------------------------------
def test_korean_summary_rejects_raw_english_and_length():
    assert analysis_v2.korean_errors("x", KO * 30, 250, 600) == []
    assert any("English passage" in e for e in analysis_v2.korean_errors(
        "x", KO * 30 + " You are a careful early-stage investment research analyst working for one individual investor"))
    assert any("at least" in e for e in analysis_v2.korean_errors("x", KO, 250, 600))


def test_brief_v2_top_summary_and_untruncated_appendix(ctx):
    p, d = setup_offering(ctx)
    o = v2_outputs(d)
    long_reason = "매우 긴 이유입니다. " * 80
    o["D_final"]["criteria"][0]["reason_ko"] = long_reason
    r, _ = run(ctx, o, p)
    b = build_brief_v2(ctx, r["analysis_id"], out_dir=ctx.tmp / "briefs").read_text()
    assert b.index("## 요약") < b.index("# 부록") and "개발 사례" in b
    assert long_reason.strip() in b                                   # nothing truncated
    assert "override" not in b.lower() and "무시하고" not in b
    assert "모델 판단(model judgment)이며 검증이 아닙니다" in b


# ---- access and import screening ------------------------------------------------------------------------------------
def test_challenge_login_and_widget_pages_are_classified_before_extraction():
    block = (TEMPLATES / "example_block_page.html").read_text()
    assert access.classify_page(403, "u", "u", block)["result"] == "challenge"
    assert access.classify_page(200, "u", "u", "<title>Just a moment...</title><div id='cf-chl-widget'></div>")["result"] == "challenge"
    shop = "<html><script src='hcaptcha.js'></script><body>" + "Gluten-free cookies with clean ingredients. " * 30 + "</body></html>"
    assert access.classify_page(200, "u", "u", shop)["result"] == "public_content"
    assert access.classify_page(200, "https://x/a", "https://x/users/sign_in", "<html>" + "text " * 100 + "</html>")["result"] == "login_required"
    assert access.classify_page(None, "u", "", "")["result"] == "network_error"


def test_manual_import_example_and_private_or_secret_material_exclusion(ctx):
    setup_offering(ctx)
    work = ctx.tmp / "imp"
    shutil.copytree(TEMPLATES, work)
    rows = list(csv.DictReader(open(work / "example_import.csv")))
    for r in rows:
        r["offering_id"] = "O1"
    (work / "cookies.txt").write_text("# Netscape HTTP Cookie File\n.republic.com\tTRUE\t/\tTRUE\t0\t_session_id\tabc")
    (work / "logged_in.html").write_text("<html><body>" + "Investor-only update text visible after login. " * 20 + "</body></html>")
    rows += [dict(rows[0], file="cookies.txt", description="cookie jar"),
             dict(rows[0], file="logged_in.html", captured_while_logged_in="yes", description="seen while logged in")]
    with open(work / "imp.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    s = outputs.import_evidence(ctx, work / "imp.csv")
    assert s["imported"] == 2 and s["rejected"] == 2 and s["private"] == 1
    reasons = [x["reason"] for x in s["rows"] if x["status"] == "rejected"]
    assert any("challenge" in x for x in reasons) and any("cookie" in x for x in reasons)
    vis = [r[0] for r in ctx.con.execute("SELECT visibility FROM documents WHERE source_type='user_import' ORDER BY document_id")]
    assert vis == ["public", "private"]
    outputs.export_public(ctx)
    exported = (ctx.root / "data/exports/documents.csv").read_text()
    assert "logged in" not in exported and "Investor-only" not in exported
    # an import made now can never enter an earlier pack
    p2 = packs.build_pack(ctx, "O1", "2030-01-05T00:00:00+00:00")
    assert all(d["source_type"] != "user_import" for d in json.loads(Path(p2["path"]).read_text())["documents"])
