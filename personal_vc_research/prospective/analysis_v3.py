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
from .analysis import WS_MATCHES, claims_checks
from .analysis_v2 import COST_LABEL, korean_errors, _usage_row
from .core import Ctx
from .llm.schemas_v1 import CRITICAL_ITEMS
from .llm import schemas_v3, schemas_v3_1
from .llm.schemas_v3 import QUESTIONS, RULE_IDS, SCHEMA_VERSION, STAGE_ORDER, STAGES
from .packs import load_pack

PROMPT_VERSION = "analyst_prompt_v3"
PIPELINE_VERSION = "analysis_v3_pipeline_0_3"
# 0_3 (2026-10-17, final-review prep): read-only plan_resume() (resume uses it) and explicit provenance of reused
# stages (original run, prompt, schema, model). Validation and classification are unchanged.
CITATION_RULE = "citation_rule_3_1_whitespace_insensitive"
# 0_2 (2026-10-17, after run 15): citation rule 3_1 (whitespace-only differences accepted and recorded) and resume():
# continue the SAME workflow from a run's validated stage outputs, with the run's repair budget carried over.
POLICY_VERSION = "screening_policy_v1_2"
PROMPTS = Path(__file__).parent / "llm" / "prompts"
MAX_SUPPORT_CHECKS = 24
AUDITOR_ATTR = re.compile(r"\bauditor|independent accountant|audit report|accountant'?s (review )?report|감사인|감사보고서|회계사", re.I)
AUDIT_REPORT_PAGE = re.compile(r"independent auditor|auditor[’']s report|accountants?[’']? (review )?report|report of independent|"
                               r"independent accountants?[’']? review", re.I)
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


SCHEMA_MODULES = {"analysis_schema_v3_0": schemas_v3, "analysis_schema_v3_1": schemas_v3_1}


def _S(ctxd):
    return ctxd.get("S", schemas_v3)


def _typed(ctxd) -> bool:
    return _S(ctxd) is schemas_v3_1


def _cc(pack, outs, errs, ctxd):
    return claims_checks(pack, outs, errs, whitespace_insensitive=True, typed_calcs=_typed(ctxd))


def _schema(stage, out, ctxd=None):
    if out is None:
        return [f"{stage}: missing output"]
    return [f"{stage}: schema: {e.message[:160]} at {'/'.join(map(str, e.absolute_path))}"
            for e in jsonschema.Draft202012Validator(_S(ctxd or {}).STAGES[stage]).iter_errors(out)]


def typed_calc_errors(new_claims: list[dict], by_id: dict, ctxd: dict) -> list[str]:
    """v3_1: compute every calc_request with typed_calc; validation problems are stage errors."""
    from . import typed_calc
    a = (ctxd.get("outputs_ref") or {}).get("A_extraction") or {}
    planned = {cid for cv in (a.get("valuation_inputs") or {}).get("convertible_instruments", [])
               if cv.get("status") == "planned" for cid in cv.get("claim_ids", [])}
    errs = []
    for c in new_claims:
        req = c.get("calc_request")
        if not req:
            continue
        res = typed_calc.compute(req, by_id, ctxd.get("calcs", {}), planned)
        errs += [f"{c['claim_id']}: {e}" for e in res["errors"]]
        ctxd.setdefault("typed", {})[c["claim_id"]] = res
    return errs


def _partial(outputs):
    return {k: outputs.get(k) or ({"claims": []} if k == "A_extraction" else {"additional_claims": [], "issues": []})
            for k in ("A_extraction", "B_analysis", "C_critical_review")}


def validate_stage(stage: str, pack: dict, outputs: dict, ctxd: dict) -> list[str]:
    ctxd["outputs_ref"] = outputs
    errs = _schema(stage, outputs.get(stage), ctxd)
    if errs:
        return errs
    pol = ctxd["policy"]
    if stage in ("A_extraction", "B_analysis", "C_critical_review"):
        claims, by_id, valid, check_refs = _cc(pack, _partial(outputs), errs, ctxd)
        new = outputs[stage]["claims" if stage == "A_extraction" else "additional_claims"]
        if _typed(ctxd):
            errs += typed_calc_errors(new, by_id, ctxd)
        for c in new:
            if len(c["dimensions"]) > 1 and not c["dimension_rationale"].strip():
                errs.append(f"{c['claim_id']}: more than one dimension requires dimension_rationale")
            if AUDITOR_ATTR.search(c.get("attribution", "")):
                pg = {(p["doc_id"], p["page"]): p["text"] for p in pack["pages"]}
                if not any(AUDIT_REPORT_PAGE.search(pg.get((x["doc_id"], x["page"]), "")) for x in c["citations"]):
                    errs.append(f"{c['claim_id']}: attributed to an auditor/accountant, but no cited page is part of an "
                                "auditor's or accountant's report (issuer statements are not auditor statements)")
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
    claims, by_id, valid, _ = _cc(pack, outputs, [], ctxd)
    known = set(by_id) | set(ctxd.get("calcs", {}))
    preds = pol.get("predicates") or {}
    if stage == "D_final" and _typed(ctxd):
        for f in outputs[stage]["rule_findings"]:
            pd = preds.get(f["rule_id"])
            if not pd:
                continue
            authored = {e["id"] for els in (pd.get("branches") or {"all": pd.get("elements", [])}).values() for e in els}
            got = {e["element_id"] for e in f["predicate"]["elements"]}
            if got - authored:
                errs.append(f"finding {f['rule_id']}: predicate elements {sorted(got - authored)} are not authored by {pol['version']}")
            if f["result"] == "adverse" and authored - got:
                errs.append(f"finding {f['rule_id']}: an adverse finding must assess every authored element; missing {sorted(authored - got)}")
            for e in f["predicate"]["elements"]:
                errs += [f"finding {f['rule_id']}.{e['element_id']}: unknown id {x}" for x in e["evidence_for"] + e["evidence_against"]
                         if x not in known]
                errs += korean_errors(f"finding {f['rule_id']}.{e['element_id']}.reasoning_ko", e["reasoning_ko"])
    if stage == "E_support_check" and _typed(ctxd):
        cand = {f["rule_id"] for f in outputs["D_final"]["rule_findings"] if f["result"] == "adverse" and f["rule_id"] in preds}
        got = {r["rule_id"] for r in outputs[stage]["predicate_reviews"]}
        if cand - got:
            errs.append(f"E_support_check: predicate_reviews must review every adverse candidate; missing {sorted(cand - got)}")
        for r in outputs[stage]["predicate_reviews"]:
            for o in r["objections"]:
                errs += korean_errors(f"E.review {r['rule_id']}.{o['element_id']}", o["objection_ko"])
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
        if f["result"] == "adverse":
            for e in (f.get("predicate") or {}).get("elements", []):
                adverse += [c for c in e["evidence_for"] if c in by_id]
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
                "benchmark_alternative": pol["benchmark_alternative"], "predicates": pol.get("predicates") or {}}
    base = {"task": TASK[stage], "screening_policy": pol_view}
    if stage in ("A_extraction", "B_analysis", "C_critical_review", "D_final"):
        base.update({"prior_stage_outputs": {k: outputs[k] for k in STAGE_ORDER[:STAGE_ORDER.index(stage)]},
                     "deterministic_calculations": list(ctxd.get("calcs", {}).values()), "evidence_pack": pack,
                     "thesis_questions": QUESTIONS})
    elif stage == "E_support_check":
        _, by_id, _, _ = _cc(pack, outputs, [], ctxd)
        texts = {(p["doc_id"], p["page"]): p["text"] for p in pack["pages"]}
        if _typed(ctxd):
            preds = pol.get("predicates") or {}
            base["adverse_candidates_to_review"] = [
                {"rule_id": f["rule_id"], "rule_text": pol["_rules"][f["rule_id"]]["text"],
                 "adverse_definition": pol["_rules"][f["rule_id"]].get("adverse_definition", ""),
                 "authored_predicate": preds[f["rule_id"]], "finding": f}
                for f in outputs["D_final"]["rule_findings"] if f["result"] == "adverse" and f["rule_id"] in preds]
            base["review_instructions"] = ("For every adverse candidate: assess the INFERENCE from the original cited evidence to "
                                           "each authored element. Record objections; do not resolve your own objections by narrative.")
        base.update({"claims_to_check": ctxd["claims_to_check"], "untrusted_content_notice": pack["untrusted_content_notice"],
                     "items": [{"claim": by_id[c], "cited_pages": [{"doc_id": x["doc_id"], "page": x["page"],
                                                                    "page_text": texts.get((x["doc_id"], x["page"]), "")[:12000]}
                                                                   for x in by_id[c]["citations"]]} for c in ctxd["claims_to_check"]]})
    else:
        res = ctxd["assessment"]
        _, by_id, _, _ = _cc(pack, outputs, [], ctxd)
        base.update({"computed_classification": {k: res[k] for k in ("screening", "evidence_status", "evidence_scope", "thesis_status",
                                                                     "decisive")},
                     "rule_findings": [{k: r[k] for k in ("rule_id", "final_result", "interpretation_ko", "unresolved_ko")} for r in res["findings"]],
                     "thesis": outputs["D_final"]["thesis"], "deterministic_calculations": list(ctxd.get("calcs", {}).values()),
                     "claims": [{k: c[k] for k in ("claim_id", "claim_text", "evidence_kind", "attribution", "as_of")} for c in by_id.values()],
                     "offering": pack["offering"]})
    return json.dumps(base, ensure_ascii=False)


def compute_calcs(pack: dict, outputs: dict, typed: bool = False) -> dict:
    _, by_id, valid, _ = claims_checks(pack, outputs, [], whitespace_insensitive=True, typed_calcs=typed)
    a = outputs["A_extraction"]
    ks = calc.implied_equity(a["valuation_inputs"], by_id, valid, pack["offering"].get("security_class") or "")
    rw = calc.runway(a["cash_points"], a["spending_points"], valid)
    pr = calc.investor_proceeds(pack["offering"].get("security_class") or "", {})
    for extra in (rw, pr):
        extra = {"formula": "see calc.py", "inputs": extra.get("inputs", []), "assumptions": extra.get("assumptions", []),
                 "included_instruments": [], "excluded_instruments": [], **extra}
        ks.append({**extra, "calc_id": f"K{len(ks) + 1}"})
    return {k["calc_id"]: k for k in ks}


def recalc(ctx: Ctx, analysis_id: int) -> list[dict]:
    """Recompute the deterministic calculations of a stored v3 run with the CURRENT calculator (new rows; old rows kept)."""
    a = ctx.con.execute("SELECT * FROM analysis_runs WHERE analysis_id=?", (analysis_id,)).fetchone()
    comb = json.loads((ctx.root / a["output_path"] / "combined.json").read_text())
    pack, _ = load_pack(ctx, a["pack_id"])
    ks = list(compute_calcs(pack, comb["outputs"]).values())
    for k in ks:
        ctx.con.execute("INSERT INTO calculations(analysis_id, pack_id, calc_type, formula, inputs, assumptions, included_instruments, "
                        "excluded_instruments, units, result_value, result_kind, withheld_reason, calculator_version, created_utc) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (analysis_id, a["pack_id"], f"{k['calc_id']}:{k['calc_type']}", k.get("formula", ""), json.dumps(k.get("inputs", [])),
                         json.dumps(k.get("assumptions", [])), json.dumps(k.get("included_instruments", [])),
                         json.dumps(k.get("excluded_instruments", [])), k.get("units", ""), k.get("result_value"), k["result_kind"],
                         k.get("withheld_reason", ""), k["calculator_version"], ctx.now()))
    ctx.con.commit()
    return ks


def lineage(ctx: Ctx, analysis_id: int) -> list[int]:
    """[analysis_id, parent, grandparent, ...] following notes.parent_analysis_id (or the older 'resume of analysis N')."""
    chain, cur = [], analysis_id
    while cur is not None and cur not in chain:
        chain.append(cur)
        row = ctx.con.execute("SELECT notes FROM analysis_runs WHERE analysis_id=?", (cur,)).fetchone()
        n = json.loads(row[0] or "{}") if row else {}
        par = n.get("parent_analysis_id")
        if par is None:
            m = re.search(r"resume of analysis (\d+)", n.get("note", ""))
            par = int(m.group(1)) if m else None
        cur = par
    return chain


def lineage_repairs(ctx: Ctx, analysis_id: int) -> int:
    ids = lineage(ctx, analysis_id)
    q = f"SELECT COUNT(*) FROM stage_usage WHERE attempt != 'original' AND analysis_id IN ({','.join('?' * len(ids))})"
    return ctx.con.execute(q, ids).fetchone()[0]


def migrate_cached_stage(stage: str, out: dict, calcs: dict) -> tuple[dict | None, list[dict]]:
    """Explicit v3_0 -> v3_1 migration of a cached stage output (deterministic; no model call).
    * claims without a calculation: `calculation: null` becomes `calc_request: null`;
    * a legacy calculation is accepted only if its formula, after cosmetic normalisation (display label/whitespace),
      matches a software calculation's formula, its inputs equal that calculation's inputs and its result equals the
      calculation's result. It then becomes {kind: 'ref', k_ref: Kn};
    * anything else is rejected (returns None): numbers, signs, operators and operands are never repaired.
    Returns (migrated_output or None, log)."""
    from .typed_calc import normalize_legacy_formula
    import copy
    key = "claims" if stage == "A_extraction" else "additional_claims"
    if key not in (out or {}):
        return copy.deepcopy(out), [{"stage": stage, "action": "no claims; copied unchanged"}]
    new, log = copy.deepcopy(out), []
    for c in new[key]:
        calc_ = c.pop("calculation", None)
        if calc_ is None:
            c["calc_request"] = None
            continue
        nz = normalize_legacy_formula(calc_.get("formula", ""))
        log.append({"stage": stage, "claim_id": c["claim_id"], "original": nz["original"], "normalized": nz["normalized"], "log": nz["log"]})
        if not nz["ok"]:
            log[-1]["action"] = "rejected: legacy formula does not parse"
            return None, log
        target = calcs.get(nz["label"]) if nz["label"] else None
        names = {i["name"]: i["value"] for i in calc_.get("inputs", [])}
        k_in = {i["name"]: i["value"] for i in (target or {}).get("inputs", [])}
        if not target or nz["normalized"] != target.get("formula") or names != k_in or target.get("result_value") != calc_.get("result"):
            log[-1]["action"] = "rejected: does not reproduce a software calculation exactly (no guessing)"
            return None, log
        c["calc_request"] = {"kind": "ref", "k_ref": nz["label"], "inputs": []}
        log[-1]["action"] = f"mapped to software calculation {nz['label']} (formula, inputs and result identical)"
    return new, log


def _origin_run(ctx: Ctx, analysis_id: int, stage: str) -> int:
    """The earliest run in the lineage whose directory holds a model-generated (not reused) output for `stage`."""
    origin = analysis_id
    for aid in lineage(ctx, analysis_id):
        row = ctx.con.execute("SELECT output_path FROM analysis_runs WHERE analysis_id=?", (aid,)).fetchone()
        d = ctx.root / row[0]
        if (d / f"{stage}.json").exists() or list(d.glob(f"{stage}_repair*.json")):
            origin = aid
    return origin


def plan_resume(ctx: Ctx, source_analysis_id: int, version_id: str | None = None) -> dict:
    """READ-ONLY: what a resume would reuse (after the logged migration and re-validation) and which stages would need
    model calls. Makes no model call and writes nothing. resume() uses exactly this plan."""
    a = ctx.con.execute("SELECT * FROM analysis_runs WHERE analysis_id=?", (source_analysis_id,)).fetchone()
    d = ctx.root / a["output_path"]
    target_v = version_id or a["version_id"]
    tv = ctx.con.execute("SELECT * FROM analyst_versions WHERE version_id=?", (target_v,)).fetchone()
    if tv is None:
        raise ValueError(f"target analyst version {target_v} is not registered (register before running)")
    src_schema = a["schema_version"]
    stored, migration_log = {}, []
    order = SCHEMA_MODULES[tv["schema_version"]].STAGE_ORDER
    comb = json.loads((d / "combined.json").read_text())
    calcs = comb.get("calcs") or {}
    for st in order:
        cands = sorted(x for x in d.glob(f"{st}_repair*.json") if not x.name.endswith(".meta.json"))
        reused = d / f"{st}.reused.json"
        base = d / f"{st}.json"
        f = cands[-1] if cands else (reused if reused.exists() else (base if base.exists() else None))
        if f is None:
            break
        out = json.loads(f.read_text())
        if src_schema != tv["schema_version"]:
            out, lg = migrate_cached_stage(st, out, calcs)
            migration_log += lg
            if out is None:
                break                                     # rejected: this stage is re-run by the model
        stored[st] = out
    # keep only the CONTIGUOUS prefix of stages that validate; later stages are recomputed
    pack, _ = load_pack(ctx, a["pack_id"])
    pol = policy_mod.load(tv["policy_version"] if tv["policy_version"] in policy_mod.FILES else POLICY_VERSION)
    ctxd = {"calcs": {}, "policy": pol, "S": SCHEMA_MODULES[tv["schema_version"]]}
    keep, outs = {}, {}
    for st in order:
        if st not in stored or st in ("E_support_check", "F_brief_ko"):
            break
        outs[st] = stored[st]
        if validate_stage(st, pack, outs, ctxd):
            del outs[st]
            break
        keep[st] = stored[st]
        if st == "A_extraction":
            ctxd["calcs"] = compute_calcs(pack, outs, _typed(ctxd))
    remaining = [st for st in order if st not in keep]
    return {"source": dict(a), "target_version": dict(tv), "keep": keep, "outs": outs, "ctxd": ctxd,
            "migration_log": migration_log, "src_schema": src_schema, "remaining_stages": remaining,
            "stored_candidates": {st: True for st in stored}}


def resume(ctx: Ctx, source_analysis_id: int, adapter, note: str = "", version_id: str | None = None,
           extra_repairs_authorized: int = 0, authorization_note: str = "") -> dict:
    """Continue the SAME workflow as a NEW child run. Reuses the source's final stored stage outputs (migrated
    explicitly to the target schema when it differs) and calls the model only for stages that never validated.
    Repairs: every repair in the lineage stays counted. A new run may make at most `extra_repairs_authorized`
    repairs, which is 0 unless the user explicitly authorized a bounded continuation. A new run id cannot reset the
    counter. The source run is never modified."""
    plan = plan_resume(ctx, source_analysis_id, version_id)
    a, tv, keep, migration_log, src_schema = plan["source"], plan["target_version"], plan["keep"], plan["migration_log"], plan["src_schema"]
    target_v = tv["version_id"]
    used = lineage_repairs(ctx, source_analysis_id)
    return run_v3(ctx, a["offering_id"], a["pack_id"], adapter, target_v, stored_outputs=keep,
                  repair_allowance=extra_repairs_authorized,
                  lineage_info={"parent_analysis_id": source_analysis_id, "lineage": lineage(ctx, source_analysis_id),
                                "lineage_repairs_before": used, "extra_repairs_authorized": extra_repairs_authorized,
                                "authorization_note": authorization_note, "reused_stages": list(keep),
                                "reused_stage_provenance": {st: {"generated_in_analysis": _origin_run(ctx, source_analysis_id, st),
                                                                 "original_prompt_version": a["prompt_version"],
                                                                 "original_schema_version": src_schema,
                                                                 "original_model": a["model_reported"],
                                                                 "note": "generated by the original version; conclusions in "
                                                                         "this stage are NOT new-model outputs"} for st in keep},
                                "schema_migration": {"from": src_schema, "to": tv["schema_version"], "log": migration_log}},
                  note=f"resume of analysis {source_analysis_id} ({len(keep)} validated stage(s) reused, {used} lineage repair(s)); {note}")


def register_v3(ctx: Ctx, version_id: str, description: str, development_offering_ids: list[str], repair_rounds: int = 1,
                model_requested: str | None = None, max_total_repairs: int | None = None, prompt_version: str = PROMPT_VERSION,
                schema_version: str = SCHEMA_VERSION, policy_version: str = POLICY_VERSION) -> None:
    if schema_version not in SCHEMA_MODULES or policy_version not in policy_mod.FILES or not (PROMPTS / f"{prompt_version}.md").exists():
        raise ValueError("unknown prompt, schema or policy version")
    ctx.con.execute("INSERT OR IGNORE INTO analyst_versions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (version_id, "challenger", prompt_version, schema_version, policy_version, model_requested,
                     json.dumps({"tools": "disabled", "max_budget_usd_per_stage": 5.0, "repair_rounds": repair_rounds,
                                 "max_total_repairs": max_total_repairs, "pipeline": "analysis_v3", "classifier": assess_v3.CLASSIFIER_VERSION,
                                 "calculator": calc.CALCULATOR_VERSION}),
                     description, ctx.now(), json.dumps(development_offering_ids)))
    ctx.con.commit()


def run_v3(ctx: Ctx, offering_id: str, pack_id: str, adapter, version_id: str, note: str = "",
           repair_override: int | None = None, policy_override: dict | None = None, stored_outputs: dict | None = None,
           repairs_already_used: int = 0, repair_allowance: int | None = None, lineage_info: dict | None = None) -> dict:
    v = ctx.con.execute("SELECT * FROM analyst_versions WHERE version_id=?", (version_id,)).fetchone()
    if v is None:
        raise ValueError(f"analyst version {version_id} is not registered")
    settings = json.loads(v["settings"] or "{}")
    cap = int(settings.get("repair_rounds", 0)) if repair_override is None else repair_override
    total_cap = settings.get("max_total_repairs")          # whole-run limit, e.g. 1 for a bounded live rerun
    used = repairs_already_used
    if repair_allowance is not None:                        # child of a lineage: only the explicitly authorized repairs
        total_cap, used = repair_allowance, 0
    WS_MATCHES.clear()
    pack, pack_sha = load_pack(ctx, pack_id)
    if pack["offering"]["offering_id"] != offering_id:
        raise ValueError("pack belongs to another offering")
    pv = v["policy_version"] if v["policy_version"] in policy_mod.FILES else POLICY_VERSION
    pol = policy_override or policy_mod.load(pv)
    pstate = "proposed" if policy_override else policy_mod.state(ctx, pv)
    S = SCHEMA_MODULES[v["schema_version"]]
    system_prompt = (PROMPTS / f"{v['prompt_version']}.md").read_text()
    started = ctx.now()
    out_dir = ctx.root / ctx.cfg.raw["paths"].get("analyses_dir", "data/analyses") / f"{offering_id}_{started.replace(':', '')}_v3"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs, usage, errors, presentation = {}, [], [], []
    ctxd = {"calcs": {}, "policy": pol, "policy_state": pstate, "S": S}
    o = dict(ctx.con.execute("SELECT * FROM offerings WHERE offering_id=?", (offering_id,)).fetchone())

    def attempt(stage, label, payload):
        out, meta = adapter.run(stage, system_prompt, payload, S.STAGES[stage])
        (out_dir / f"{stage}{label}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        (out_dir / f"{stage}{label}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        return out, meta or {}

    res = None
    for stage in S.STAGE_ORDER:
        if stage == "E_support_check":
            _, by_id, _, _ = _cc(pack, outputs, [], ctxd)
            ctxd["claims_to_check"] = _claims_to_check(outputs, by_id, pol)
        if stage == "F_brief_ko":
            res = _assess(ctx, [], outputs, pack, pol, pstate, ctxd, o)
            ctxd["assessment"] = res
        payload = _payload(stage, pack, outputs, ctxd)
        if stored_outputs and stage in stored_outputs:            # resumed: reuse the stored output, no model call
            out, meta = stored_outputs[stage], {"model_reported": "(stored output reused)", "cost_usd": 0.0, "seconds": 0}
            (out_dir / f"{stage}.reused.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        else:
            out, meta = attempt(stage, "", payload)
        outputs[stage] = out
        errs = validate_stage(stage, pack, outputs, ctxd)
        usage.append(_usage_row(stage, "original", meta, errs))
        rnd = 0
        while errs and rnd < cap and (total_cap is None or used < total_cap):
            rnd += 1
            used += 1
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
            ctxd["calcs"] = compute_calcs(pack, outputs, _typed(ctxd))
    if errors:
        res = _assess(ctx, errors, outputs, pack, pol, pstate, ctxd, o)
    ctxd["lineage_info"] = lineage_info or {}
    return _store(ctx, offering_id, pack_id, pack, pack_sha, v, adapter, started, ctx.now(), outputs, usage, ctxd, errors,
                  presentation, res, out_dir, note, pol, pstate)


def _assess(ctx, errors, outputs, pack, pol, pstate, ctxd, o):
    by_id, valid = {}, set()
    if not errors:
        _, by_id, valid, _ = _cc(pack, outputs, [], ctxd)
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
        (offering_id, pack_id, pack_sha, v["version_id"], v["prompt_version"], v["schema_version"], pol["version"], adapter.name,
         ";".join(models) or None, None, v["settings"], started, finished, status, "development" if offering_id in dev else "evaluation",
         str(out_dir.relative_to(ctx.root)), hashlib.sha256(combined.encode()).hexdigest(), json.dumps(errors), cost,
         json.dumps({"pipeline": "analysis_v3", "pipeline_version": PIPELINE_VERSION, "policy_sha256": pol["_sha256"],
                     "policy_state": pstate, "status_column_note": "placeholder; v3 results live in assessments_v3 and never feed approvals",
                     "presentation_errors": presentation, "note": note, "cost_label": COST_LABEL,
                     "citation_rule": CITATION_RULE, **(ctxd.get("lineage_info") or {}), "whitespace_insensitive_matches": sorted(set(WS_MATCHES))},
                    ensure_ascii=False)))
    aid = cur.lastrowid
    now = ctx.now()
    if not errors:
        claims, _, _, _ = _cc(pack, outputs, [], ctxd)
        for c in claims:
            ctx.con.execute("""INSERT INTO analysis_claims(analysis_id, claim_id, stage, claim_text, claim_type, evidence_status, citations,
                observed_cutoff_utc, financial_period, calculation_inputs, contradictions, missing) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (aid, c["claim_id"], {"A": "A_extraction", "B": "B_analysis", "C": "C_critical_review"}[c["claim_id"][0]],
                             c["claim_text"], c["claim_type"], c["evidence_status"], json.dumps(c["citations"], ensure_ascii=False),
                             pack["cutoff_utc"], c["financial_period"],
                             json.dumps({"evidence_kind": c["evidence_kind"], "dimensions": c["dimensions"], "attribution": c["attribution"],
                                         "as_of": c["as_of"], "calculation": c.get("calculation"), "calc_request": c.get("calc_request"),
                                         "typed_result": (ctxd.get("typed") or {}).get(c["claim_id"])}, ensure_ascii=False, default=str),
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
