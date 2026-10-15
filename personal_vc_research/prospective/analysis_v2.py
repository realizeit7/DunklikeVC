"""Analyst v2 pipeline (v2.1): stage-by-stage validation with targeted, capped repair; deterministic calculations;
per-criterion results; a structured support check; a computed four-dimension assessment; and a Korean summary written
after the assessment.

Never-weaken rules
* Each stage is validated as soon as it returns. A failing stage gets at most `repair_rounds` repair requests. Each
  request carries only the explicit validation errors and the previous output. Original and repaired outputs are both
  saved. Validation is identical for original and repaired outputs.
* If a stage still fails after the cap, the run stops and is recorded as `analysis_failed`. Nothing is regenerated in
  the hope of a different conclusion.
* Usage is recorded per stage and attempt: tokens, seconds and the CLI cost estimate. The CLI figure is labelled an
  estimated list-price equivalent, not a billed amount.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import jsonschema

from . import assess, calc, journal
from .analysis import POLICY_VERSION, _norm, budget_gate, claims_checks, derive_status
from .core import Ctx, parse_utc
from .llm.schemas_v1 import CRITICAL_ITEMS
from .llm.schemas_v2 import CRITERIA, SCHEMA_VERSION, STAGE_ORDER, STAGES
from .packs import load_pack

PROMPT_VERSION = "analyst_prompt_v2"
PROMPTS = Path(__file__).parent / "llm" / "prompts"
NON_BLOCKING_CRITICAL = {"closing_or_availability_evidence"}
MAX_SUPPORT_CHECKS = 24
COST_LABEL = "cli_estimated_list_price_equivalent_not_billed"

STAGE_TASK = {
    "A_extraction": "Stage A: evidence extraction. Claims A1..; critical_items; missing_information; valuation_inputs; "
                    "financial_statements.",
    "B_analysis": "Stage B: business and investment analysis (new claim ids B1..). Cite K ids for valuation arithmetic.",
    "C_critical_review": "Stage C: critical review of A and B (new claim ids C1..). Same model: critical review, not "
                         "independent verification. Look especially for overstatement (see precision rules).",
    "D_final": "Stage D: respond to every C issue; give the eight criterion results; 0-3 forecasts (FORECAST_V2 rules).",
    "E_support_check": "Stage E: structured support check of each claim in claims_to_check, using the cited page texts "
                       "provided. This is a model judgment, not verification.",
    "F_brief_ko": "Stage F: write the Korean summary fields. The assessment is computed and fixed; do not change it.",
}


# ---- stage-level validation ----------------------------------------------------------------------------------
def _schema_errors(stage: str, out) -> list[str]:
    if out is None:
        return [f"{stage}: missing output"]
    return [f"{stage}: schema: {e.message[:160]} at {'/'.join(map(str, e.absolute_path))}"
            for e in jsonschema.Draft202012Validator(STAGES[stage]).iter_errors(out)]


THRESHOLD_OR = re.compile(r"\b(at or above|at or below|or more|or greater|or less|or fewer|on or before|on or after|or higher|or lower)\b", re.I)
ENGLISH_RUN = re.compile(r"(?:\b[A-Za-z][A-Za-z'’-]+\b[\s,;:]+){8,}")


VALIDATOR_VERSION = "v2_validator_0_2"
# 0_2 (2026-10-15, after analysis 10): English terms inside parentheses, which the prompt explicitly allows (e.g.
# "희석방지권(anti-dilution rights)"), no longer count toward the Latin-character ratio. 0_1 counted them and forced
# a needless repair round on a short Korean note in analysis 10, stage E. The English-passage rule is unchanged.


def korean_errors(where: str, txt: str, min_words: int | None = None, max_words: int | None = None) -> list[str]:
    errs = []
    bare = re.sub(r"\([^)]*\)", " ", txt)
    hangul = len(re.findall(r"[가-힣]", txt))
    latin = len(re.findall(r"[A-Za-z]", bare))
    if txt.strip() and hangul == 0:
        errs.append(f"{where}: must be written in Korean")
    elif latin > 0.35 * (hangul + latin):
        errs.append(f"{where}: too much English text ({latin} Latin vs {hangul} Hangul characters); write in Korean")
    m = ENGLISH_RUN.search(bare)
    if m:
        errs.append(f"{where}: contains an English passage outside parentheses: {m.group(0)[:60]!r}")
    n = len(txt.split())
    if min_words and n < min_words:
        errs.append(f"{where}: {n} words; at least {min_words} required")
    if max_words and n > max_words:
        errs.append(f"{where}: {n} words; at most {max_words} allowed")
    return errs


def validate_stage(stage: str, pack: dict, outputs: dict, ctxd: dict) -> list[str]:
    """Errors for `stage` given earlier (already valid) stages. ctxd carries calcs and claims_to_check."""
    errs = _schema_errors(stage, outputs.get(stage))
    if errs:
        return errs
    if stage in ("A_extraction", "B_analysis", "C_critical_review"):
        partial = {k: outputs.get(k) or ({"claims": []} if k == "A_extraction" else {"additional_claims": [], "issues": []})
                   for k in ("A_extraction", "B_analysis", "C_critical_review")}
        claims, by_id, valid, check_refs = claims_checks(pack, partial, errs)
        known = set(by_id) | set(ctxd.get("calcs", {}))
        if stage == "A_extraction":
            a = outputs[stage]
            for ci in a["critical_items"]:
                check_refs(f"critical_item {ci['item']}", ci["claim_ids"])
            vi = a["valuation_inputs"]
            refs = [vi["price_claim_id"]] if vi["price_per_share_usd"] is not None else []
            refs += [c["claim_id"] for c in vi["share_counts"]]
            for cv in vi["convertible_instruments"]:
                refs += cv["claim_ids"]
            check_refs("valuation_inputs", refs)
            check_refs("financial_statements", a["financial_statements"]["claim_ids"])
            items = [ci["item"] for ci in a["critical_items"]]
            if sorted(set(items)) != sorted(CRITICAL_ITEMS) or len(items) != len(CRITICAL_ITEMS):
                errs.append(f"A_extraction: critical_items must list each of the 7 items once, got {items}")
        if stage == "B_analysis":
            for k, sec in outputs[stage].items():
                if isinstance(sec, dict) and "claim_ids" in sec:
                    errs += [f"B.{k}: unknown id {r}" for r in sec["claim_ids"] if r not in known]
        if stage == "C_critical_review":
            for i, iss in enumerate(outputs[stage]["issues"]):
                errs += [f"C.issue[{i}]: unknown id {r}" for r in iss["claim_ids"] if r not in known]
        return errs
    claims, by_id, valid, _ = claims_checks(pack, outputs, [])
    known = set(by_id) | set(ctxd.get("calcs", {}))
    if stage == "D_final":
        d = outputs[stage]
        n_issues = len(outputs["C_critical_review"]["issues"])
        missing = set(range(n_issues)) - {r["issue_index"] for r in d["critique_responses"]}
        if missing:
            errs.append(f"D_final: critique issues without a response: {sorted(missing)}")
        ids = [c["criterion_id"] for c in d["criteria"]]
        if sorted(ids) != sorted(CRITERIA):
            errs.append(f"D_final: criteria must contain each of the 8 criteria exactly once, got {ids}")
        for c in d["criteria"]:
            w = f"criterion {c['criterion_id']}"
            errs += [f"{w}: unknown id {r}" for r in c["claim_ids"] + c["counter_claim_ids"] if r not in known]
            errs += [f"{w}: unverified assertion {r} used as support" for r in c["claim_ids"]
                     if r in by_id and by_id[r]["evidence_status"] == "unverified_assertion"]
            if c["result"] == "fail" and not c["failure_grounds"]:
                errs.append(f"{w}: a fail must list failure_grounds")
            if c["result"] != "fail" and c["failure_grounds"]:
                errs.append(f"{w}: failure_grounds given for a non-fail result")
            if c["result"] == "fail" and not c["claim_ids"]:
                errs.append(f"{w}: a fail must cite claim or K ids")
            errs += korean_errors(f"{w}.reason_ko", c["reason_ko"]) + korean_errors(f"{w}.what_would_change_ko", c["what_would_change_ko"])
        cutoff = parse_utc(pack["cutoff_utc"])
        for j, f in enumerate(d["forecasts"]):
            w = f"forecast[{j}]"
            if re.search(r"\bor\b|또는|혹은", THRESHOLD_OR.sub(" ", f["event"]), re.I):
                errs.append(f"{w}: event joins alternatives with 'or'; split distinct events into separate forecasts")
            dl = parse_utc(f["deadline_date"])
            if dl <= cutoff or (dl - cutoff).days > 25 * 30.4375:
                errs.append(f"{w}: deadline {f['deadline_date']} must be after the cutoff and within 25 months")
            errs += [f"{w}: unknown basis id {r}" for r in f["basis_claim_ids"] if r not in known]
            cited = " ".join(_norm(by_id[r]["claim_text"]) + " " + " ".join(_norm(x["quote"]) for x in by_id[r]["citations"])
                             for r in f["basis_claim_ids"] if r in by_id)
            nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", cited)]
            nums += [100 * float((by_id[r].get("calculation") or {}).get("result", 0)) for r in f["basis_claim_ids"] if r in by_id]
            for pct in re.findall(r"(\d+(?:\.\d+)?)\s?%", f["rationale"]):
                if not any(abs(float(pct) - n) <= 0.5 for n in nums):
                    errs.append(f"{w}: statistic {pct}% in rationale is not supported by any cited basis claim")
    if stage == "E_support_check":
        got = [c["claim_id"] for c in outputs[stage]["checks"]]
        want = ctxd.get("claims_to_check", [])
        if sorted(got) != sorted(want):
            errs.append(f"E_support_check: must check exactly {want}; got {got}")
        for ch in outputs[stage]["checks"]:
            errs += korean_errors(f"E.{ch['claim_id']}.note_ko", ch["note_ko"])
    if stage == "F_brief_ko":
        f = outputs[stage]
        errs += korean_errors("F.summary_ko", f["summary_ko"], 250, 600)
        errs += korean_errors("F.business_one_liner_ko", f["business_one_liner_ko"])
        for k in ("decisive_reasons_ko", "material_missing_ko", "what_would_change_ko"):
            for i, t in enumerate(f[k]):
                errs += korean_errors(f"F.{k}[{i}]", t)
        for t in f["terms_explained_ko"]:
            errs += korean_errors(f"F.terms[{t['term']}]", t["explanation_ko"])
        alltxt = json.dumps(f, ensure_ascii=False)
        errs += [f"F: reference [{r}] to unknown id" for r in re.findall(r"\[([ABCK]\d{1,3})\]", alltxt) if r not in known]
    return errs


# ---- payloads -----------------------------------------------------------------------------------------------------
def _payload(stage: str, pack: dict, outputs: dict, ctxd: dict) -> str:
    base = {"task": STAGE_TASK[stage], "screening_policy_version": POLICY_VERSION}
    if stage in ("A_extraction", "B_analysis", "C_critical_review", "D_final"):
        base.update({"prior_stage_outputs": {k: outputs[k] for k in STAGE_ORDER[:STAGE_ORDER.index(stage)]},
                     "deterministic_calculations": list(ctxd.get("calcs", {}).values()), "evidence_pack": pack})
    elif stage == "E_support_check":
        claims, by_id, _, _ = claims_checks(pack, outputs, [])
        texts = {(p["doc_id"], p["page"]): p["text"] for p in pack["pages"]}
        items = []
        for cid in ctxd["claims_to_check"]:
            c = by_id[cid]
            items.append({"claim": c, "cited_pages": [{"doc_id": x["doc_id"], "page": x["page"],
                                                       "page_text": texts.get((x["doc_id"], x["page"]), "")[:12000]}
                                                      for x in c["citations"]],
                          "basis_claims": [by_id[b] for b in c["basis_claim_ids"] if b in by_id]})
        base.update({"claims_to_check": ctxd["claims_to_check"], "items": items,
                     "untrusted_content_notice": pack["untrusted_content_notice"]})
    elif stage == "F_brief_ko":
        claims, by_id, _, _ = claims_checks(pack, outputs, [])
        res = ctxd["assessment"]
        used = sorted({i for r in res["criteria"] for i in r["claim_ids"] if i in by_id})
        base.update({"computed_assessment": {k: res[k] for k in ("assessment", "evidence_completeness",
                                                                 "operational_readiness", "budget_status", "decisive",
                                                                 "unresolved")},
                     "criteria": res["criteria"], "support_checks": outputs["E_support_check"]["checks"],
                     "deterministic_calculations": list(ctxd.get("calcs", {}).values()),
                     "claims": [{k: by_id[i][k] for k in ("claim_id", "claim_text", "evidence_status", "financial_period")} for i in used],
                     "missing_information": outputs["A_extraction"]["missing_information"],
                     "business_sections": {k: v["assessment"] for k, v in outputs["B_analysis"].items() if isinstance(v, dict) and "assessment" in v},
                     "offering": pack["offering"]})
    return json.dumps(base, ensure_ascii=False)


def _claims_to_check(outputs: dict, by_id: dict) -> list[str]:
    fail_ids, pass_ids = [], []
    for c in outputs["D_final"]["criteria"]:
        tgt = fail_ids if c["result"] == "fail" else pass_ids if c["result"] == "pass" else None
        if tgt is not None:
            tgt += [i for i in c["claim_ids"] if i in by_id and i not in tgt]
    out = list(dict.fromkeys(fail_ids))
    for i in pass_ids:
        if len(out) >= MAX_SUPPORT_CHECKS:
            break
        if i not in out:
            out.append(i)
    return out[:max(MAX_SUPPORT_CHECKS, len(fail_ids))]


# ---- orchestration ------------------------------------------------------------------------------------------------
def register_v2(ctx: Ctx, version_id: str, description: str, development_offering_ids: list[str], repair_rounds: int = 2,
                model_requested: str | None = None) -> None:
    ctx.con.execute("INSERT OR IGNORE INTO analyst_versions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (version_id, "challenger", PROMPT_VERSION, SCHEMA_VERSION, POLICY_VERSION, model_requested,
                     json.dumps({"tools": "disabled", "max_budget_usd_per_stage": 5.0, "repair_rounds": repair_rounds,
                                 "pipeline": "analysis_v2", "classifier": assess.CLASSIFIER_VERSION,
                                 "calculator": calc.CALCULATOR_VERSION}),
                     description, ctx.now(), json.dumps(development_offering_ids)))
    ctx.con.commit()


def run_v2(ctx: Ctx, offering_id: str, pack_id: str, adapter, version_id: str, note: str = "") -> dict:
    v = ctx.con.execute("SELECT * FROM analyst_versions WHERE version_id=?", (version_id,)).fetchone()
    if v is None:
        raise ValueError(f"analyst version {version_id} is not registered")
    settings = json.loads(v["settings"] or "{}")
    cap = int(settings.get("repair_rounds", 0))
    pack, pack_sha = load_pack(ctx, pack_id)
    if pack["offering"]["offering_id"] != offering_id:
        raise ValueError("pack belongs to another offering")
    system_prompt = (PROMPTS / f"{v['prompt_version']}.md").read_text()
    started = ctx.now()
    out_dir = ctx.root / ctx.cfg.raw["paths"].get("analyses_dir", "data/analyses") / f"{offering_id}_{started.replace(':', '')}_v2"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict = {}
    usage: list[dict] = []
    ctxd: dict = {"calcs": {}}
    errors: list[str] = []
    res = None

    def attempt(stage: str, label: str, payload: str):
        out, meta = adapter.run(stage, system_prompt, payload, STAGES[stage])
        (out_dir / f"{stage}{label}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        (out_dir / f"{stage}{label}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        return out, meta or {}

    for stage in STAGE_ORDER:
        if stage == "E_support_check":
            _, by_id, _, _ = claims_checks(pack, outputs, [])
            ctxd["claims_to_check"] = _claims_to_check(outputs, by_id)
        if stage == "F_brief_ko":
            res = _assess(ctx, offering_id, pack, outputs, ctxd, [])
            ctxd["assessment"] = res
        payload = _payload(stage, pack, outputs, ctxd)
        out, meta = attempt(stage, "", payload)
        outputs[stage] = out
        errs = validate_stage(stage, pack, outputs, ctxd)
        usage.append(_usage_row(stage, "original", meta, errs))
        rnd = 0
        while errs and rnd < cap:
            rnd += 1
            rp = json.dumps({"task": "REPAIR: your previous output for this stage failed mechanical validation. Return the "
                                     "complete corrected output for this stage. Fix exactly the listed errors; keep claim ids "
                                     "unchanged unless an error requires removing a claim; do not add unsupported content and "
                                     "do not change conclusions that the errors do not concern.",
                             "validation_errors": errs[:40], "previous_output": outputs[stage],
                             "original_request": json.loads(payload)}, ensure_ascii=False)
            out2, meta2 = attempt(stage, f"_repair{rnd}", rp)
            if out2 is not None:
                outputs[stage] = out2
            errs = validate_stage(stage, pack, outputs, ctxd)
            usage.append(_usage_row(stage, f"repair{rnd}", meta2, errs))
        if errs:
            errors = errs
            break
        if stage == "A_extraction":
            claims, by_id, valid, _ = claims_checks(pack, outputs, [])
            for k in calc.implied_equity(outputs["A_extraction"]["valuation_inputs"], by_id, valid):
                ctxd["calcs"][k["calc_id"]] = k
    finished = ctx.now()
    if errors:
        res = _assess(ctx, offering_id, pack, outputs, ctxd, errors)
    return _store(ctx, offering_id, pack_id, pack, pack_sha, v, adapter, started, finished, outputs, usage, ctxd, errors,
                  res, out_dir, note)


def _usage_row(stage: str, attempt_label: str, meta: dict, errs: list[str]) -> dict:
    u = meta.get("usage") or {}
    return {"stage": stage, "attempt": attempt_label, "seconds": meta.get("seconds"), "input_tokens": u.get("input_tokens"),
            "output_tokens": u.get("output_tokens"), "cache_read_tokens": u.get("cache_read_tokens"),
            "cache_creation_tokens": u.get("cache_creation_tokens"), "cost_estimate_usd": meta.get("cost_usd"),
            "outcome": "valid" if not errs else "invalid", "n_errors": len(errs), "model": meta.get("model_reported"),
            "errors_sample": errs[:5]}


def _assess(ctx: Ctx, offering_id: str, pack: dict, outputs: dict, ctxd: dict, errors: list[str]) -> dict:
    o = dict(ctx.con.execute("SELECT * FROM offerings WHERE offering_id=?", (offering_id,)).fetchone())
    critical = {}
    by_id, valid = {}, set()
    if outputs.get("A_extraction") and not (errors and any(e.startswith("A_extraction") or re.match(r"^A\d", e) for e in errors)):
        _, by_id, valid, _ = claims_checks(pack, outputs, [])
        crit = {ci["item"]: ci for ci in outputs["A_extraction"]["critical_items"]}
        for item in CRITICAL_ITEMS:
            ci = crit.get(item)
            ok = bool(ci and ci["status"] == "confirmed_with_citation" and ci["claim_ids"] and all(r in valid for r in ci["claim_ids"]))
            critical[item] = "confirmed" if ok else ("non_blocking_unknown" if item in NON_BLOCKING_CRITICAL else "not_confirmed")
    av = assess.availability_observations(ctx, offering_id)
    bg = budget_gate(ctx, offering_id)
    res = assess.evaluate(errors, outputs, critical, by_id, valid, ctxd.get("calcs", {}), pack, o, av, bg)
    res["critical"] = critical
    res["budget_gate"] = bg
    return res


def _derived_gates(res: dict, critical: dict) -> list[dict]:
    gates = []
    ev = "pass" if critical and all(v != "not_confirmed" for v in critical.values()) else "unknown"
    gates.append({"gate": "evidence_sufficiency", "result": ev})
    for g in ("business_thesis", "price_and_contract"):
        rows = [r for r in res["criteria"] if r["gate"] == g]
        r = "fail" if any(x["final_result"] == "fail" for x in rows) else (
            "pass" if rows and all(x["final_result"] == "pass" for x in rows) else "unknown")
        gates.append({"gate": g, "result": r})
    return gates


def _store(ctx, offering_id, pack_id, pack, pack_sha, v, adapter, started, finished, outputs, usage, ctxd, errors, res,
           out_dir, note) -> dict:
    critical = res.get("critical", {})
    gates = _derived_gates(res, critical) if not errors else []
    legacy = derive_status(errors, critical, gates)
    combined = json.dumps({"outputs": outputs, "usage": usage, "calcs": ctxd.get("calcs"),
                           "claims_to_check": ctxd.get("claims_to_check")}, sort_keys=True, ensure_ascii=False)
    (out_dir / "combined.json").write_text(combined)
    models = sorted({u["model"] for u in usage if u.get("model")})
    cost = sum(u["cost_estimate_usd"] or 0 for u in usage)
    dev = json.loads(v["development_offering_ids"])
    cur = ctx.con.execute(
        """INSERT INTO analysis_runs(offering_id, pack_id, pack_sha256, version_id, prompt_version, schema_version, policy_version,
           adapter, model_reported, provider_reported, settings, started_utc, finished_utc, status, split, output_path,
           output_sha256, validation_errors, cost_usd, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (offering_id, pack_id, pack_sha, v["version_id"], v["prompt_version"], SCHEMA_VERSION, POLICY_VERSION, adapter.name,
         ";".join(models) or None, None, v["settings"], started, finished, legacy,
         "development" if offering_id in dev else "evaluation", str(out_dir.relative_to(ctx.root)),
         hashlib.sha256(combined.encode()).hexdigest(), json.dumps(errors), cost,
         json.dumps({"pipeline": "analysis_v2", "validator": VALIDATOR_VERSION, "legacy_status_note": "status column = screening_policy_v1 mapping; "
                     "v2.1 dimensions in table assessments", "critical": critical, "note": note,
                     "cost_label": COST_LABEL}, ensure_ascii=False)))
    aid = cur.lastrowid
    now = ctx.now()
    if not errors or outputs.get("A_extraction"):
        try:
            claims, by_id, _, _ = claims_checks(pack, {k: outputs.get(k) or {"claims": [], "additional_claims": [], "issues": []}
                                                       for k in ("A_extraction", "B_analysis", "C_critical_review")}, [])
        except (KeyError, TypeError):
            claims = []
        if not errors:
            for c in claims:
                ctx.con.execute("""INSERT INTO analysis_claims(analysis_id, claim_id, stage, claim_text, claim_type, evidence_status,
                    citations, observed_cutoff_utc, financial_period, calculation_inputs, contradictions, missing) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (aid, c["claim_id"], {"A": "A_extraction", "B": "B_analysis", "C": "C_critical_review"}[c["claim_id"][0]],
                                 c["claim_text"], c["claim_type"], c["evidence_status"], json.dumps(c["citations"], ensure_ascii=False),
                                 pack["cutoff_utc"], c["financial_period"], json.dumps(c.get("calculation")), c["contradictions"], ""))
    for g in gates:
        ctx.con.execute("INSERT INTO analysis_gates(analysis_id, gate, result, source, criteria) VALUES (?,?,?,?,?)",
                        (aid, g["gate"], g["result"], "derived_from_criteria_v2", "see criterion_results"))
    bg = res["budget_gate"]
    ctx.con.execute("INSERT INTO analysis_gates(analysis_id, gate, result, source, criteria, uncertainty) VALUES (?,?,?,?,?,?)",
                    (aid, bg["gate"], bg["result"], bg["source"], bg["criteria"], bg["uncertainty"]))
    for r in res["criteria"]:
        ctx.con.execute("INSERT INTO criterion_results(analysis_id, criterion_id, gate, required, model_result, final_result, support, "
                        "claim_ids, reason_ko, validator_notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (aid, r["criterion_id"], r["gate"], 1, r["model_result"], r["final_result"], r["support"],
                         json.dumps(r["claim_ids"]), r["reason_ko"], json.dumps(r["validator_notes"] + [f"grounds={r['failure_grounds']}"],
                                                                                ensure_ascii=False)))
    for k in ctxd.get("calcs", {}).values():
        ctx.con.execute("INSERT INTO calculations(analysis_id, pack_id, calc_type, formula, inputs, assumptions, included_instruments, "
                        "excluded_instruments, units, result_value, result_kind, withheld_reason, calculator_version, created_utc) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, pack_id, f"{k['calc_id']}:{k['calc_type']}", k["formula"], json.dumps(k["inputs"]),
                         json.dumps(k["assumptions"]), json.dumps(k["included_instruments"]), json.dumps(k["excluded_instruments"]),
                         k["units"], k["result_value"], k["result_kind"], k["withheld_reason"], k["calculator_version"], now))
    for ch in (outputs.get("E_support_check") or {}).get("checks", []) if not errors or outputs.get("F_brief_ko") else []:
        ctx.con.execute("INSERT INTO support_checks(analysis_id, claim_id, checker, judgment_label, citation_exists, passage_supports, "
                        "omitted_qualifications, evidence_type, conflicts, overstatement, verdict, note, checked_utc) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, ch["claim_id"], f"model:{';'.join(models)}", "model_judgment_not_verification", 1,
                         ch["passage_supports"], ch["omitted_qualifications"], ch["evidence_type"], ch["conflicts"],
                         ch["overstatement"], ch["verdict"], ch["note_ko"], now))
    fresh = assess.freshness(ctx, offering_id, finished, pack, outputs if not errors else None)
    ctx.con.execute("INSERT INTO assessments(analysis_id, classifier_version, policy_version, created_utc, assessment, "
                    "evidence_completeness, operational_readiness, budget_status, decisive_criteria, reasons, unresolved_criteria, "
                    "freshness, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (aid, assess.CLASSIFIER_VERSION, assess.PROPOSED_POLICY, now, res["assessment"], res["evidence_completeness"],
                     res["operational_readiness"], res["budget_status"], json.dumps(res["decisive"]),
                     json.dumps(res["reasons"], ensure_ascii=False), json.dumps(res["unresolved"]),
                     json.dumps(fresh, ensure_ascii=False), f"legacy policy-v1 status: {legacy}"))
    for u in usage:
        ctx.con.execute("INSERT INTO stage_usage(analysis_id, run_dir, stage, attempt, seconds, input_tokens, output_tokens, "
                        "cache_read_tokens, cache_creation_tokens, cost_estimate_usd, cost_label, outcome, n_errors) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, str(out_dir.relative_to(ctx.root)), u["stage"], u["attempt"], u["seconds"], u["input_tokens"],
                         u["output_tokens"], u["cache_read_tokens"], u["cache_creation_tokens"], u["cost_estimate_usd"],
                         COST_LABEL, u["outcome"], u["n_errors"]))
    n_fc = 0
    if not errors:
        for f in outputs["D_final"]["forecasts"]:
            months = max(1, round((parse_utc(f["deadline_date"]) - parse_utc(pack["cutoff_utc"])).days / 30.4375))
            pid = journal.add_forecast(ctx, offering_id, f["event"], f["event_kind"], months, f["probability"],
                                       f"{f['target_type']}: {f['event']} | scope: {f['target_scope']}", f["reporting_lag_days"],
                                       f["unknown_treatment"], forecaster=f"{v['version_id']} ({';'.join(models)})",
                                       permitted_evidence="; ".join(f["allowed_evidence"]),
                                       deadline_override=f["deadline_date"] + "T23:59:59+00:00")
            ctx.con.execute("INSERT INTO prediction_meta VALUES (?,?,?,?,?,?)",
                            (pid, aid, pack_sha, v["version_id"], ";".join(models), f["probability_label"]))
            ctx.con.execute("INSERT INTO forecast_definitions(prediction_id, analysis_id, schema_version, target_type, target_scope, "
                            "deadline_utc, reporting_lag_days, allowed_evidence, rationale, assumptions, unknown_treatment, "
                            "cancellation_treatment, early_true_allowed, silence_is_false) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,0)",
                            (pid, aid, SCHEMA_VERSION, f["target_type"], f["target_scope"], f["deadline_date"] + "T23:59:59+00:00",
                             f["reporting_lag_days"], json.dumps(f["allowed_evidence"], ensure_ascii=False), f["rationale"],
                             json.dumps(f["assumptions"], ensure_ascii=False), f["unknown_treatment"], f["cancellation_treatment"]))
            n_fc += 1
    ctx.con.commit()
    return {"analysis_id": aid, "legacy_status": legacy, "assessment": res["assessment"],
            "evidence_completeness": res["evidence_completeness"], "operational_readiness": res["operational_readiness"],
            "budget_status": res["budget_status"], "decisive": res["decisive"], "unresolved": res["unresolved"],
            "n_errors": len(errors), "errors": errors[:15], "forecasts": n_fc, "models": models, "cost_estimate_usd": round(cost, 4),
            "usage": usage, "output_dir": str(out_dir)}


def reassess(ctx: Ctx, analysis_id: int, note: str = "") -> dict:
    """Re-run the CURRENT classifier on a stored v2 run's outputs (no LLM call). Inserts a new assessments row; the
    earlier row, criterion results and forecasts are untouched."""
    a = ctx.con.execute("SELECT * FROM analysis_runs WHERE analysis_id=?", (analysis_id,)).fetchone()
    comb = json.loads((ctx.root / a["output_path"] / "combined.json").read_text())
    pack, _ = load_pack(ctx, a["pack_id"])
    errors = json.loads(a["validation_errors"] or "[]")
    res = _assess(ctx, a["offering_id"], pack, comb["outputs"], {"calcs": comb.get("calcs") or {}}, errors)
    fresh = assess.freshness(ctx, a["offering_id"], a["finished_utc"], pack, comb["outputs"] if not errors else None)
    ctx.con.execute("INSERT INTO assessments(analysis_id, classifier_version, policy_version, created_utc, assessment, "
                    "evidence_completeness, operational_readiness, budget_status, decisive_criteria, reasons, unresolved_criteria, "
                    "freshness, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (analysis_id, assess.CLASSIFIER_VERSION, assess.PROPOSED_POLICY, ctx.now(), res["assessment"],
                     res["evidence_completeness"], res["operational_readiness"], res["budget_status"], json.dumps(res["decisive"]),
                     json.dumps(res["reasons"], ensure_ascii=False), json.dumps(res["unresolved"]),
                     json.dumps(fresh, ensure_ascii=False), f"reassessment without LLM call; legacy policy-v1 status: {a['status']}; {note}"))
    ctx.con.commit()
    return {k: res[k] for k in ("assessment", "evidence_completeness", "operational_readiness", "budget_status", "decisive")}


def forecast_lineage(ctx: Ctx, original_id: int, relation: str, reason: str, successor_id: int | None = None) -> int:
    """A separate, timestamped record. The original prediction row is never changed and stays scorable as written."""
    cur = ctx.con.execute("INSERT INTO forecast_lineage(original_prediction_id, successor_prediction_id, relation, created_utc, reason) "
                          "VALUES (?,?,?,?,?)", (original_id, successor_id, relation, ctx.now(), reason))
    ctx.con.commit()
    return cur.lastrowid
