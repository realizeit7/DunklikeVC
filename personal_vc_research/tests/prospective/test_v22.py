"""v2.2 acceptance tests: evidence classification, generic triggers, decision chains, preferences, proposed-policy
isolation, budget/fee semantics, valuation vs judgment, runway, no invented proceeds, preservation. SYNTHETIC only."""
import copy
import json
from pathlib import Path

import pytest
import yaml

from prospective import analysis_v3, calc, journal, ledger, packs
from prospective import policy as policy_mod
from prospective.brief_v3 import build_brief_v3
from prospective.core import Ctx
from prospective.llm.schemas_v3 import QUESTIONS, RULE_IDS

CFG = Path(__file__).resolve().parents[2] / "prospective" / "config.yaml"
DOC = ("<nameOfIssuer>Synthetic Neuro Inc</nameOfIssuer>\n<revenueMostRecentFiscalYear>0.00</revenueMostRecentFiscalYear>\n"
       "In a mouse study the treated group showed improved motor scores (p=0.01); sample size was not disclosed.\n"
       "The price per share is $1.00 and was determined arbitrarily.\n"
       "As of December 31, 2029 the Company had 10,000,000 shares of Common Stock issued and outstanding.\n"
       "The Company is offering a maximum of 1,000,000 shares.\n"
       "Cash was $20,000 as of December 31, 2028.\n"
       "Net loss for the year ended December 31, 2028 was $240,000.\n"
       "Our financial condition raises substantial doubt about our ability to continue as a going concern.\n"
       "The Securities do not entitle Investors to any dividends.\n"
       "The Securities do not have anti-dilution rights.\n"
       "First, five percent of Pre-Distribution Cash shall be allocated to an Affiliate of the Manager before any distribution to Members.\n"
       "THE SUBSCRIPTION AGREEMENT governs the purchase of the Securities.\n"
       "The minimum investment is $100.\n")
KO = "회사 설명에 따르면 이 회사는 신경 질환 치료 기술을 개발하는 초기 단계 기업이며 아직 매출이 없습니다. "


def claim(cid, text, quote, kind, dims, status="document_supported_fact", as_of="", rationale=""):
    return {"claim_id": cid, "claim_text": text, "evidence_status": status, "evidence_kind": kind, "dimensions": dims,
            "dimension_rationale": rationale, "attribution": "issuer Form C", "as_of": as_of,
            "citations": [{"doc_id": 0, "page": 1, "quote": quote}] if quote else [], "financial_period": "",
            "calculation": None, "basis_claim_ids": [], "contradictions": "", "claim_type": "other"}


def finding(rule_id, result="unknown", facts=(), scope="none"):
    return {"rule_id": rule_id, "result": result, "scope": scope, "claims_independently_decisive": result == "adverse",
            "facts": [{"claim_id": c, "role": r, "generic_trigger": g} for c, r, g in facts],
            "interpretation_ko": "문서에 근거한 해석입니다.", "counterevidence_ko": "", "unresolved_ko": "추가 자료가 필요합니다.",
            "what_would_change_ko": "새 재무 자료가 나오면 바뀔 수 있습니다."}


def outputs(doc_id):
    cl = [claim("A1", "Issuer is Synthetic Neuro Inc", "<nameOfIssuer>Synthetic Neuro Inc", "form_field", ["TERMS"]),
          claim("A2", "Revenue $0 (pre-revenue)", "<revenueMostRecentFiscalYear>0.00", "audited_financials", ["FIN"]),
          claim("A3", "Issuer-reported mouse study, p=0.01, sample size not disclosed", "In a mouse study the treated group showed improved motor scores",
                "preclinical_efficacy", ["TECH"]),
          claim("A4", "Price $1.00, set arbitrarily", "The price per share is $1.00 and was determined arbitrarily.", "contract_term", ["TERMS"]),
          claim("A5", "10,000,000 shares issued", "10,000,000 shares of Common Stock issued and outstanding", "form_field", ["TERMS"], as_of="2029-12-31"),
          claim("A6", "Offering maximum 1,000,000 shares", "offering a maximum of 1,000,000 shares", "contract_term", ["TERMS"]),
          claim("A7", "Cash $20,000 at 2028-12-31", "Cash was $20,000 as of December 31, 2028.", "audited_financials", ["FIN"], as_of="2028-12-31"),
          claim("A8", "Net loss 2028 $240,000", "Net loss for the year ended December 31, 2028 was $240,000.", "audited_financials", ["FIN"]),
          claim("A9", "Going-concern risk factor", "raises substantial doubt about our ability to continue as a going concern", "form_field", ["FIN"]),
          claim("A10", "No dividends", "The Securities do not entitle Investors to any dividends.", "contract_term", ["TERMS"]),
          claim("A11", "No anti-dilution", "The Securities do not have anti-dilution rights.", "contract_term", ["TERMS"]),
          claim("A12", "5% of pre-distribution cash goes to a manager affiliate before members", "five percent of Pre-Distribution Cash shall be allocated to an Affiliate",
                "contract_term", ["TERMS"]),
          claim("A13", "Subscription agreement present", "THE SUBSCRIPTION AGREEMENT governs the purchase", "contract_term", ["TERMS"]),
          claim("A14", "Minimum investment $100", "The minimum investment is $100.", "contract_term", ["TERMS"])]
    for c in cl:
        for x in c["citations"]:
            x["doc_id"] = doc_id
    items = ["issuer_and_offering_identity", "security_type", "operative_contract", "price_cap_and_conversion_terms",
             "minimum_investment_and_fees", "financial_statements_and_dates", "closing_or_availability_evidence"]
    a = {"claims": cl, "critical_items": [{"item": i, "status": "confirmed_with_citation", "claim_ids": ["A1"], "note": ""} for i in items],
         "missing_information": ["investor fees"],
         "valuation_inputs": {"price_per_share_usd": 1.0, "price_claim_id": "A4", "note": "",
                              "share_counts": [{"kind": "issued_outstanding", "share_class": "Common", "value": 10_000_000, "as_of": "2029-12-31",
                                                "basis": "form_c_capitalization_table", "claim_id": "A5"},
                                               {"kind": "offered_maximum", "share_class": "Common", "value": 1_000_000, "as_of": "",
                                                "basis": "offering_terms", "claim_id": "A6"}],
                              "convertible_instruments": [{"instrument": "planned note", "status": "planned", "principal_usd": 50000, "as_of": "",
                                                           "conversion_terms_disclosed": False, "claim_ids": ["A13"], "note": ""}]},
         "cash_points": [{"amount_usd": 20000, "as_of": "2028-12-31", "assurance": "audited", "claim_id": "A7"}],
         "spending_points": [{"kind": "net_loss", "amount_usd": 240000, "period_start": "2028-01-01", "period_end": "2028-12-31",
                              "assurance": "audited", "claim_id": "A8"}],
         "financial_statements": {"period_end": "2028-12-31", "assurance": "audited", "claim_ids": ["A7"]},
         "fees": {"investor_paid_fee_stated": False, "investor_fee_claim_ids": [], "issuer_paid_fee_claim_ids": [],
                  "minimum_investment_usd": 100, "minimum_claim_id": "A14"},
         "document_conflicts": []}
    sec = {"assessment": "x", "claim_ids": ["A2"]}
    b = {k: sec for k in ["technical_and_efficacy", "commercial_demand", "regulatory_progress", "team_execution", "financing_and_runway",
                          "terms_and_investor_proceeds", "competition_and_advantage"]}
    b.update({"stage": "preclinical_or_prototype", "additional_claims": []})
    c = {"issues": [], "additional_claims": []}
    d = {"rule_findings": [finding(r) for r in RULE_IDS], "preference_findings": [],
         "thesis": [{"question_id": q, "status": "unknown", "answer_ko": "문서에 근거가 없습니다.", "claim_ids": []} for q in QUESTIONS],
         "critique_responses": []}
    d["thesis"][-1]["status"] = "no_substantiated_advantage_identified"
    f = {"company_ko": KO, "why_could_work_ko": "입증된 근거는 아직 없습니다.", "unknowns_ko": ["투자자 수수료"], "what_would_change_ko": ["최신 재무제표"]}
    return {"A_extraction": a, "B_analysis": b, "C_critical_review": c, "D_final": d, "F_brief_ko": f}


def set_finding(o, rule_id, result, facts, scope="economic_concern"):
    o["D_final"]["rule_findings"] = [finding(rule_id, result, facts, scope) if x["rule_id"] == rule_id else x
                                     for x in o["D_final"]["rule_findings"]]


class Ad:
    name = "fixture"

    def __init__(self, outs, verdicts=None, calls=None):
        self.outs, self.verdicts, self.calls = outs, verdicts or {}, []

    def run(self, stage, system_prompt, payload, schema):
        self.calls.append(stage)
        meta = {"model_reported": "fixture-model", "usage": {"output_tokens": 1}, "cost_usd": 0.0, "seconds": 0}
        if stage == "E_support_check":
            p = json.loads(payload)
            want = p["claims_to_check"] if "claims_to_check" in p else p["original_request"]["claims_to_check"]
            return {"judgment_label": "model_judgment_not_verification",
                    "checks": [{"claim_id": c, "passage_supports": "yes", "omitted_qualifications": "", "evidence_type": "contract_text",
                                "conflicts": "", "overstatement": "none", "verdict": self.verdicts.get(c, "supported"),
                                "note_ko": "인용문이 주장을 뒷받침합니다."} for c in want]}, meta
        return copy.deepcopy(self.outs[stage]), meta


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(yaml.safe_load(CFG.read_text())))
    c = Ctx(tmp_path / "config.yaml", "test", now="2030-01-10T00:00:00+00:00", offline=True)
    c.tmp = tmp_path
    c.con.execute("""INSERT INTO offerings(offering_id, issuer_id, offering_file_number, legal_name, cohort, eligibility, first_observed_utc,
        availability_status, closing_status, security_class, initial_filing_date) VALUES ('O1','0000000001','020-1','Synthetic Neuro',
        'inception','eligible','2030-01-01T00:00:00+00:00','unknown','none_reported','equity','2030-01-01')""")
    c.record_document(url="x1", source_type="sec_primary_xml", offering_id="O1", data=DOC.encode(),
                      retrieved_utc="2030-01-02T00:00:00+00:00", description="primary_doc.xml")
    p = packs.build_pack(c, "O1", "2030-01-05T00:00:00+00:00")
    c.pack = p
    c.doc_id = json.loads(Path(p["path"]).read_text())["documents"][0]["doc_id"]
    analysis_v3.register_v3(c, "v3test", "synthetic", ["O1"], repair_rounds=1)
    return c


def run(ctx, o, verdicts=None, policy_override=None):
    ad = Ad(o, verdicts)
    return analysis_v3.run_v3(ctx, "O1", ctx.pack["pack_id"], ad, "v3test", policy_override=policy_override), ad


def finding_row(ctx, aid, rule):
    return ctx.con.execute("SELECT * FROM rule_findings WHERE analysis_id=? AND rule_id=?", (aid, rule)).fetchone()


# 1. mouse efficacy cannot silently become demand evidence
def test_mouse_efficacy_is_not_demand_evidence(ctx):
    o = outputs(ctx.doc_id)
    o["A_extraction"]["claims"][2]["dimensions"] = ["TECH", "DEMAND"]
    o["A_extraction"]["claims"][2]["dimension_rationale"] = "shows the product works"
    pack = packs.load_pack(ctx, ctx.pack["pack_id"])[0]
    errs = analysis_v3.validate_stage("A_extraction", pack, o, {"policy": policy_mod.load("screening_policy_v1_2")})
    assert any("cannot be classified as commercial DEMAND" in e for e in errs)
    o = outputs(ctx.doc_id)
    set_finding(o, "R-DEM-1", "not_adverse", [("A3", "supporting", "none")])
    errs = analysis_v3.validate_stage("D_final", pack, o, {"policy": policy_mod.load("screening_policy_v1_2"), "calcs": {}})
    assert any("A3 (preclinical_efficacy) cannot support R-DEM-1" in e for e in errs)


# 2. each generic early-stage characteristic alone does not force rejection
@pytest.mark.parametrize("rule,cid,trig", [("R-FIN-1", "A2", "G1"), ("R-FIN-1", "A7", "none"), ("R-FIN-1", "A9", "G3"),
                                           ("R-TERMS-1", "A10", "none"), ("R-TERMS-1", "A11", "G5"), ("R-TERMS-1", "A4", "G7")])
def test_generic_trigger_alone_never_rejects(ctx, rule, cid, trig):
    o = outputs(ctx.doc_id)
    set_finding(o, rule, "adverse", [(cid, "supporting", trig)])   # "none" for A7/A10: keyword/date rules must still catch them
    r, _ = run(ctx, o)
    row = finding_row(ctx, r["analysis_id"], rule)
    assert row["final_result"] == "adverse_contributing" and not row["independently_decisive"]
    assert r["screening"] == "provisional_unresolved"
    assert "generic" in row["validator_notes"]


# 3. an explicit, enabled preference breach independently gives a provisional rejection
def test_enabled_preference_breach_rejects_provisionally(ctx):
    pol = policy_mod.load("screening_policy_v1_2")
    pol = copy.deepcopy(pol)
    pol["preferences"][0].update(enabled=True, parameters={"max_implied_pre_money": 5_000_000})
    r, _ = run(ctx, outputs(ctx.doc_id), policy_override=pol)
    assert r["screening"] == "provisional_reject" and r["decisive"] == ["P-1"]
    a = ctx.con.execute("SELECT notes FROM assessments_v3 WHERE analysis_id=?", (r["analysis_id"],)).fetchone()[0]
    assert "10,000,000" in a and "deterministic" in a


# 4. missing information stays unknown
def test_missing_information_stays_unknown_and_unresolved(ctx):
    r, _ = run(ctx, outputs(ctx.doc_id))
    rows = ctx.con.execute("SELECT final_result FROM rule_findings WHERE analysis_id=?", (r["analysis_id"],)).fetchall()
    assert {x[0] for x in rows} == {"unknown"} and r["screening"] == "provisional_unresolved"
    assert r["evidence_status"] == "insufficient" and r["thesis_status"] == "incomplete"


# 5. a supported company-specific failure is not masked by unrelated missing information
def test_supported_decisive_failure_not_masked(ctx):
    o = outputs(ctx.doc_id)
    set_finding(o, "R-TERMS-1", "adverse", [("A12", "supporting", "none"), ("A10", "supporting", "G4")])
    r, _ = run(ctx, o)
    assert r["screening"] == "provisional_reject" and r["decisive"] == ["R-TERMS-1"]
    assert r["evidence_status"] == "sufficient_for_named_decision"
    scope = ctx.con.execute("SELECT evidence_scope FROM assessments_v3 WHERE analysis_id=?", (r["analysis_id"],)).fetchone()[0]
    assert "provisional_reject" in scope and "not a statement that diligence is complete" in scope
    b = build_brief_v3(ctx, r["analysis_id"], out_dir=ctx.tmp / "b").read_text()
    assert "제안된 정책에 따른 잠정 분류" in b and "R-TERMS-1" in b and "doc " in b and "규칙 문구" in b
    assert b.count("제안된 정책에 따른 잠정 분류") == 1


# 6. unsupported rule conclusions cannot produce a validated decisive rejection
def test_unsupported_conclusion_cannot_reject(ctx):
    o = outputs(ctx.doc_id)
    set_finding(o, "R-TERMS-1", "adverse", [("A12", "supporting", "none")])
    r, _ = run(ctx, o, verdicts={"A12": "not_supported"})
    assert r["screening"] == "provisional_unresolved"
    assert finding_row(ctx, r["analysis_id"], "R-TERMS-1")["final_result"] == "adverse_contributing"
    o2 = outputs(ctx.doc_id)
    o2["A_extraction"]["claims"][11]["citations"][0]["quote"] = "ten percent of all cash goes to insiders first"
    r2, _ = run(ctx, o2)
    assert r2["screening"] == "analysis_failed"


# 7. proposed policies cannot enter the approval path; only the user can activate
def test_proposed_policy_cannot_enter_approval_path(ctx):
    o = outputs(ctx.doc_id)
    set_finding(o, "R-TERMS-1", "adverse", [("A12", "supporting", "none")])
    r, _ = run(ctx, o)
    for kw in [dict(screening_policy_version="screening_policy_v1_2"), dict(analysis_id=r["analysis_id"])]:
        res = ledger.approve(ctx, offering_id="O1", amount_usd="100", fee_usd=None, fee_basis=None, issuer_key_confirmed="0000000001",
                             analysis_id=kw.get("analysis_id"), min_investment_usd="100", applicable_terms="t", availability_note="a",
                             contract_document_id=None, override_rationale="x", **{k: v for k, v in kw.items() if k != "analysis_id"})
        assert res["status"] == "blocked" and any("PROPOSED" in b or "not active" in b for b in res["blockers"])
    assert ctx.con.execute("SELECT COUNT(*) FROM ledger_events").fetchone()[0] == 0
    with pytest.raises(PermissionError):
        policy_mod.activate(ctx, "screening_policy_v1_2", policy_mod.sha("screening_policy_v1_2"), "x" * 30, False)
    with pytest.raises(ValueError):
        policy_mod.activate(ctx, "screening_policy_v1_2", "0" * 64, "x" * 30, True)
    assert policy_mod.state(ctx, "screening_policy_v1_2") == "proposed"


# 8. missing fees block full cost verification without reporting the budget as exceeded
def test_missing_fees_block_verification_not_budget(ctx):
    r, _ = run(ctx, outputs(ctx.doc_id))
    b = json.loads(ctx.con.execute("SELECT budget FROM assessments_v3 WHERE analysis_id=?", (r["analysis_id"],)).fetchone()[0])
    assert b["total_cost_verifiable"] is False and b["investor_fee_status"] == "not_stated"
    assert b["annual_remaining_usd"] == "$12,000.00" and b["issuer_remaining_usd"] == "$1,200.00"
    assert "not assumed zero" in b["note"] and "not reported as exceeded" in b["note"]


# 9. valuation arithmetic is separate from valuation judgment and from fully diluted value
def test_valuation_arithmetic_vs_judgment(ctx):
    o = outputs(ctx.doc_id)
    set_finding(o, "R-TERMS-2", "adverse", [("A4", "supporting", "G7"), ("K1", "supporting", "none")])
    r, _ = run(ctx, o)
    k = {x[0].split(":")[1]: x for x in ctx.con.execute("SELECT calc_type, result_value, result_kind, excluded_instruments FROM calculations "
                                                        "WHERE analysis_id=?", (r["analysis_id"],))}
    assert k["implied_pre_money_equity"][1] == 10_000_000 and k["implied_pre_money_equity"][2] == "computed"
    assert "planned" in k["implied_pre_money_equity"][3]          # a planned note is listed, never counted as existing
    assert finding_row(ctx, r["analysis_id"], "R-TERMS-2")["final_result"] == "adverse_contributing"   # judgment rule cannot reject alone
    assert r["screening"] == "provisional_unresolved"


# 10. stale spending never silently produces a current runway
def test_stale_spending_gives_no_runway():
    cash = [{"amount_usd": 160000, "as_of": "2030-06-18", "assurance": "unaudited_issuer_statement", "claim_id": "C"}]
    old = [{"kind": "net_loss", "amount_usd": 56000, "period_start": "2029-01-01", "period_end": "2029-12-31", "assurance": "audited", "claim_id": "S"}]
    r = calc.runway(cash, old, {"C", "S"})
    assert r["result_kind"] == "withheld" and "stale" in r["withheld_reason"]
    fresh = [{"kind": "operating_cash_outflow", "amount_usd": 60000, "period_start": "2030-01-01", "period_end": "2030-05-31",
              "assurance": "unaudited_issuer_statement", "claim_id": "S"}]
    r2 = calc.runway(cash, fresh, {"C", "S"})
    assert r2["result_value"] is not None and r2["result_kind"] == "illustrative"
    issuer_burn = [{"kind": "issuer_stated_monthly_burn", "amount_usd": 26000, "period_start": "", "period_end": "2030-06-18",
                    "assurance": "unaudited_issuer_statement", "claim_id": "S"}]
    assert calc.runway(cash, issuer_burn, {"C", "S"})["result_kind"] == "withheld"


# 11. no exit cash flow, probability or return from missing inputs
def test_no_invented_proceeds_or_returns(ctx):
    p = calc.investor_proceeds("equity", {})
    assert p["result_kind"] == "withheld" and "exit_equity_value_usd_assumption" in p["withheld_reason"]
    r, _ = run(ctx, outputs(ctx.doc_id))
    kinds = {x[0].split(":")[1]: x[1] for x in ctx.con.execute("SELECT calc_type, result_kind FROM calculations WHERE analysis_id=?",
                                                              (r["analysis_id"],))}
    assert kinds["investor_cash_proceeds_scenario"] == "withheld"
    rw = ctx.con.execute("SELECT assumptions FROM calculations WHERE analysis_id=? AND calc_type LIKE '%runway%'", (r["analysis_id"],)).fetchone()[0]
    assert "NOT a current runway" in rw                       # same-period 2028 figures: runway at that date only
    o = outputs(ctx.doc_id)
    o["D_final"]["thesis"][0]["answer_ko"] = "성공 확률은 30%입니다."
    errs = analysis_v3.validate_stage("D_final", packs.load_pack(ctx, ctx.pack["pack_id"])[0], o,
                                      {"policy": policy_mod.load("screening_policy_v1_2"), "calcs": {}})
    assert any("percentage needs a cited basis" in e for e in errs)


# 12. old analyses, decisions, forecasts and budget behaviour stay intact
def test_old_records_and_budget_intact(ctx):
    pid = journal.add_forecast(ctx, "O1", "old forecast", "business", 12, 0.2, "rule", 30, "unresolved", "v1")
    before_state = ledger.current_state(ctx)
    before = {t: ctx.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("predictions", "decisions", "assessments", "approvals")}
    run(ctx, outputs(ctx.doc_id))
    after = {t: ctx.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in before}
    assert before == after                                       # v3 creates no forecasts, decisions, v2 assessments or approvals
    assert ctx.con.execute("SELECT target_event FROM predictions WHERE prediction_id=?", (pid,)).fetchone()[0] == "old forecast"
    s = ledger.current_state(ctx)
    assert (s.annual_remaining_cents, s.period_label) == (before_state.annual_remaining_cents, before_state.period_label)
    import sqlite3
    for t in ("rule_findings", "assessments_v3", "thesis_answers"):
        with pytest.raises(sqlite3.IntegrityError):
            ctx.con.execute(f"DELETE FROM {t}")


# citation rule 3_1 (v3 only): whitespace-only differences pass and are recorded; other differences fail; v1/v2 unchanged
def test_whitespace_only_citation_rule_is_v3_only():
    from prospective import analysis
    pack = {"documents": [{"doc_id": 1, "source_type": "sec_attachment"}],
            "pages": [{"doc_id": 1, "page": 1, "text": "CommonStock,$0.00parvalue;1shareauthorized; 1"}]}
    cl = claim("A1", "1 share at year end", "Common Stock,$0.00parvalue;1shareauthorized; 1", "audited_financials", ["TERMS"])
    cl["citations"][0]["doc_id"] = 1
    outs = {"A_extraction": {"claims": [cl]}}
    e2 = []
    analysis.claims_checks(pack, outs, e2)
    assert any("not found verbatim" in x for x in e2)                          # v1/v2 behaviour unchanged
    e3 = []
    analysis.claims_checks(pack, outs, e3, whitespace_insensitive=True)
    assert e3 == [] and any("ignoring whitespace" in m for m in analysis.WS_MATCHES)
    cl["citations"][0]["quote"] = "Common Stock,$0.00parvalue;2sharesauthorized"
    e4 = []
    analysis.claims_checks(pack, {"A_extraction": {"claims": [cl]}}, e4, whitespace_insensitive=True)
    assert any("not found verbatim" in x for x in e4)                          # different characters still fail


def test_resume_reuses_stored_stages_and_carries_the_repair_budget(ctx):
    o = outputs(ctx.doc_id)
    good_a = copy.deepcopy(o["A_extraction"])
    o["A_extraction"]["claims"][0]["citations"][0]["quote"] = "a quote that is not on the page at all"
    r1, ad1 = run(ctx, o)
    assert r1["screening"] == "analysis_failed" and ad1.calls.count("A_extraction") == 2
    d = Path(r1["output_dir"])
    (d / "A_extraction_repair1.json").write_text(json.dumps(good_a))         # stands in for a repaired output on disk
    ad2 = Ad(outputs(ctx.doc_id))
    r2 = analysis_v3.resume(ctx, r1["analysis_id"], ad2)
    assert "A_extraction" not in ad2.calls and r2["analysis_id"] != r1["analysis_id"]
    assert r2["screening"] == "provisional_unresolved"
    assert ctx.con.execute("SELECT status FROM analysis_runs WHERE analysis_id=?", (r1["analysis_id"],)).fetchone()[0] == "analysis_failed"


def test_cap_table_total_beats_component_and_class_labels_normalise():
    claims = {k: {"citations": [{"doc_id": 1, "page": 1}]} for k in ("P", "A", "B", "O")}
    vi = {"price_per_share_usd": 1.0, "price_claim_id": "P", "convertible_instruments": [], "note": "", "share_counts": [
        {"kind": "issued_outstanding", "share_class": "Common", "value": 1, "as_of": "2025-12-31", "basis": "audited_balance_sheet", "claim_id": "A"},
        {"kind": "issued_outstanding", "share_class": "Common (ratified to founder)", "value": 75_000_000, "as_of": "2026-06-25",
         "basis": "board_ratification_or_issuance", "claim_id": "B"},
        {"kind": "issued_outstanding", "share_class": "Common (total)", "value": 75_000_001, "as_of": "2026-06-25",
         "basis": "form_c_capitalization_table", "claim_id": "B"},
        {"kind": "offered_maximum", "share_class": "Common", "value": 5_000_000, "as_of": "", "basis": "offering_terms", "claim_id": "O"}]}
    k = calc.implied_equity(vi, claims, {"P", "A", "B", "O"}, "equity")
    assert (k[0]["result_value"], k[0]["result_kind"]) == (75_000_001, "computed")
    assert any("historical" in x for x in k[0]["assumptions"])
    assert k[2]["result_value"] == 80_000_001
