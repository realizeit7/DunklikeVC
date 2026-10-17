"""Analyst v3 pipeline (v2.2) for screening_policy_v1_2 (PROPOSED). It reuses the v2 mechanics: stage-by-stage
validation, capped targeted repair, original and repaired outputs both kept, per-stage usage, presentation-only
stage F.

New in v3:
* Evidence-kind / dimension validation. A preclinical efficacy claim cannot carry the DEMAND dimension or support
  the demand rule.
* One structured finding per policy rule, with per-fact roles and generic-trigger tags. assess_v3 decides
  decisiveness.
* Seven thesis questions, a deterministic runway (withheld on stale spending) and an investor-proceeds scenario that
  is withheld unless every input truly exists.
* Results are labelled provisional unless the policy version + hash has a user activation row.
* `analysis_runs.status` for a v3 run is `needs_information` (or `analysis_failed`). v3 results never feed the
  approval path; ledger.approve also refuses analyses screened under a non-active policy.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import jsonschema

from . import assess_v3, calc
from . import policy as policy_mod
from .analysis import claims_checks
from .analysis_v2 import COST_LABEL, korean_errors, _usage_row
from .core import Ctx
from .llm.schemas_v1 import CRITICAL_ITEMS
from .llm.schemas_v3 import QUESTIONS, RULE_IDS, SCHEMA_VERSION, STAGE_ORDER, STAGES
from .packs import load_pack

PROMPT_VERSION = "analyst_prompt_v3"
PIPELINE_VERSION = "analysis_v3_pipeline_0_1"
POLICY_VERSION = "screening_policy_v1_2"
PROMPTS = Path(__file__).parent / "llm" / "prompts"
MAX_SUPPORT_CHECKS = 24
ATTRIBUTION_KO = re.compile(r"회사 설명에 따르면|회사에 따르면|발행사에 따르면|회사가 밝힌|발행사가 밝힌|회사는 .{0,30}(설명|주장|밝히)")

TASK = {
    "A_extraction": "Stage A: evidence extraction under v3 rules (evidence_kind, dimensions, attribution, as_of, cash/spending "
                    "points, all share counts with basis, existing vs planned convertibles, issuer- vs investor-paid fees, conflicts).",
    "B_analysis": "Stage B: analysis by evidence dimension (new claim ids B1..). Cite K ids for arithmetic.",
    "C_critical_review": "Stage C: critical review (new claim ids C1..). Look especially for dimension misclassification and for generic "
                         "triggers used as decisive.",
    "D_final": "Stage D: one finding per policy rule, the seven thesis questions, enabled preference findings, critique responses.",
    "E_support_check": "Stage E: structured support check of each claim in claims_to_check (model judgment, not verification).",
    "F_brief_ko": "Stage F: Korean prose. The classification is computed and fixed.",
}


def _schema(stage, out):
    if out is None:
        return [f"{stage}: missing output"]
    return [f"{stage}: schema: {e.message[:160]} at {'/'.join(map(str, e.absolute_path))}"
            for e in jsonschema.Draft202012Validator(STAGES[stage]).iter_errors(out)]


def _partial(outputs):
    return {k: outputs.get(k) or ({"claims": []} if k == "A_extraction" else {"additional_claims": [], "issues": []})
            for k in ("A_extraction", "B_analysis", "C_critical_review")}


def validate_stage(stage: str, pack: dict, outputs: dict, ctxd: dict) -> list[str]:
    errs = _schema(stage, outputs.get(stage))
    if errs:
        return errs
    pol = ctxd["policy"]
    if stage in ("A_extraction", "B_analysis", "C_critical_review"):
        claims, by_id, valid, check_refs = claims_checks(pack, _partial(outputs), errs)
        new = outputs[stage]["claims" if stage == "A_extraction" else "additional_claims"]
        for c in new:
            if len(c["dimensions"]) > 1 and not c["dimension_rationale"].strip():
                errs.append(f"{c['claim_id']}: more than one dimension requires dimension_rationale")
            if c["evidence_kind"] == "preclinical_efficacy" and "DEMAND" in c["dimensions"]:
                errs.append(f"{c['claim_id']}: preclinical efficacy evidence cannot be classified as commercial DEMAND evidence")
        known = set(by_id) | set(ctxd.get("calcs", {}))
        if stage == "A_extraction":
            a = outputs[stage]
            refs = [r for ci in a["critical_items"] for r in ci["claim_ids"]]
            vi = a["valuation_inputs"]
            refs += ([vi["price_claim_id"]] if vi["price_per_share_usd"] is not None else []) + [c["claim_id"] for c in vi["share_counts"]]
            refs += [r for cv in vi["convertible_instruments"] for r in cv["claim_ids"]]
            refs += [c["claim_id"] for c in a["cash_points"]] + [c["claim_id"] for c in a["spending_points"]]
            refs += a["fees"]["investor_fee_claim_ids"] + a["fees"]["issuer_paid_fee_claim_ids"] + a["financial_statements"]["claim_ids"]
            refs += [r for d in a["document_conflicts"] for r in d["claim_ids"]]
            check_refs("A references", [r for r in refs if r])
            items = [ci["item"] for ci in a["critical_items"]]
            if sorted(items) != sorted(CRITICAL_ITEMS):
                errs.append(f"A_extraction: critical_items must list each of the 7 items once, got {items}")
        else:
            secs = outputs[stage].items() if stage == "B_analysis" else enumerate(outputs[stage]["issues"])
            for k, sec in secs:
                if isinstance(sec, dict) and "claim_ids" in sec:
                    errs += [f"{stage}.{k}: unknown id {r}" for r in sec["claim_ids"] if r not in known]
        return errs
    claims, by_id, valid, _ = claims_checks(pack, outputs, [])
    known = set(by_id) | set(ctxd.get("calcs", {}))
    if stage == "D_final":
        d = outputs[stage]
        ids = [f["rule_id"] for f in d["rule_findings"]]
        if sorted(ids) != sorted(RULE_IDS):
            errs.append(f"D_final: rule_findings must contain each policy rule once, got {ids}")
        rules = pol["_rules"]
        for f in d["rule_findings"]:
            w = f"finding {f['rule_id']}"
            for x in f["facts"]:
                if x["claim_id"] not in known:
                    errs.append(f"{w}: unknown id {x['claim_id']}")
                    continue
                c = by_id.get(x["claim_id"])
                allowed = set(rules[f["rule_id"]].get("allowed_support_kinds") or [])
                if c and x["role"] == "supporting" and allowed and f["result"] in ("adverse", "not_adverse") \
                        and c["evidence_kind"] not in allowed:
                    errs.append(f"{w}: {x['claim_id']} ({c['evidence_kind']}) cannot support {f['rule_id']}; allowed: {sorted(allowed)}")
                if c and c["evidence_status"] == "unverified_assertion" and x["role"] == "supporting":
                    errs.append(f"{w}: unverified assertion {x['claim_id']} used as support")
            if f["result"] == "adverse" and not [x for x in f["facts"] if x["role"] == "supporting"]:
                errs.append(f"{w}: an adverse finding needs at least one supporting fact")
            if f["result"] == "adverse" and f["scope"] == "none":
                errs.append(f"{w}: an adverse finding needs a scope")
            for k in ("interpretation_ko", "counterevidence_ko", "unresolved_ko", "what_would_change_ko"):
                errs += korean_errors(f"{w}.{k}", f[k])
        qs = [t["question_id"] for t in d["thesis"]]
        if sorted(qs) != sorted(QUESTIONS):
            errs.append(f"D_final: thesis must answer each of the 7 questions once, got {qs}")
        for t in d["thesis"]:
            errs += [f"thesis {t['question_id']}: unknown id {r}" for r in t["claim_ids"] if r not in known]
            if t["status"] in ("specific_reason_supported", "no_substantiated_advantage_identified") and t["question_id"] != "Q7_vs_schg":
                errs.append(f"thesis {t['question_id']}: status {t['status']} is only for Q7")
            errs += korean_errors(f"thesis {t['question_id']}", t["answer_ko"])
            if re.search(r"\d+(\.\d+)?\s?%", t["answer_ko"]) and not t["claim_ids"]:
                errs.append(f"thesis {t['question_id']}: a percentage needs a cited basis")
        enabled = {p["id"] for p in pol.get("preferences", []) if p.get("enabled")}
        extra = {p["pref_id"] for p in d["preference_findings"]} - enabled
        if extra:
            errs.append(f"D_final: preference findings for preferences that are not enabled: {sorted(extra)}")
        n = len(outputs["C_critical_review"]["issues"])
        miss = set(range(n)) - {r["issue_index"] for r in d["critique_responses"]}
        if miss:
            errs.append(f"D_final: critique issues without a response: {sorted(miss)}")
    if stage == "E_support_check":
        got = sorted(c["claim_id"] for c in outputs[stage]["checks"])
        if got != sorted(ctxd["claims_to_check"]):
            errs.append(f"E_support_check: must check exactly {ctxd['claims_to_check']}; got {got}")
        for ch in outputs[stage]["checks"]:
            errs += korean_errors(f"E.{ch['claim_id']}.note_ko", ch["note_ko"])
    if stage == "F_brief_ko":
        f = outputs[stage]
        errs += korean_errors("F.company_ko", f["company_ko"]) + korean_errors("F.why_could_work_ko", f["why_could_work_ko"])
        if not ATTRIBUTION_KO.search(f["company_ko"]):
            errs.append("F.company_ko: attribute the description to the issuer (e.g. '회사 설명에 따르면')")
        for k in ("unknowns_ko", "what_would_change_ko"):
            for i, t in enumerate(f[k]):
                errs += korean_errors(f"F.{k}[{i}]", t)
        errs += [f"F: reference [{r}] to unknown id" for r in re.findall(r"\[([ABCK]\d{1,3})\]", json.dumps(f, ensure_ascii=False))
                 if r not in known]
    return errs


def _claims_to_check(outputs: dict, by_id: dict, policy: dict) -> list[str]:
    adverse, other = [], []
    for f in outputs["D_final"]["rule_findings"]:
        for x in f["facts"]:
            if x["role"] == "supporting" and x["claim_id"] in by_id:
                (adverse if f["result"] == "adverse" else other).append(x["claim_id"])
        if f["result"] == "not_adverse" and policy["_rules"][f["rule_id"]]["independent_rejection"]:
            pass
    out = list(dict.fromkeys(adverse))
    for c in other:
        if len(out) >= MAX_SUPPORT_CHECKS:
            break
        if c not in out:
            out.append(c)
    return out


def _payload(stage, pack, outputs, ctxd):
    pol = ctxd["policy"]
    pol_view = {"version": pol["version"], "state": ctxd["policy_state"], "rules": pol["rules"],
                "generic_triggers": pol["generic_triggers"], "evidence_dimensions": pol["evidence_dimensions"],
                "enabled_preferences": [p for p in pol.get("preferences", []) if p.get("enabled")],
                "benchmark_alternative": pol["benchmark_alternative"]}
    base = {"task": TASK[stage], "screening_policy": pol_view}
    if stage in ("A_extraction", "B_analysis", "C_critical_review", "D_final"):
        base.update({"prior_stage_outputs": {k: outputs[k] for k in STAGE_ORDER[:STAGE_ORDER.index(stage)]},
                     "deterministic_calculations": list(ctxd.get("calcs", {}).values()), "evidence_pack": pack,
                     "thesis_questions": QUESTIONS})
    elif stage == "E_support_check":
        _, by_id, _, _ = claims_checks(pack, outputs, [])
        texts = {(p["doc_id"], p["page"]): p["text"] for p in pack["pages"]}
        base.update({"claims_to_check": ctxd["claims_to_check"], "untrusted_content_notice": pack["untrusted_content_notice"],
                     "items": [{"claim": by_id[c], "cited_pages": [{"doc_id": x["doc_id"], "page": x["page"],
                                                                    "page_text": texts.get((x["doc_id"], x["page"]), "")[:12000]}
                                                                   for x in by_id[c]["citations"]]} for c in ctxd["claims_to_check"]]})
    else:
        res = ctxd["assessment"]
        _, by_id, _, _ = claims_checks(pack, outputs, [])
        base.update({"computed_classification": {k: res[k] for k in ("screening", "evidence_status", "evidence_scope", "thesis_status",
                                                                     "decisive")},
                     "rule_findings": [{k: r[k] for k in ("rule_id", "final_result", "interpretation_ko", "unresolved_ko")} for r in res["findings"]],
                     "thesis": outputs["D_final"]["thesis"], "deterministic_calculations": list(ctxd.get("calcs", {}).values()),
                     "claims": [{k: c[k] for k in ("claim_id", "claim_text", "evidence_kind", "attribution", "as_of")} for c in by_id.values()],
                     "offering": pack["offering"]})
    return json.dumps(base, ensure_ascii=False)


def compute_calcs(pack: dict, outputs: dict) -> dict:
    _, by_id, valid, _ = claims_checks(pack, outputs, [])
    a = outputs["A_extraction"]
    ks = calc.implied_equity(a["valuation_inputs"], by_id, valid, pack["offering"].get("security_class") or "")
    rw = calc.runway(a["cash_points"], a["spending_points"], valid)
    pr = calc.investor_proceeds(pack["offering"].get("security_class") or "", {})
    for extra in (rw, pr):
        extra = {"formula": "see calc.py", "inputs": extra.get("inputs", []), "assumptions": extra.get("assumptions", []),
                 "included_instruments": [], "excluded_instruments": [], **extra}
        ks.append({**extra, "calc_id": f"K{len(ks) + 1}"})
    return {k["calc_id"]: k for k in ks}


def register_v3(ctx: Ctx, version_id: str, description: str, development_offering_ids: list[str], repair_rounds: int = 1,
                model_requested: str | None = None) -> None:
    ctx.con.execute("INSERT OR IGNORE INTO analyst_versions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (version_id, "challenger", PROMPT_VERSION, SCHEMA_VERSION, POLICY_VERSION, model_requested,
                     json.dumps({"tools": "disabled", "max_budget_usd_per_stage": 5.0, "repair_rounds": repair_rounds,
                                 "pipeline": "analysis_v3", "classifier": assess_v3.CLASSIFIER_VERSION,
                                 "calculator": calc.CALCULATOR_VERSION}),
                     description, ctx.now(), json.dumps(development_offering_ids)))
    ctx.con.commit()


def run_v3(ctx: Ctx, offering_id: str, pack_id: str, adapter, version_id: str, note: str = "",
           repair_override: int | None = None, policy_override: dict | None = None) -> dict:
    v = ctx.con.execute("SELECT * FROM analyst_versions WHERE version_id=?", (version_id,)).fetchone()
    if v is None:
        raise ValueError(f"analyst version {version_id} is not registered")
    cap = int(json.loads(v["settings"] or "{}").get("repair_rounds", 0)) if repair_override is None else repair_override
    pack, pack_sha = load_pack(ctx, pack_id)
    if pack["offering"]["offering_id"] != offering_id:
        raise ValueError("pack belongs to another offering")
    pol = policy_override or policy_mod.load(POLICY_VERSION)
    pstate = "proposed" if policy_override else policy_mod.state(ctx, POLICY_VERSION)
    system_prompt = (PROMPTS / f"{v['prompt_version']}.md").read_text()
    started = ctx.now()
    out_dir = ctx.root / ctx.cfg.raw["paths"].get("analyses_dir", "data/analyses") / f"{offering_id}_{started.replace(':', '')}_v3"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs, usage, errors, presentation = {}, [], [], []
    ctxd = {"calcs": {}, "policy": pol, "policy_state": pstate}
    o = dict(ctx.con.execute("SELECT * FROM offerings WHERE offering_id=?", (offering_id,)).fetchone())

    def attempt(stage, label, payload):
        out, meta = adapter.run(stage, system_prompt, payload, STAGES[stage])
        (out_dir / f"{stage}{label}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        (out_dir / f"{stage}{label}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        return out, meta or {}

    res = None
    for stage in STAGE_ORDER:
        if stage == "E_support_check":
            _, by_id, _, _ = claims_checks(pack, outputs, [])
            ctxd["claims_to_check"] = _claims_to_check(outputs, by_id, pol)
        if stage == "F_brief_ko":
            res = _assess(ctx, [], outputs, pack, pol, pstate, ctxd, o)
            ctxd["assessment"] = res
        payload = _payload(stage, pack, outputs, ctxd)
        out, meta = attempt(stage, "", payload)
        outputs[stage] = out
        errs = validate_stage(stage, pack, outputs, ctxd)
        usage.append(_usage_row(stage, "original", meta, errs))
        rnd = 0
        while errs and rnd < cap:
            rnd += 1
            rp = json.dumps({"task": "REPAIR: your previous output for this stage failed mechanical validation. Return the complete "
                                     "corrected output. Fix exactly the listed errors; do not change conclusions the errors do not concern.",
                             "validation_errors": errs[:40], "previous_output": outputs[stage], "original_request": json.loads(payload)},
                            ensure_ascii=False)
            out2, meta2 = attempt(stage, f"_repair{rnd}", rp)
            if out2 is not None:
                outputs[stage] = out2
            errs = validate_stage(stage, pack, outputs, ctxd)
            usage.append(_usage_row(stage, f"repair{rnd}", meta2, errs))
        if errs and stage == "F_brief_ko":
            presentation, outputs[stage] = errs, None
            break
        if errs:
            errors = errs
            break
        if stage == "A_extraction":
            ctxd["calcs"] = compute_calcs(pack, outputs)
    if errors:
        res = _assess(ctx, errors, outputs, pack, pol, pstate, ctxd, o)
    return _store(ctx, offering_id, pack_id, pack, pack_sha, v, adapter, started, ctx.now(), outputs, usage, ctxd, errors,
                  presentation, res, out_dir, note, pol, pstate)


def _assess(ctx, errors, outputs, pack, pol, pstate, ctxd, o):
    by_id, valid = {}, set()
    if not errors:
        _, by_id, valid, _ = claims_checks(pack, outputs, [])
    return assess_v3.evaluate(ctx, errors, outputs, pack, pol, pstate, by_id, valid, ctxd.get("calcs", {}), o)


def _store(ctx, offering_id, pack_id, pack, pack_sha, v, adapter, started, finished, outputs, usage, ctxd, errors, presentation,
           res, out_dir, note, pol, pstate):
    combined = json.dumps({"outputs": outputs, "usage": usage, "calcs": ctxd.get("calcs"), "claims_to_check": ctxd.get("claims_to_check"),
                           "assessment": res}, sort_keys=True, ensure_ascii=False, default=str)
    (out_dir / "combined.json").write_text(combined)
    models = sorted({u["model"] for u in usage if u.get("model")})
    cost = sum(u["cost_estimate_usd"] or 0 for u in usage)
    dev = json.loads(v["development_offering_ids"])
    status = "analysis_failed" if errors else "needs_information"
    cur = ctx.con.execute(
        """INSERT INTO analysis_runs(offering_id, pack_id, pack_sha256, version_id, prompt_version, schema_version, policy_version,
           adapter, model_reported, provider_reported, settings, started_utc, finished_utc, status, split, output_path,
           output_sha256, validation_errors, cost_usd, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (offering_id, pack_id, pack_sha, v["version_id"], v["prompt_version"], SCHEMA_VERSION, pol["version"], adapter.name,
         ";".join(models) or None, None, v["settings"], started, finished, status, "development" if offering_id in dev else "evaluation",
         str(out_dir.relative_to(ctx.root)), hashlib.sha256(combined.encode()).hexdigest(), json.dumps(errors), cost,
         json.dumps({"pipeline": "analysis_v3", "pipeline_version": PIPELINE_VERSION, "policy_sha256": pol["_sha256"],
                     "policy_state": pstate, "status_column_note": "placeholder; v3 results live in assessments_v3 and never feed approvals",
                     "presentation_errors": presentation, "note": note, "cost_label": COST_LABEL}, ensure_ascii=False)))
    aid = cur.lastrowid
    now = ctx.now()
    if not errors:
        claims, _, _, _ = claims_checks(pack, outputs, [])
        for c in claims:
            ctx.con.execute("""INSERT INTO analysis_claims(analysis_id, claim_id, stage, claim_text, claim_type, evidence_status, citations,
                observed_cutoff_utc, financial_period, calculation_inputs, contradictions, missing) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (aid, c["claim_id"], {"A": "A_extraction", "B": "B_analysis", "C": "C_critical_review"}[c["claim_id"][0]],
                             c["claim_text"], c["claim_type"], c["evidence_status"], json.dumps(c["citations"], ensure_ascii=False),
                             pack["cutoff_utc"], c["financial_period"],
                             json.dumps({"evidence_kind": c["evidence_kind"], "dimensions": c["dimensions"], "attribution": c["attribution"],
                                         "as_of": c["as_of"], "calculation": c.get("calculation")}, ensure_ascii=False),
                             c["contradictions"], ""))
    for k in ctxd.get("calcs", {}).values():
        ctx.con.execute("INSERT INTO calculations(analysis_id, pack_id, calc_type, formula, inputs, assumptions, included_instruments, "
                        "excluded_instruments, units, result_value, result_kind, withheld_reason, calculator_version, created_utc) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, pack_id, f"{k['calc_id']}:{k['calc_type']}", k.get("formula", ""), json.dumps(k.get("inputs", [])),
                         json.dumps(k.get("assumptions", [])), json.dumps(k.get("included_instruments", [])),
                         json.dumps(k.get("excluded_instruments", [])), k.get("units", ""), k.get("result_value"), k["result_kind"],
                         k.get("withheld_reason", ""), k["calculator_version"], now))
    models_label = f"model:{';'.join(models)}"
    for ch in (outputs.get("E_support_check") or {}).get("checks", []) if not errors else []:
        ctx.con.execute("INSERT INTO support_checks(analysis_id, claim_id, checker, judgment_label, citation_exists, passage_supports, "
                        "omitted_qualifications, evidence_type, conflicts, overstatement, verdict, note, checked_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, ch["claim_id"], models_label, "model_judgment_not_verification", 1, ch["passage_supports"],
                         ch["omitted_qualifications"], ch["evidence_type"], ch["conflicts"], ch["overstatement"], ch["verdict"],
                         ch["note_ko"], now))
    for r in res["findings"]:
        ctx.con.execute("INSERT INTO rule_findings(analysis_id, rule_id, rule_text, policy_version, policy_sha256, policy_state, model_result, "
                        "final_result, scope, independently_decisive, facts, interpretation_ko, counterevidence, unresolved_ko, "
                        "what_would_change_ko, validator_notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, r["rule_id"], r["rule_text"], pol["version"], pol["_sha256"], pstate, r["model_result"], r["final_result"],
                         r["scope"], int(r["independently_decisive"]), json.dumps(r["facts"], ensure_ascii=False), r["interpretation_ko"],
                         r["counterevidence_ko"], r["unresolved_ko"], r["what_would_change_ko"], json.dumps(r["validator_notes"])))
    for t in (outputs.get("D_final") or {}).get("thesis", []) if not errors else []:
        ctx.con.execute("INSERT INTO thesis_answers(analysis_id, question_id, status, answer_ko, claim_ids) VALUES (?,?,?,?,?)",
                        (aid, t["question_id"], t["status"], t["answer_ko"], json.dumps(t["claim_ids"])))
    ctx.con.execute("INSERT INTO assessments_v3(analysis_id, classifier_version, policy_version, policy_sha256, policy_state, screening, "
                    "evidence_status, evidence_scope, thesis_status, thesis_notes, execution, budget, decisive, created_utc, notes) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (aid, assess_v3.CLASSIFIER_VERSION, pol["version"], pol["_sha256"], pstate, res["screening"], res["evidence_status"],
                     res["evidence_scope"], res["thesis_status"], json.dumps(res["thesis_notes"], ensure_ascii=False),
                     json.dumps(res["execution"], ensure_ascii=False), json.dumps(res["budget"], ensure_ascii=False),
                     json.dumps(res["decisive"]), now, json.dumps({"preferences": res["preferences"]}, ensure_ascii=False)))
    for u in usage:
        ctx.con.execute("INSERT INTO stage_usage(analysis_id, run_dir, stage, attempt, seconds, input_tokens, output_tokens, cache_read_tokens, "
                        "cache_creation_tokens, cost_estimate_usd, cost_label, outcome, n_errors) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, str(out_dir.relative_to(ctx.root)), u["stage"], u["attempt"], u["seconds"], u["input_tokens"],
                         u["output_tokens"], u["cache_read_tokens"], u["cache_creation_tokens"], u["cost_estimate_usd"], COST_LABEL,
                         u["outcome"], u["n_errors"]))
    ctx.con.commit()
    return {"analysis_id": aid, "screening": res["screening"], "evidence_status": res["evidence_status"],
            "thesis_status": res["thesis_status"], "decisive": res["decisive"], "n_errors": len(errors), "errors": errors[:15],
            "presentation_errors": presentation, "models": models, "cost_estimate_usd": round(cost, 4), "output_dir": str(out_dir),
            "policy_state": pstate, "policy_sha256": pol["_sha256"]}
