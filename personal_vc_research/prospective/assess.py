"""v2.1 assessment: four separate dimensions, criterion-level aggregation, freshness and next-action priority.

Implementation (no policy change):
* An alleged failure counts only if it is SUPPORTED. That means at least one decisive ground, a valid cited claim or
  computed calculation, and a model support check that did not reject it. Otherwise the criterion is `unresolved`.
* Parse/validation failure means the analysis is incomplete. It is never read as the issuer not disclosing something.
* Freshness: "no new filings" is stated only for an interval covered by a successful source check.

Proposed policy change (screening_policy_v1_1, NOT acknowledged; see policies/). The v2.1 aggregation:
* A supported failure of a required criterion gives `fails_current_screen`, even when other information is missing.
* Operational availability and investor fees are reported as separate dimensions. They no longer block the
  assessment.

The legacy policy-v1 status is still computed and stored in analysis_runs.status. The approval path still uses it.
"""
from __future__ import annotations

import datetime as dt
import json

from .core import Ctx, iso, parse_utc
from .llm.schemas_v2 import CRITERIA, NON_DECISIVE_GROUNDS

CLASSIFIER_VERSION = "assessment_classifier_v2_1_1"
# v2_1_1 (2026-10-15, manual spot check of analysis 10): budget status 'eligible' now also needs an investor-fee
# confirmation from the user. In v2_1 the model marked `minimum_investment_and_fees` confirmed from the
# issuer-paid intermediary fee (claim A6), which says nothing about what the investor pays. Investor fees are shown
# at checkout, not in the filing, so before an approval the status is `incomplete_cost_information`.
PROPOSED_POLICY = "screening_policy_v1_1_proposed_unacknowledged"
OPERATIONAL_ITEMS = {"closing_or_availability_evidence", "minimum_investment_and_fees"}


def criterion_final(c: dict, by_id: dict, valid_cited: set, calcs: dict, checks: dict) -> dict:
    """Deterministic support rules for one model criterion result."""
    ids = c["claim_ids"]
    evid = [i for i in ids if i in valid_cited and by_id[i]["evidence_status"] != "unverified_assertion"]
    computed = [i for i in ids if i in calcs and calcs[i]["result_kind"] == "computed"]
    notes: list[str] = []
    checked = [checks[i] for i in ids if i in checks]
    rejected = [ch for ch in checked if ch["verdict"] == "not_supported"]
    good = [ch for ch in checked if ch["verdict"] == "supported" and ch["overstatement"] != "material"]
    if c["result"] == "unknown":
        return {"final": "unresolved", "support": "model_unknown", "notes": notes}
    if c["result"] == "pass":
        if not (evid or computed):
            return {"final": "unresolved", "support": "pass_without_valid_evidence", "notes": ["no valid cited claim"]}
        if checked and len(rejected) == len(checked):
            return {"final": "unresolved", "support": "pass_rejected_by_support_check", "notes": notes}
        return {"final": "pass", "support": "supported" if good else "mechanically_valid_only", "notes": notes}
    # alleged failure
    grounds = set(c["failure_grounds"])
    decisive = grounds - NON_DECISIVE_GROUNDS
    if not decisive:
        return {"final": "unresolved", "support": "unsupported_non_decisive_grounds_only",
                "notes": [f"grounds {sorted(grounds) or '[]'} cannot on their own support a failure"]}
    if decisive == {"deterministic_calculation"} and not computed:
        return {"final": "unresolved", "support": "calculation_not_computed",
                "notes": ["the cited calculation was withheld or illustrative"]}
    if not (evid or computed):
        return {"final": "unresolved", "support": "no_valid_evidence", "notes": ["no valid cited claim or computed calculation"]}
    if not good:
        why = "rejected by support check" if rejected else "only partial support or material overstatement"
        return {"final": "unresolved", "support": "support_check_not_passed", "notes": [why]}
    return {"final": "fail", "support": "supported", "notes": notes}


def evaluate(errors: list[str], outputs: dict, critical: dict, by_id: dict, valid_cited: set, calcs: dict,
             pack: dict, offering: dict, availability: dict, budget: dict, investor_fee_confirmed: bool = False) -> dict:
    if errors:
        return {"assessment": "analysis_failed", "evidence_completeness": "extraction_incomplete",
                "operational_readiness": _operational(offering, availability), "budget_status": _budget(budget, critical, investor_fee_confirmed),
                "criteria": [], "decisive": [], "unresolved": list(CRITERIA),
                "reasons": [f"분석 출력이 기계적 검증을 통과하지 못했습니다(오류 {len(errors)}건). 회사의 미공개가 아니라 분석 미완료입니다."]}
    checks = {ch["claim_id"]: ch for ch in (outputs.get("E_support_check") or {}).get("checks", [])}
    rows = []
    for c in outputs["D_final"]["criteria"]:
        f = criterion_final(c, by_id, valid_cited, calcs, checks)
        rows.append({"criterion_id": c["criterion_id"], "gate": CRITERIA[c["criterion_id"]], "required": True,
                     "model_result": c["result"], "final_result": f["final"], "support": f["support"], "claim_ids": c["claim_ids"],
                     "failure_grounds": c["failure_grounds"], "reason_ko": c["reason_ko"],
                     "what_would_change_ko": c["what_would_change_ko"], "validator_notes": f["notes"]})
    fails = [r for r in rows if r["final_result"] == "fail"]
    unresolved = [r["criterion_id"] for r in rows if r["final_result"] == "unresolved"]
    a_items = {ci["item"]: ci for ci in outputs["A_extraction"]["critical_items"]}
    unreadable = bool(pack.get("gaps")) or any(ci["status"] == "not_readable_in_pack" for ci in a_items.values())
    substantive_missing = [k for k, v in critical.items() if v == "not_confirmed" and k not in OPERATIONAL_ITEMS]
    if fails:
        assessment = "fails_current_screen"
    elif not unresolved and len(rows) == len(CRITERIA) and not unreadable:
        assessment = "passes_current_screen"
    else:
        assessment = "indeterminate"
    if unreadable and assessment != "fails_current_screen":
        completeness = "extraction_incomplete"
    elif assessment == "fails_current_screen":
        completeness = "sufficient_for_current_conclusion"
    elif substantive_missing or unresolved:
        completeness = "material_gaps"
    else:
        completeness = "sufficient_for_current_conclusion"
    return {"assessment": assessment, "evidence_completeness": completeness,
            "operational_readiness": _operational(offering, availability),
            "budget_status": _budget(budget, critical, investor_fee_confirmed), "criteria": rows, "decisive": [r["criterion_id"] for r in fails], "unresolved": unresolved,
            "substantive_missing": substantive_missing, "extraction_gaps": [g["detail"] for g in pack.get("gaps", [])],
            "reasons": [f"{r['criterion_id']}: {r['reason_ko']}" for r in fails]}


def _operational(o: dict, availability: dict) -> str:
    if o.get("availability_status") in ("withdrawn", "closed_reported") or (o.get("closing_status") or "none_reported") != "none_reported":
        return "unavailable_or_closed"
    if o.get("availability_status") in ("open_verified", "available_verified"):
        return "available_verified"
    if availability.get("attempts"):
        return "availability_unknown"
    return "not_checked"


def _budget(budget: dict, critical: dict, investor_fee_confirmed: bool = False) -> str:
    if budget.get("result") == "fail":
        return "ineligible"
    if critical.get("minimum_investment_and_fees") != "confirmed" or not investor_fee_confirmed:
        return "incomplete_cost_information"
    return "eligible"


# ---- availability and freshness ------------------------------------------------------------------------
def availability_observations(ctx: Ctx, offering_id: str) -> dict:
    o = ctx.con.execute("SELECT legal_name FROM offerings WHERE offering_id=?", (offering_id,)).fetchone()
    rows = []
    if ctx.con.execute("SELECT 1 FROM sqlite_master WHERE name='access_attempts'").fetchone():
        slug = {"RCF-2114933-020-37299": "hope-neuron", "RCF-2147043-020-37424": "mightylicious",
                "RCF-2128340-020-37393": "tradefunded"}.get(offering_id, "")
        rows = [dict(r) for r in ctx.con.execute(
            "SELECT attempted_utc, url, method, result FROM access_attempts WHERE url LIKE ? OR url LIKE ? ORDER BY attempt_id",
            ("%republic.com/companies%", f"%republic.com/{slug}%" if slug else "%no-match%"))]
    blocks = [dict(r) for r in ctx.con.execute(
        "SELECT utc AS attempted_utc, url, detail AS result FROM gaps WHERE kind='access_blocked' AND url LIKE '%republic.com%' ORDER BY utc")]
    return {"attempts": rows + blocks, "legal_name": o["legal_name"] if o else ""}


def freshness(ctx: Ctx, offering_id: str, analysis_finished_utc: str, pack: dict, outputs: dict | None) -> dict:
    now = parse_utc(ctx.now())
    cutoff = pack["cutoff_utc"]
    out = {"as_of": iso(now), "analysis_finished_utc": analysis_finished_utc,
           "analysis_age_days": round((now - parse_utc(analysis_finished_utc)).total_seconds() / 86400, 1),
           "evidence_cutoff_utc": cutoff}
    sc = [dict(r) for r in ctx.con.execute("SELECT * FROM source_checks WHERE offering_id=? ORDER BY check_id", (offering_id,))] \
        if ctx.con.execute("SELECT 1 FROM sqlite_master WHERE name='source_checks'").fetchone() else []
    ok = [r for r in sc if r["success"] == 1]
    failed_after = [r for r in sc if r["success"] == 0 and (not ok or r["checked_utc"] > ok[-1]["checked_utc"])]
    out["last_successful_source_check_utc"] = ok[-1]["checked_utc"] if ok else None
    out["failed_source_checks_since_last_success"] = len(failed_after)
    covering = [r for r in ok if (r["covers_from_utc"] or "") <= cutoff and (r["covers_to_utc"] or "") >= cutoff]
    if covering:
        last = covering[-1]
        newer = [dict(r) for r in ctx.con.execute(
            "SELECT event_type, event_date, accession FROM events WHERE offering_id=? AND observed_utc > ? ORDER BY event_date",
            (offering_id, cutoff))]
        out["new_filings_since_cutoff"] = (f"{len(newer)} new filing event(s) observed after the evidence cutoff" if newer
                                           else f"no new filings observed between the cutoff and {last['covers_to_utc']} "
                                                f"(successful EDGAR check)")
        out["new_filings_detail"] = newer
    else:
        out["new_filings_since_cutoff"] = "not established: no successful source check covers the interval after the cutoff"
    fs = (outputs or {}).get("A_extraction", {}).get("financial_statements") if outputs else None
    if fs and fs.get("period_end"):
        pe = parse_utc(fs["period_end"])
        months = (parse_utc(cutoff) - pe).days / 30.4375
        out.update({"financial_period_end": fs["period_end"], "financial_assurance": fs["assurance"],
                    "financial_age_months_at_cutoff": round(months, 1),
                    "financial_age_months_now": round((now - pe).days / 30.4375, 1),
                    "financial_stale_rule": "stale if > 15 months at the cutoff (proposed convention, unvalidated)",
                    "financial_stale": months > 15})
    else:
        out.update({"financial_period_end": None, "financial_stale": None})
    docs = {d["doc_id"]: d for d in pack["documents"]}
    contract_docs = sorted({d["doc_id"] for d in pack["documents"] if d.get("contract_marker_pages")})
    out["contract_observed_utc"] = [docs[i]["retrieved_utc"] for i in contract_docs] or None
    av = availability_observations(ctx, offering_id)
    out["availability_observation"] = (f"not observed; last attempt {av['attempts'][-1]['attempted_utc']} "
                                       f"({av['attempts'][-1]['result']})" if av["attempts"] else "never checked")
    out["known_outages"] = sorted({f"{a['url']}: {a['result']}" for a in av["attempts"] if a["result"] != "public_content"})[:5]
    return out


# ---- next actions (deterministic priority) ----------------------------------------------------------------
def next_actions(res: dict, fresh: dict) -> list[str]:
    a, comp, op = res["assessment"], res["evidence_completeness"], res["operational_readiness"]
    acts: list[str] = []
    if a == "analysis_failed":
        return ["분석 재실행 또는 표적 수정(repair): 출력이 검증을 통과하지 못했습니다. 이는 분석이 끝나지 않은 것이지 회사가 정보를 공개하지 않은 것이 아닙니다."]
    if a == "fails_current_screen":
        acts.append("추가 자료 수집은 우선순위가 낮습니다. 결정적 사유가 유지되는 한 결론은 바뀌지 않습니다.")
        acts.append("결론을 다시 보려면, 결정적 사유(" + ", ".join(res["decisive"]) + ")의 인용 원문을 직접 확인하는 것이 첫 단계입니다.")
        if comp == "extraction_incomplete":
            acts.append("읽지 못한 문서가 있어 결정적 사유와 무관한지 확인이 필요합니다.")
        return acts
    if comp == "extraction_incomplete":
        acts.append("읽지 못한 문서(대용량·이미지 PDF 등)에서 계약서와 재무제표 페이지를 먼저 추출(OCR)하세요: " +
                    "; ".join(res.get("extraction_gaps", [])[:2]))
    if a == "indeterminate":
        for r in res["criteria"]:
            if r["final_result"] == "unresolved" and r["what_would_change_ko"]:
                acts.append(f"{r['criterion_id']} 미결: {r['what_would_change_ko']}")
            if len(acts) >= 3:
                break
    if a == "passes_current_screen":
        if op != "available_verified":
            acts.append("실행 차단 요소: 모집이 아직 진행 중인지 본인 브라우저에서 확인하세요(현재 확인 불가).")
        if res["budget_status"] == "incomplete_cost_information":
            acts.append("투자자 부담 수수료와 최소 투자금을 확인하세요.")
    if "not established" in fresh.get("new_filings_since_cutoff", ""):
        acts.append("EDGAR 후속 점검(followup)이 성공하지 않아 새 공시 여부를 알 수 없습니다. 점검을 먼저 실행하세요.")
    return acts or ["현재 우선 조치 없음."]
