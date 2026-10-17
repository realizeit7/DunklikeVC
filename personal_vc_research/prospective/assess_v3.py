"""v2.2 screening classifier for screening_policy_v1_2. Code, not the LLM, derives every result from validated rule
findings.

A rule finding is DECISIVE only when all of these hold:
1. the policy rule allows independent rejection;
2. the model reports it adverse;
3. at least one SUPPORTING fact is a valid cited claim (or a computed K-id) of an evidence kind the rule allows;
4. that fact is not a generic trigger (G1–G8). The trigger is the model's tag, or a keyword match on the claim text:
   the stricter of the two applies, which can only reduce decisiveness, never create it;
5. the structured support check rated that fact `supported` without material overstatement.

Otherwise an adverse finding is `adverse_contributing`: shown, never erased, but not decisive. Missing information is
`unknown`; it is never favorable, adverse or zero.
"""
from __future__ import annotations

import json
import re

from . import assess, ledger
from .core import Ctx

CLASSIFIER_VERSION = "assessment_classifier_v3_1"
# v3_1 (2026-10-17, v2.2.1): a finding is decisive only if the rule's AUTHORED predicate (policy `predicates`) is met
# as computed by code from the element assessments (deterministic elements evaluated by code), AND the stage-E
# predicate review agrees with no material unresolved objection. Under a policy without authored predicates
# (v1_2) nothing can be decisive. Earlier: a valid, specific, support-checked fact was enough (the flaw).
# v3_0_1 (2026-10-17): G4 also matches "no assurance" next to Reg A / IPO / listing / liquidity / conversion
# (Hope-Neuron A32: a stated interest in a Reg A offering "with no assurance it will happen" is a missing liquidity
# promise, i.e. generic).
GENERIC_KEYWORDS = {
    "G1": r"pre-revenue|no revenue|revenue of \$?0\b|\$0(\.00)? revenue|has not generated revenue",
    "G3": r"going concern|going-concern|substantial doubt",
    # absence-type phrasing only: a documented repurchase BELOW the price paid is company-specific, not G4
    "G4": (r"no (promised |expected )?dividends?|not entitle\w* .{0,40}dividends?|dividends? (are|is) not (expected|promised|guaranteed)|"
           r"no (right to |obligation to )?(buyback|repurchase)|no (repurchase|buyback) right|no (public |trading )?market|"
           r"no (plan\w* (for|to) )?(an )?IPO|no (assured |guaranteed )?(listing|liquidity event)|"
           r"(reg(ulation)? a\b|ipo|listing|liquidity)[^.]{0,160}no assurance|no assurance[^.]{0,160}(reg(ulation)? a\b|ipo|listing|liquidity|conversion)"),
    "G5": r"anti-dilution",
    "G6": r"transfer restrict|one-year|resale|custodian|nominee|illiquid|minority",
    "G7": r"arbitrar",
    "G8": r"\bproxy\b|voting right|non-voting|no vote",
}
GENERIC_LABEL_KO = {"G1": "매출 전 단계", "G2": "과거 재무제표의 낮은 현금", "G3": "계속기업 관련 공시", "G4": "배당·환매·IPO 약속 없음",
                    "G5": "희석방지권 없음", "G6": "소수 지분·일반적 비유동성", "G7": "'임의' 가격 공시", "G8": "의결권 부재·의결권 위임"}


def keyword_triggers(text: str) -> set[str]:
    return {g for g, pat in GENERIC_KEYWORDS.items() if re.search(pat, text or "", re.I)}


def _stale_cash(c: dict, cutoff: str) -> bool:
    import datetime as dt
    if not c.get("as_of") or not re.search(r"\bcash\b", c["claim_text"], re.I):
        return False
    return (dt.date.fromisoformat(cutoff[:10]) - dt.date.fromisoformat(c["as_of"])).days > 180


DETERMINISTIC_ELEMENTS = {
    # FIN1-A2: same-period cash and spending exist <=> the software runway calculation was NOT withheld
    "FIN1-A2": lambda calcs: ("established" if any(k.get("calc_type") == "runway_months" and k.get("result_kind") in ("computed", "illustrative")
                                                  for k in calcs.values()) else "unknown"),
}


def _mentions(el: dict, fact_ids: list[str], texts: dict) -> bool:
    pats = el.get("evidence_must_mention")
    if not pats:
        return True
    return any(re.search(p, texts.get(f, ""), re.I) for f in fact_ids for p in pats)


def predicate_overall(pred_def: dict, model_pred: dict | None, valid: set, calcs: dict,
                      texts: dict | None = None) -> tuple[str, list[dict], list[str]]:
    """Code-computed predicate outcome. Elements not assessed by the model are 'unknown'. 'established' needs at least
    one valid evidence_for fact; deterministic elements are evaluated by code (the model's view is recorded)."""
    notes: list[str] = []
    given = {e["element_id"]: e for e in (model_pred or {}).get("elements", [])}
    if pred_def.get("applicability") and (model_pred or {}).get("overall") == "not_applicable":
        return "not_applicable", [], ["model marked the rule not applicable (applicability: " + pred_def["applicability"] + ")"]
    groups = pred_def["branches"] if pred_def.get("logic") == "any_branch" else {"all": pred_def["elements"]}
    rows, outcome = [], {}
    for g, els in groups.items():
        res = []
        for el in els:
            m = given.get(el["id"], {})
            a = m.get("assessment", "unknown")
            if el["mode"] == "deterministic" and el["id"] in DETERMINISTIC_ELEMENTS:
                d = DETERMINISTIC_ELEMENTS[el["id"]](calcs)
                if d != a:
                    notes.append(f"{el['id']}: model said {a}, code evaluated {d} (deterministic element)")
                a = d
            elif a == "established" and not any(f in valid or f in calcs for f in m.get("evidence_for", [])):
                notes.append(f"{el['id']}: 'established' without a valid evidence_for fact -> unknown")
                a = "unknown"
            elif a == "established" and not _mentions(el, [f for f in m.get("evidence_for", []) if f in valid], texts or {}):
                notes.append(f"{el['id']}: no evidence_for fact states the required event (evidence_must_mention) -> unknown")
                a = "unknown"
            res.append(a)
            rows.append({"branch": g, "element_id": el["id"], "text": el["text"], "mode": el["mode"], "assessment": a,
                         "model_assessment": m.get("assessment", "not assessed"), "evidence_for": m.get("evidence_for", []),
                         "evidence_against": m.get("evidence_against", []), "reasoning_ko": m.get("reasoning_ko", "")})
        outcome[g] = "met" if all(x == "established" for x in res) else ("not_met" if "contradicted" in res else "unresolved")
    vals = list(outcome.values())
    overall = "met" if "met" in vals else ("not_met" if all(v == "not_met" for v in vals) else "unresolved")
    extra = set(given) - {e["id"] for els in groups.values() for e in els}
    if extra:
        notes.append(f"model assessed non-authored elements {sorted(extra)}: ignored")
    if model_pred and model_pred.get("overall") and model_pred["overall"] != overall:
        notes.append(f"model overall '{model_pred['overall']}' differs from code '{overall}': code wins")
    return overall, rows, notes


def evaluate_findings(policy: dict, outputs: dict, by_id: dict, valid: set, calcs: dict, checks: dict,
                      cutoff: str = "") -> list[dict]:
    rules = policy["_rules"]
    rows = []
    for f in outputs["D_final"]["rule_findings"]:
        rule = rules[f["rule_id"]]
        notes: list[str] = []
        facts = []
        pred_rows: list[dict] = []
        review = None
        for x in f["facts"]:
            c = by_id.get(x["claim_id"])
            k = calcs.get(x["claim_id"])
            trig = {x["generic_trigger"]} - {"none"}
            if c:
                kw = keyword_triggers(c["claim_text"]) | ({"G2"} if cutoff and _stale_cash(c, cutoff) else set())
                if kw - trig:
                    notes.append(f"{x['claim_id']}: generic trigger(s) {sorted(kw - trig)} added by keyword rule")
                trig |= kw
            facts.append({**x, "generic_effective": sorted(trig), "valid": (x["claim_id"] in valid) or bool(k and k["result_kind"] == "computed"),
                          "evidence_kind": c["evidence_kind"] if c else ("calculation" if k else None),
                          "claim_text": c["claim_text"] if c else (f"{k['calc_type']} = {k['result_value']}" if k else ""),
                          "attribution": c.get("attribution", "") if c else "code calculation",
                          "as_of": c.get("as_of", "") if c else "",
                          "citations": [{"doc_id": z["doc_id"], "page": z["page"], "quote": z["quote"]} for z in c["citations"]] if c else [],
                          "support_check": (checks.get(x["claim_id"]) or {}).get("verdict")})
        allowed = set(rule.get("allowed_support_kinds") or [])
        sup = [x for x in facts if x["role"] == "supporting"]
        final, decisive = f["result"], False
        if f["result"] == "adverse":
            cand = [x for x in sup if x["valid"] and (not allowed or x["evidence_kind"] in allowed)]
            specific = [x for x in cand if not x["generic_effective"]]
            checked = [x for x in specific if x["claim_id"] in checks and checks[x["claim_id"]]["verdict"] == "supported"
                       and checks[x["claim_id"]]["overstatement"] != "material"]
            if not rule["independent_rejection"]:
                final, why = "adverse_contributing", "rule cannot independently reject"
            elif not cand:
                final, why = "adverse_contributing", "no valid supporting fact of an allowed evidence kind"
            elif not specific:
                final, why = "adverse_contributing", "all supporting facts are generic triggers"
            elif not checked:
                final, why = "adverse_contributing", "no company-specific fact passed the support check"
            else:
                final, why, decisive = "adverse_decisive", "fact checks passed", True
            notes.append(why)
            if decisive:
                texts = {cid: c["claim_text"] + " " + " ".join(z["quote"] for z in c.get("citations", [])) for cid, c in by_id.items()}
                final, decisive, pnotes, pred_rows, review = _predicate_gate(policy, f, outputs, valid, calcs, texts)
                notes += pnotes
        elif f["result"] == "not_adverse":
            if not any(x["valid"] for x in sup):
                final = "unknown"
                notes.append("not_adverse without a valid supporting fact: unknown")
        rows.append({"rule_id": f["rule_id"], "rule_text": rule["text"], "adverse_definition": rule.get("adverse_definition", ""),
                     "predicate_elements": pred_rows, "predicate_review": review, "rule_type": rule["type"],
                     "independent_rejection_allowed": rule["independent_rejection"], "model_result": f["result"],
                     "final_result": final, "independently_decisive": decisive, "model_claimed_decisive": f["claims_independently_decisive"],
                     "scope": f["scope"], "facts": facts, "interpretation_ko": f["interpretation_ko"],
                     "counterevidence_ko": f["counterevidence_ko"], "unresolved_ko": f["unresolved_ko"],
                     "what_would_change_ko": f["what_would_change_ko"], "validator_notes": notes})
    return rows


def _predicate_gate(policy: dict, f: dict, outputs: dict, valid: set, calcs: dict, texts: dict | None = None):
    """After the fact checks pass: predicate met (code) + review agreement without material unresolved objection."""
    preds = policy.get("predicates") or {}
    pd = preds.get(f["rule_id"])
    if pd is None:
        return ("adverse_contributing", False, [f"no authored predicate for {f['rule_id']} in {policy['version']}: cannot be decisive "
                                                f"under {CLASSIFIER_VERSION}"], [], None)
    overall, rows, notes = predicate_overall(pd, f.get("predicate"), valid, calcs, texts)
    reviews = {r["rule_id"]: r for r in (outputs.get("E_support_check") or {}).get("predicate_reviews", [])}
    rv = reviews.get(f["rule_id"])
    if overall == "not_applicable":
        return "not_applicable", False, notes + ["rule not applicable"], rows, rv
    if overall != "met":
        return "adverse_contributing", False, notes + [f"predicate {overall} (code): not decisive"], rows, rv
    if rv is None:
        return "adverse_contributing", False, notes + ["no critical review of this candidate: not decisive"], rows, rv
    open_obj = [o for o in rv["objections"] if o["material"] and not o["resolved"]]
    if open_obj:
        return "adverse_contributing", False, notes + [f"{len(open_obj)} material unresolved review objection(s): not decisive"], rows, rv
    if rv["review_overall"] != "met" or not rv["agrees_with_finding"]:
        return "adverse_contributing", False, notes + [f"review disagrees (review: {rv['review_overall']}): not decisive"], rows, rv
    return "adverse_decisive", True, notes + ["predicate met (code) and review agrees: decisive"], rows, rv


def evaluate_preferences(policy: dict, outputs: dict, calcs: dict, checks: dict) -> list[dict]:
    out = []
    model = {p["pref_id"]: p for p in outputs["D_final"].get("preference_findings", [])}
    for p in policy.get("preferences", []):
        if not p.get("enabled"):
            continue
        res = {"pref_id": p["id"], "text": p["text"], "breached": "unknown", "basis": ""}
        if p["id"] == "P-1":
            k = next((c for c in calcs.values() if c["calc_type"] == "implied_pre_money_equity"), None)
            lim = p["parameters"].get("max_implied_pre_money")
            if k and k["result_kind"] == "computed" and lim is not None:
                res.update(breached="yes" if k["result_value"] > lim else "no",
                           basis=f"{k['calc_id']} = {k['result_value']:,.0f} vs limit {lim:,.0f} (deterministic)")
            else:
                res["basis"] = "implied pre-money not computed or no limit: unknown"
        else:
            m = model.get(p["id"])
            if m and m["breached"] == "yes" and any(checks.get(c, {}).get("verdict") == "supported" for c in m["claim_ids"]):
                res.update(breached="yes", basis="model finding, support-checked: " + m["note_ko"])
            elif m:
                res.update(breached="no" if m["breached"] == "no" else "unknown", basis=m["note_ko"])
        out.append(res)
    return out


def thesis_status(outputs: dict, valid: set, calcs: dict) -> tuple[str, list[str]]:
    notes, answers = [], {t["question_id"]: t for t in outputs["D_final"]["thesis"]}
    ok = lambda t: any(c in valid or c in calcs for c in t["claim_ids"])  # noqa: E731
    if any(t["status"] == "contradicted" and ok(t) for t in answers.values()):
        return "contradicted", [f"{q}: contradicted by cited evidence" for q, t in answers.items() if t["status"] == "contradicted"]
    core = [q for q in answers if q != "Q7_vs_schg"]
    if all(answers[q]["status"] == "supported" and ok(answers[q]) for q in core) and \
            answers.get("Q7_vs_schg", {}).get("status") == "specific_reason_supported" and ok(answers["Q7_vs_schg"]):
        return "supported", notes
    for q, t in answers.items():
        if t["status"] in ("unknown", "no_substantiated_advantage_identified") or not ok(t):
            notes.append(f"{q}: {t['status']}{'' if ok(t) else ' (no valid citation)'}")
    return "incomplete", notes


def budget_detail(ctx: Ctx, offering_id: str, outputs: dict) -> dict:
    o = ctx.con.execute("SELECT issuer_id FROM offerings WHERE offering_id=?", (offering_id,)).fetchone()
    key = ledger.issuer_key_for(ctx, o["issuer_id"])[0]
    st = ledger.current_state(ctx)
    fees = (outputs.get("A_extraction") or {}).get("fees") or {}
    return {"checked_utc": ctx.now(), "period": st.period_label,
            "annual_remaining_usd": ledger.usd(st.annual_remaining_cents),
            "issuer_remaining_usd": ledger.usd(st.issuer_remaining_cents(key)), "issuer_key": key,
            "minimum_investment_usd": fees.get("minimum_investment_usd"),
            "investor_fee_status": "stated_in_pack_unconfirmed" if fees.get("investor_paid_fee_stated") else "not_stated",
            "total_cost_verifiable": False,
            "note": ("investor-paid fees are not verified: total cost cannot yet be verified (fees are not assumed zero and the "
                     "budget is not reported as exceeded)")}


def evaluate(ctx: Ctx, errors: list[str], outputs: dict, pack: dict, policy: dict, policy_state: str, by_id: dict, valid: set,
             calcs: dict, offering: dict) -> dict:
    prefix = "" if policy_state == "active" else "provisional_"
    av = assess.availability_observations(ctx, offering["offering_id"])
    execution = {"availability": assess._operational(offering, av),
                 "required_before_any_investment": ["offering availability at decision time", "investor-paid fee confirmation",
                                                    "the operative contract as signed at checkout"]}
    if errors:
        return {"screening": "analysis_failed", "evidence_status": "insufficient", "evidence_scope": "analysis did not validate",
                "thesis_status": "incomplete", "thesis_notes": ["analysis did not validate"], "findings": [], "preferences": [],
                "decisive": [], "execution": execution, "budget": budget_detail(ctx, offering["offering_id"], outputs)}
    checks = {c["claim_id"]: c for c in (outputs.get("E_support_check") or {}).get("checks", [])}
    rows = evaluate_findings(policy, outputs, by_id, valid, calcs, checks, pack["cutoff_utc"])
    prefs = evaluate_preferences(policy, outputs, calcs, checks)
    decisive = [r["rule_id"] for r in rows if r["independently_decisive"]] + [p["pref_id"] for p in prefs if p["breached"] == "yes"]
    indep = [r for r in rows if r["independent_rejection_allowed"]]
    ev1 = next((r for r in rows if r["rule_id"] == "R-EV1"), None)
    if decisive:
        screening = prefix + "reject"
    elif all(r["final_result"] in ("not_adverse", "not_applicable") for r in indep) and ev1 and ev1["final_result"] == "not_adverse" \
            and not pack.get("gaps"):
        screening = prefix + "eligible_for_review"
    else:
        screening = prefix + "unresolved"
    conflicts = [c for c in outputs["A_extraction"].get("document_conflicts", []) if c["material"]]
    decisive_facts = {x["claim_id"] for r in rows if r["independently_decisive"] for x in r["facts"] if x["role"] == "supporting"}
    if any(set(c["claim_ids"]) & decisive_facts for c in conflicts):
        ev, scope = "conflicting", "a material document conflict touches a decisive fact"
    elif pack.get("gaps") and screening != prefix + "eligible_for_review":
        ev, scope = "insufficient", "unread pack pages may hold counterevidence: " + "; ".join(g["detail"] for g in pack["gaps"])[:300]
    elif screening.endswith("unresolved"):
        ev, scope = "insufficient", "not sufficient for any screening decision under " + policy["version"]
    else:
        ev = "sufficient_for_named_decision"
        scope = (f"sufficient only for '{screening}' under {policy['version']} ({policy_state}); "
                 + ("decisive: " + ", ".join(decisive) if decisive else "eligible for USER REVIEW only")
                 + ". This is not a statement that diligence is complete.")
    ts, tnotes = thesis_status(outputs, valid, calcs)
    return {"screening": screening, "evidence_status": ev, "evidence_scope": scope, "thesis_status": ts, "thesis_notes": tnotes,
            "findings": rows, "preferences": prefs, "decisive": decisive, "execution": execution,
            "budget": budget_detail(ctx, offering["offering_id"], outputs), "conflicts": conflicts}


def next_actions(res: dict, pack: dict) -> list[str]:
    s = res["screening"]
    if s == "analysis_failed":
        return ["분석이 검증을 통과하지 못했습니다. 이는 분석 미완료이며 회사의 미공개를 뜻하지 않습니다. 오류를 고쳐 다시 실행하세요."]
    acts = []
    if s.endswith("reject"):
        acts.append("결정적 사유의 원문 페이지를 직접 확인하는 것 외에는 추가 수집이 필요하지 않습니다(" + ", ".join(res["decisive"]) + ").")
    elif s.endswith("unresolved"):
        unk = [r for r in res["findings"] if r["independent_rejection_allowed"] and r["final_result"] in ("unknown", "adverse_contributing")]
        for r in unk[:3]:
            if r["what_would_change_ko"]:
                acts.append(f"{r['rule_id']}: {r['what_would_change_ko']}")
        acts.append("미결 상태에서는 투자 결정을 내릴 근거가 부족합니다. 위 자료를 얻을 수 없다면 기회비용(SCHG) 대비 이 건을 보류하는 것이 합리적입니다.")
    else:
        acts.append("사용자 검토 대상입니다. 투자 전 모집 진행 여부와 투자자 부담 수수료를 본인 브라우저에서 확인하세요(실행 조건).")
    if pack.get("gaps"):
        acts.append("팩에서 읽지 못한 페이지가 있습니다: " + "; ".join(g["detail"] for g in pack["gaps"])[:200])
    return acts
