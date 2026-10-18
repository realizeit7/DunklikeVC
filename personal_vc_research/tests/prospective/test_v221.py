"""v2.2.1 regression tests: rule-predicate satisfaction, critical review, typed calculations, legacy normalisation,
lineage, approval isolation. SYNTHETIC fixtures; they test logic, not semantic correctness or performance."""
import copy
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from prospective import analysis_v3, assess_v3, calc, journal, ledger, packs, typed_calc
from prospective import policy as policy_mod
from prospective.core import Ctx
from prospective.llm.schemas_v3 import QUESTIONS, RULE_IDS

import test_v22 as base

CFG = Path(__file__).resolve().parents[2] / "prospective" / "config.yaml"
DOC = base.DOC + ("The Company owes $199,875 to its founder; the liability has no specified interest rate or maturity date.\n"
                  "The Company entered a memorandum of understanding for a $50,000 convertible note that has not been issued.\n"
                  "The Company is in default on its secured loan and the lender has accelerated the full balance.\n"
                  "Risk factor: our financial condition raises substantial doubt about our ability to continue as a going concern.\n")


def claim(cid, text, quote, kind="form_field", dims=("FIN",), attribution="issuer Form C"):
    c = base.claim(cid, text, quote, kind, list(dims))
    c.pop("calculation")
    c["calc_request"] = None
    c["attribution"] = attribution
    return c


def outputs31(doc_id):
    o = base.outputs(doc_id)
    for c in o["A_extraction"]["claims"]:
        c.pop("calculation")
        c["calc_request"] = None
    extra = [claim("A15", "Founder payable $199,875, no maturity", "liability has no specified interest rate or maturity date"),
             claim("A16", "MOU for a $50,000 note, not issued", "memorandum of understanding for a $50,000 convertible note"),
             claim("A17", "Secured loan in default; balance accelerated", "is in default on its secured loan and the lender has accelerated",
                   "contract_term")]
    o["A_extraction"]["claims"] += extra
    for c in o["A_extraction"]["claims"]:
        for x in c["citations"]:
            x["doc_id"] = doc_id
    o["A_extraction"]["valuation_inputs"]["convertible_instruments"][0]["claim_ids"] = ["A16"]
    for f in o["D_final"]["rule_findings"]:
        f["predicate"] = {"elements": [], "branch": "", "overall": "unresolved", "missing_facts_ko": "", "temporal_conflicts_ko": ""}
    return o


def fin_finding(o, b1_facts, b1="established", review=None):
    """R-FIN-1 adverse, documented_distress branch FIN1-B1 assessed as `b1` with evidence `b1_facts`."""
    f = base.finding("R-FIN-1", "adverse", [(c, "supporting", "none") for c in b1_facts], "economic_concern")
    f["predicate"] = {"elements": [{"element_id": "FIN1-B1", "assessment": b1, "evidence_for": list(b1_facts), "evidence_against": [],
                                    "reasoning_ko": "문서에 근거한 판단입니다."},
                                   {"element_id": "FIN1-A1", "assessment": "unknown", "evidence_for": [], "evidence_against": [], "reasoning_ko": "자료가 없습니다."},
                                   {"element_id": "FIN1-A2", "assessment": "unknown", "evidence_for": [], "evidence_against": [], "reasoning_ko": "자료가 없습니다."},
                                   {"element_id": "FIN1-A3", "assessment": "unknown", "evidence_for": [], "evidence_against": [], "reasoning_ko": "자료가 없습니다."}],
                      "branch": "documented_distress", "overall": "met", "missing_facts_ko": "", "temporal_conflicts_ko": ""}
    o["D_final"]["rule_findings"] = [f if x["rule_id"] == "R-FIN-1" else x for x in o["D_final"]["rule_findings"]]
    o["_review"] = review if review is not None else [{"rule_id": "R-FIN-1", "review_overall": "met", "agrees_with_finding": True, "objections": []}]


class Ad31(base.Ad):
    def run(self, stage, system_prompt, payload, schema):
        out, meta = super().run(stage, system_prompt, payload, schema)
        if stage == "E_support_check" and isinstance(out, dict):
            out["predicate_reviews"] = copy.deepcopy(self.outs.get("_review", []))
        return out, meta


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
    c.pack = packs.build_pack(c, "O1", "2030-01-05T00:00:00+00:00")
    c.doc_id = json.loads(Path(c.pack["path"]).read_text())["documents"][0]["doc_id"]
    analysis_v3.register_v3(c, "v31test", "synthetic", ["O1"], repair_rounds=1, max_total_repairs=1, prompt_version="analyst_prompt_v3_2",
                            schema_version="analysis_schema_v3_1", policy_version="screening_policy_v1_3")
    return c


def run(ctx, o, verdicts=None):
    ad = Ad31(o, verdicts)
    return analysis_v3.run_v3(ctx, "O1", ctx.pack["pack_id"], ad, "v31test"), ad


def fin_row(ctx, aid):
    r = ctx.con.execute("SELECT * FROM rule_findings WHERE analysis_id=? AND rule_id='R-FIN-1'", (aid,)).fetchone()
    return dict(r), json.loads(r["validator_notes"])


# 1
def test_founder_payable_without_maturity_is_not_a_default(ctx):
    o = outputs31(ctx.doc_id)
    fin_finding(o, ["A15"])                                     # model claims FIN1-B1 established from the payable
    r, _ = run(ctx, o)
    row, notes = fin_row(ctx, r["analysis_id"])
    assert row["final_result"] == "adverse_contributing" and not row["independently_decisive"]
    assert any("evidence_must_mention" in n for n in notes) and r["screening"] == "provisional_unresolved"


# 2
def test_planned_note_is_not_issued_liability_or_threshold(ctx):
    o = outputs31(ctx.doc_id)
    fin_finding(o, ["A16"])
    r, _ = run(ctx, o)
    assert fin_row(ctx, r["analysis_id"])[0]["final_result"] == "adverse_contributing"
    claims = {c["claim_id"]: c for c in o["A_extraction"]["claims"]}
    req = {"kind": "post_money", "inputs": [
        {"role": "price", "claim_id": "A4", "value": "1.00", "unit": "USD_per_share", "security_class": "Common"},
        {"role": "shares_outstanding", "claim_id": "A16", "value": "50,000", "unit": "shares", "security_class": "Common"},
        {"role": "shares_offered", "claim_id": "A6", "value": "1,000,000", "unit": "shares", "security_class": "Common"}]}
    res = typed_calc.compute(req, claims, {}, planned_claim_ids={"A16"})
    assert any("PLANNED instrument" in e for e in res["errors"])


# 3
def test_issuer_risk_language_cannot_be_attributed_to_the_auditor(ctx):
    o = outputs31(ctx.doc_id)
    o["A_extraction"]["claims"].append(claim("A18", "Auditor expresses going-concern doubt", "substantial doubt about our ability to continue",
                                             attribution="independent auditor"))
    o["A_extraction"]["claims"][-1]["citations"][0]["doc_id"] = ctx.doc_id
    errs = analysis_v3.validate_stage("A_extraction", packs.load_pack(ctx, ctx.pack["pack_id"])[0], o,
                                      {"policy": policy_mod.load("screening_policy_v1_3"), "S": analysis_v3.schemas_v3_1})
    assert any("issuer statements are not auditor statements" in e for e in errs)


# 4
def test_specific_allowed_fact_cannot_reject_without_predicate(ctx):
    o = outputs31(ctx.doc_id)
    f = base.finding("R-TERMS-1", "adverse", [("A12", "supporting", "none")], "economic_concern")
    f["predicate"] = {"elements": [{"element_id": e, "assessment": "unknown", "evidence_for": [], "evidence_against": [], "reasoning_ko": "판단 보류입니다."}
                                   for e in ("TERMS1-1", "TERMS1-2", "TERMS1-3", "TERMS1-4")],
                      "branch": "", "overall": "met", "missing_facts_ko": "", "temporal_conflicts_ko": ""}
    o["D_final"]["rule_findings"] = [f if x["rule_id"] == "R-TERMS-1" else x for x in o["D_final"]["rule_findings"]]
    o["_review"] = [{"rule_id": "R-TERMS-1", "review_overall": "met", "agrees_with_finding": True, "objections": []}]
    r, _ = run(ctx, o)
    row = ctx.con.execute("SELECT final_result, validator_notes FROM rule_findings WHERE analysis_id=? AND rule_id='R-TERMS-1'",
                          (r["analysis_id"],)).fetchone()
    assert row[0] == "adverse_contributing" and "code wins" in row[1] and r["screening"] == "provisional_unresolved"


# 5
@pytest.mark.parametrize("b1,review", [
    ("contradicted", None),
    ("established", [{"rule_id": "R-FIN-1", "review_overall": "met", "agrees_with_finding": True,
                      "objections": [{"element_id": "FIN1-B1", "objection_ko": "대출 계약 원문이 없습니다.", "material": True, "resolved": False}]}]),
    ("established", [{"rule_id": "R-FIN-1", "review_overall": "unresolved", "agrees_with_finding": False, "objections": []}]),
    ("established", []),
])
def test_unmet_element_or_open_objection_blocks_decisiveness(ctx, b1, review):
    o = outputs31(ctx.doc_id)
    fin_finding(o, ["A17"], b1=b1, review=review)
    r, _ = run(ctx, o)
    if review == []:                         # a review stage that skips an adverse candidate fails validation itself
        assert r["screening"] == "analysis_failed" and any("predicate_reviews must review" in e for e in r["errors"])
        return
    assert not fin_row(ctx, r["analysis_id"])[0]["independently_decisive"] and r["screening"] != "provisional_reject"


# 6
def test_missing_inputs_give_unresolved_not_not_met_or_pass(ctx):
    pd = policy_mod.load("screening_policy_v1_3")["predicates"]["R-FIN-1"]
    overall, rows, _ = assess_v3.predicate_overall(pd, {"elements": []}, set(), {})
    assert overall == "unresolved" and all(x["assessment"] == "unknown" for x in rows)
    r, _ = run(ctx, outputs31(ctx.doc_id))
    assert r["screening"] == "provisional_unresolved"


# 7 + 8
def test_satisfied_predicate_rejects_and_is_not_masked_by_unknowns(ctx):
    o = outputs31(ctx.doc_id)
    fin_finding(o, ["A17"])
    r, _ = run(ctx, o)
    row, notes = fin_row(ctx, r["analysis_id"])
    assert row["final_result"] == "adverse_decisive" and r["screening"] == "provisional_reject" and r["decisive"] == ["R-FIN-1"]
    assert r["evidence_status"] == "sufficient_for_named_decision"          # other rules unknown, fees missing
    assert any("decisive" in n for n in notes)


# 9
def test_removing_unsupported_failures_does_not_create_a_pass(ctx):
    o = outputs31(ctx.doc_id)
    fin_finding(o, ["A15"])                                                  # unsupported -> removed as decisive
    r, _ = run(ctx, o)
    assert r["screening"] == "provisional_unresolved" and "eligible" not in r["screening"]


# 10
def test_proposed_and_unacknowledged_policies_cannot_authorize(ctx):
    o = outputs31(ctx.doc_id)
    fin_finding(o, ["A17"])
    r, _ = run(ctx, o)

    def appr(**kw):
        return ledger.approve(ctx, offering_id="O1", amount_usd="100", fee_usd=None, fee_basis=None, issuer_key_confirmed="0000000001",
                              min_investment_usd="100", applicable_terms="t", availability_note="a", contract_document_id=None,
                              override_rationale="x", **kw)
    for kw in (dict(analysis_id=r["analysis_id"]), dict(analysis_id=None, screening_policy_version="screening_policy_v1_3"),
               dict(analysis_id=None)):                                         # the last one is legacy v1, never acknowledged
        assert appr(**kw)["status"] == "blocked"
    ok, _ = policy_mod.approval_eligible(ctx, "screening_policy_v1_2", policy_mod.sha("screening_policy_v1_2"), assess_v3.CLASSIFIER_VERSION)
    assert not ok
    ctx.con.execute("INSERT INTO policy_activations(policy_kind, policy_version, policy_sha256, activated_utc, statement, actor, user_confirmed) "
                    "VALUES ('screening','screening_policy_v1_2',?,'t','synthetic test activation','user',1)", (policy_mod.sha("screening_policy_v1_2"),))
    ctx.con.commit()
    ok2, why = policy_mod.approval_eligible(ctx, "screening_policy_v1_2", policy_mod.sha("screening_policy_v1_2"), assess_v3.CLASSIFIER_VERSION)
    assert not ok2 and "not compatible" in why                                # activation never makes v2.2 results eligible
    ok3, why3 = policy_mod.approval_eligible(ctx, "screening_policy_v1_3", "0" * 64, assess_v3.CLASSIFIER_VERSION)
    assert not ok3
    p = subprocess.run([sys.executable, "-m", "prospective", "--config", str(ctx.tmp / "config.yaml"), "policy-activate",
                        "screening_policy_v1_3", "--sha256", policy_mod.sha("screening_policy_v1_3"), "--statement", "x" * 30,
                        "--i-am-the-user"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                       cwd=Path(__file__).resolve().parents[2])
    assert "interactive terminal" in p.stdout
    src = (Path(__file__).resolve().parents[2] / "prospective")
    for f in ("analysis_v3.py", "assess_v3.py", "analysis_v2.py", "brief_v3.py"):
        assert ".activate(" not in (src / f).read_text()


# 11
def test_typed_calculations_reproduce_arithmetic_and_reject_mismatches():
    claims = {"P": {"claim_text": "price $1.00", "citations": []}, "S": {"claim_text": "75,000,001 shares", "citations": []},
              "O": {"claim_text": "maximum 5,000,000 shares", "citations": []}, "C": {"claim_text": "cash $160,487.20", "citations": []},
              "N": {"claim_text": "net loss $56,126", "citations": []}}
    ok = typed_calc.compute({"kind": "implied_equity", "inputs": [
        {"role": "price", "claim_id": "P", "value": "1.00", "unit": "USD_per_share", "security_class": "Common"},
        {"role": "shares_outstanding", "claim_id": "S", "value": "75,000,001", "unit": "shares", "security_class": "Common (total)"}]}, claims)
    assert ok["errors"] == [] and ok["result_value"] == "75000001.00"
    k = calc.implied_equity({"price_per_share_usd": 1.0, "price_claim_id": "P", "convertible_instruments": [], "note": "",
                             "share_counts": [{"kind": "issued_outstanding", "share_class": "Common", "value": 75_000_001, "as_of": "2026-06-25",
                                               "basis": "form_c_capitalization_table", "claim_id": "S"}]},
                            {"P": {"citations": []}, "S": {"citations": []}}, {"P", "S"}, "equity")
    assert float(ok["result_value"]) == k[0]["result_value"]
    bad_unit = typed_calc.compute({"kind": "implied_equity", "inputs": [
        {"role": "price", "claim_id": "P", "value": "1.00", "unit": "USD", "security_class": "Common"},
        {"role": "shares_outstanding", "claim_id": "S", "value": "75,000,001", "unit": "shares", "security_class": "Common"}]}, claims)
    assert any("must be in USD_per_share" in e for e in bad_unit["errors"])
    bad_class = typed_calc.compute({"kind": "post_money", "inputs": [
        {"role": "price", "claim_id": "P", "value": "1.00", "unit": "USD_per_share", "security_class": "Common"},
        {"role": "shares_outstanding", "claim_id": "S", "value": "75,000,001", "unit": "shares", "security_class": "Common"},
        {"role": "shares_offered", "claim_id": "O", "value": "5,000,000", "unit": "shares", "security_class": "Series A Preferred"}]}, claims)
    assert any("security classes differ" in e for e in bad_class["errors"])
    invented = typed_calc.compute({"kind": "implied_equity", "inputs": [
        {"role": "price", "claim_id": "P", "value": "2.00", "unit": "USD_per_share"},
        {"role": "shares_outstanding", "claim_id": "S", "value": "75,000,001", "unit": "shares"}]}, claims)
    assert any("does not appear in claim" in e for e in invented["errors"])
    stale = typed_calc.compute({"kind": "runway_months", "inputs": [
        {"role": "cash", "claim_id": "C", "value": "160,487.20", "unit": "USD", "as_of": "2026-06-18"},
        {"role": "spending", "claim_id": "N", "value": "56,126", "unit": "USD", "period_start": "2025-01-01", "period_end": "2025-12-31"}]}, claims)
    assert stale["result_kind"] == "withheld" and "not aligned" in stale["withheld_reason"]
    assert typed_calc.compute({"kind": "exit_multiple", "inputs": []}, claims)["errors"]


# 12
def test_cosmetic_legacy_normalisation_is_logged_and_numbers_are_never_repaired():
    n = typed_calc.normalize_legacy_formula("K1: price_per_share * issued_shares")
    assert n["ok"] and n["normalized"] == "price_per_share * issued_shares" and "label" in n["log"] and n["original"].startswith("K1:")
    assert not typed_calc.normalize_legacy_formula("K1: price_per_share * ")["ok"]
    assert not typed_calc.normalize_legacy_formula("K1: __import__('os')")["ok"]
    calcs = {"K1": {"formula": "price_per_share * issued_shares", "inputs": [{"name": "price_per_share", "value": 1},
                                                                             {"name": "issued_shares", "value": 75000001}],
                    "result_value": 75000001.0}}
    legacy = {"additional_claims": [{"claim_id": "B12", "calculation": {"formula": "K1: price_per_share * issued_shares",
              "inputs": [{"name": "price_per_share", "value": 1, "claim_id": "A03"}, {"name": "issued_shares", "value": 75000001, "claim_id": "A13"}],
              "result": 75000001}}]}
    for c in legacy["additional_claims"][0]["calculation"]["inputs"]:
        c.pop("claim_id")
    out, log = analysis_v3.migrate_cached_stage("B_analysis", legacy, calcs)
    assert out["additional_claims"][0]["calc_request"] == {"kind": "ref", "k_ref": "K1", "inputs": []} and log[0]["original"].startswith("K1:")
    changed = copy.deepcopy(legacy)
    changed["additional_claims"][0]["calculation"]["result"] = 80000001
    out2, log2 = analysis_v3.migrate_cached_stage("B_analysis", changed, calcs)
    assert out2 is None and "rejected" in log2[-1]["action"]


# 13
def test_resume_lineage_and_repair_counters_cannot_reset(ctx):
    o = outputs31(ctx.doc_id)
    o["A_extraction"]["claims"][0]["citations"][0]["quote"] = "a quote that is not on the page at all"
    r1, ad1 = run(ctx, o)
    assert r1["screening"] == "analysis_failed" and ad1.calls.count("A_extraction") == 2     # original + 1 repair (cap)
    ad2 = Ad31(o)
    r2 = analysis_v3.resume(ctx, r1["analysis_id"], ad2)                                     # no new authorization
    assert ad2.calls.count("A_extraction") == 1 and r2["screening"] == "analysis_failed"   # zero repairs in the child
    ad3 = Ad31(o)
    r3 = analysis_v3.resume(ctx, r2["analysis_id"], ad3)
    assert ad3.calls.count("A_extraction") == 1
    assert analysis_v3.lineage(ctx, r3["analysis_id"]) == [r3["analysis_id"], r2["analysis_id"], r1["analysis_id"]]
    assert analysis_v3.lineage_repairs(ctx, r3["analysis_id"]) == 1
    n = json.loads(ctx.con.execute("SELECT notes FROM analysis_runs WHERE analysis_id=?", (r3["analysis_id"],)).fetchone()[0])
    assert n["parent_analysis_id"] == r2["analysis_id"] and n["lineage_repairs_before"] == 1 and n["extra_repairs_authorized"] == 0
    ad4 = Ad31(o)
    analysis_v3.resume(ctx, r3["analysis_id"], ad4, extra_repairs_authorized=1, authorization_note="synthetic authorization")
    assert ad4.calls.count("A_extraction") == 2                                             # exactly the authorized one


# 14
def test_originals_forecasts_ledger_and_exports_intact(ctx):
    from prospective import outputs as out_mod
    pid = journal.add_forecast(ctx, "O1", "old forecast", "business", 12, 0.2, "rule", 30, "unresolved", "v1")
    s0 = ledger.current_state(ctx)
    r0, _ = run(ctx, outputs31(ctx.doc_id))
    before = dict(ctx.con.execute("SELECT * FROM analysis_runs WHERE analysis_id=?", (r0["analysis_id"],)).fetchone())
    o = outputs31(ctx.doc_id)
    fin_finding(o, ["A17"])
    run(ctx, o)
    assert dict(ctx.con.execute("SELECT * FROM analysis_runs WHERE analysis_id=?", (r0["analysis_id"],)).fetchone()) == before
    assert ctx.con.execute("SELECT target_event FROM predictions WHERE prediction_id=?", (pid,)).fetchone()[0] == "old forecast"
    s1 = ledger.current_state(ctx)
    assert (s1.annual_remaining_cents, s1.period_label) == (s0.annual_remaining_cents, s0.period_label) and s1.annual_remaining_cents == 1_200_000
    assert "policy_activations" not in out_mod.EXPORT_TABLES and "approvals" not in out_mod.EXPORT_TABLES
    with pytest.raises(sqlite3.IntegrityError):
        ctx.con.execute("UPDATE rule_findings SET final_result='not_adverse'")


def test_brief_shows_predicate_elements_and_review(ctx):
    from prospective.brief_v3 import build_brief_v3
    o = outputs31(ctx.doc_id)
    fin_finding(o, ["A15"], review=[{"rule_id": "R-FIN-1", "review_overall": "unresolved", "agrees_with_finding": False,
                                     "objections": [{"element_id": "FIN1-B1", "objection_ko": "만기 미기재는 채무불이행이 아닙니다.", "material": True, "resolved": False}]}])
    r, _ = run(ctx, o)
    b = build_brief_v3(ctx, r["analysis_id"], out_dir=ctx.tmp / "b").read_text()
    assert "요소 FIN1-B1" in b and "불리 정의(정확한 문구)" in b and "2차 모델 검토(독립 검증 아님)" in b and "미해결" in b
    assert "제안된 정책에 따른 잠정 분류" in b and "SCHG" in b


def test_korean_validator_allows_acronyms_but_not_english_prose():
    from prospective.analysis_v2 import korean_errors
    assert korean_errors("x", "IRB 제출, FDA 상호작용, 기기 분류.") == []
    assert korean_errors("x", "SCHG 대비 구체적 이유 없음; Form C-AR 미제출") == []
    assert any("too much English" in e or "English passage" in e
               for e in korean_errors("x", "the company has not filed anything with regulators yet 회사"))


def test_claim_prefix_relabel_is_letter_only_and_rejects_mixed():
    from prospective.analysis_v3 import normalize_claim_prefix
    out = {"claims": [{"claim_id": "C1", "claim_text": "x"}, {"claim_id": "C2", "claim_text": "y"}],
           "fees": {"minimum_claim_id": "C2", "investor_fee_claim_ids": ["C1"]},
           "document_conflicts": [{"claim_ids": ["C1", "C2"], "material": True}]}
    new, log = normalize_claim_prefix("A_extraction", out)
    assert [c["claim_id"] for c in new["claims"]] == ["A1", "A2"]
    assert new["fees"] == {"minimum_claim_id": "A2", "investor_fee_claim_ids": ["A1"]}
    assert new["document_conflicts"][0]["claim_ids"] == ["A1", "A2"]
    assert new["claims"][0]["claim_text"] == "x" and out["claims"][0]["claim_id"] == "C1" and log
    assert normalize_claim_prefix("A_extraction", new) == (new, [])
    mixed = {"claims": [{"claim_id": "C1"}, {"claim_id": "B2"}]}
    assert normalize_claim_prefix("A_extraction", mixed)[0] is None


def test_validator_0_4_ignores_code_identifiers_and_particle_attached_acronyms():
    from prospective.analysis_v2 import korean_errors
    assert korean_errors("x", "p.9와 XML의 priceDeterminationMethod가 임의 결정을 확인한다. 가격 1.00달러도 XML에 있다.") == []
    assert korean_errors("x", "회사는 revenue growth를 보였다")
    assert korean_errors("x", "This sentence is plainly written in English words 한국")
