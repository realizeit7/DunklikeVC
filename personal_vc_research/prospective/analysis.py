"""Four-stage LLM analysis of a frozen evidence pack, with mechanical validation and deterministic screening status.

Adapters
* `claude_cli`: the user's authenticated Claude Code, using documented print-mode flags only:
  `claude -p --tools "" --strict-mcp-config --no-session-persistence --output-format json --system-prompt ...
  --json-schema ...`. All tools are disabled and the run happens in an empty working directory, so text in a document
  cannot cause tool execution. The pack is sent on stdin as data.
* `files`: an interactive/manual route. `analysis-export` writes the prompt and payload for each stage; the user (or
  any LLM session) saves stage outputs as JSON; `analysis-import` validates them exactly like adapter output.
* `fixture`: for tests.

The LLM never sets the final status. `derive_status` computes it from validated gates and the critical-information
checklist. Gate 4 (budget eligibility) is computed by software from the ledger.
"""
from __future__ import annotations

import ast
import hashlib
import json
import operator
import re
import subprocess
import tempfile
import time
from pathlib import Path

import jsonschema

from . import journal, ledger
from .core import Ctx, iso, parse_utc
from .llm.schemas_v1 import CRITICAL_ITEMS, SCHEMA_VERSION, STAGES
from .packs import load_pack

PROMPT_VERSION = "analyst_prompt_v1"
PROMPT_PATH = Path(__file__).parent / "llm" / "prompts" / f"{PROMPT_VERSION}.md"
POLICY_VERSION = "screening_policy_v1"
NON_BLOCKING_CRITICAL = {"closing_or_availability_evidence"}
STAGE_ORDER = ["A_extraction", "B_analysis", "C_critical_review", "D_final"]


# ---- adapters ----------------------------------------------------------------------------------------
def relax(schema):
    """Schema sent to the CLI: drop keywords some structured-output engines do not support. The STRICT schema is
    always re-validated locally."""
    if isinstance(schema, dict):
        return {k: relax(v) for k, v in schema.items()
                if k not in ("pattern", "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems")}
    if isinstance(schema, list):
        return [relax(x) for x in schema]
    return schema


def claude_cli_command(system_prompt: str, schema: dict, model: str | None, max_budget_usd: float | None) -> list[str]:
    cmd = ["claude", "-p", "--tools", "", "--strict-mcp-config", "--no-session-persistence", "--output-format", "json",
           "--system-prompt", system_prompt, "--json-schema", json.dumps(relax(schema))]
    if model:
        cmd += ["--model", model]
    if max_budget_usd:
        cmd += ["--max-budget-usd", str(max_budget_usd)]
    return cmd


class ClaudeCLIAdapter:
    name = "claude_cli"

    def __init__(self, model: str | None = None, max_budget_usd: float | None = 5.0, timeout_s: int = 1800):
        self.model, self.max_budget_usd, self.timeout_s = model, max_budget_usd, timeout_s

    def run(self, stage: str, system_prompt: str, payload: str, schema: dict) -> tuple[dict | None, dict]:
        cmd = claude_cli_command(system_prompt, schema, self.model, self.max_budget_usd)
        with tempfile.TemporaryDirectory() as empty:   # no CLAUDE.md, no project files, no tools
            t0 = time.time()
            p = subprocess.run(cmd, input=payload, capture_output=True, text=True, cwd=empty, timeout=self.timeout_s)
        meta = {"returncode": p.returncode, "seconds": round(time.time() - t0, 1), "stderr": p.stderr[-2000:]}
        try:
            d = json.loads(p.stdout)
        except json.JSONDecodeError:
            meta["error"] = "non-JSON CLI output: " + p.stdout[:500]
            return None, meta
        usage = d.get("modelUsage") or {}
        main = max(usage, key=lambda m: usage[m].get("outputTokens", 0)) if usage else None
        u = d.get("usage") or {}
        meta["usage"] = {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                         "cache_read_tokens": u.get("cache_read_input_tokens"),
                         "cache_creation_tokens": u.get("cache_creation_input_tokens"), "duration_ms": d.get("duration_ms")}
        meta.update({"is_error": d.get("is_error"), "model_reported": main, "models_used": list(usage),
                     "provider_reported": (usage.get(main) or {}).get("provider") if main else None,
                     "cost_usd": d.get("total_cost_usd"), "num_turns": d.get("num_turns"),
                     "permission_denials": d.get("permission_denials"), "subtype": d.get("subtype")})
        if d.get("is_error"):
            meta["cli_result_text"] = str(d.get("result"))[:1500]      # v2.1: keep the CLI's own error text
        out = d.get("structured_output")
        if out is None and isinstance(d.get("result"), str):
            try:
                out = json.loads(d["result"])
            except json.JSONDecodeError:
                meta["error"] = "no structured output"
        return out, meta


class FileAdapter:
    """Reads stage outputs saved by the user/another session: <dir>/<stage>.json (+ optional <stage>.meta.json)."""
    name = "files"

    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def run(self, stage, system_prompt, payload, schema):
        f = self.dir / f"{stage}.json"
        meta_f = self.dir / f"{stage}.meta.json"
        meta = json.loads(meta_f.read_text()) if meta_f.exists() else {"model_reported": "unknown (manual import)"}
        if not f.exists():
            meta["error"] = f"missing {f.name}"
            return None, meta
        try:
            return json.loads(f.read_text()), meta
        except json.JSONDecodeError as exc:
            meta["error"] = f"invalid JSON in {f.name}: {exc}"
            return None, meta


class FixtureAdapter:
    name = "fixture"

    def __init__(self, outputs: dict, model: str = "fixture-model"):
        self.outputs, self.model = outputs, model

    def run(self, stage, system_prompt, payload, schema):
        return self.outputs.get(stage), {"model_reported": self.model, "provider_reported": "fixture"}


# ---- payloads ------------------------------------------------------------------------------------------
STAGE_TASK = {
    "A_extraction": "Stage A — evidence extraction. Produce claims (ids A1..), critical_items and missing_information.",
    "B_analysis": "Stage B — business and investment analysis based on the pack and the stage A claims (new claim ids B1..).",
    "C_critical_review": "Stage C — critical review of stages A and B (new claim ids C1..). Same model: this is critical review, "
                         "not independent verification.",
    "D_final": "Stage D — final: respond to every stage C issue, apply the three qualitative gates, write briefing_ko, "
               "and give 0-3 forecasts and an optional illustrative scenario.",
}


def stage_payload(stage: str, pack: dict, prior: dict) -> str:
    return json.dumps({"task": STAGE_TASK[stage], "screening_policy_version": POLICY_VERSION,
                       "prior_stage_outputs": prior, "evidence_pack": pack}, ensure_ascii=False)


# ---- validation ------------------------------------------------------------------------------------------
def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-")
    s = s.replace("—", "-").replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"\s+", " ", s).strip().lower()


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.USub: operator.neg}


def safe_eval(formula: str, names: dict) -> float:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name) and n.id in names:
            return names[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError(f"unsupported expression element {ast.dump(n)[:60]}")
    return ev(ast.parse(formula, mode="eval"))


def all_claims(outputs: dict) -> list[dict]:
    a = outputs.get("A_extraction") or {}
    b = outputs.get("B_analysis") or {}
    c = outputs.get("C_critical_review") or {}
    return list(a.get("claims", [])) + list(b.get("additional_claims", [])) + list(c.get("additional_claims", []))


WS_MATCHES: list[str] = []      # v3 only: citations accepted by the whitespace-insensitive rule (for the run record)


def claims_checks(pack: dict, outputs: dict, errors: list[str], whitespace_insensitive: bool = False,
                  typed_calcs: bool = False):
    """Shared by v1, v2 and v3 validation: claim ids, prefixes, citations (verbatim), evidence-status rules and
    calculations. Appends to `errors`; returns (claims, by_id, valid_cited, check_refs).

    whitespace_insensitive (v3 citation rule 3_1, default off, so v1/v2 are unchanged): a quote whose characters match
    the page exactly but whose WHITESPACE differs is accepted and recorded. This covers PDF text layers that merge
    words, e.g. 'CommonStock,$0.00parvalue'. Any other difference still fails.

    typed_calcs (schema v3_1): calculation claims carry `calc_request` (validated by typed_calc), never a formula. The
    legacy formula evaluation is skipped and no model-written expression is evaluated."""
    pages = {(p["doc_id"], p["page"]): _norm(p["text"]) for p in pack["pages"]}
    docs = {d["doc_id"]: d for d in pack["documents"]}
    claims = all_claims(outputs)
    ids = [c["claim_id"] for c in claims]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        errors.append(f"duplicate claim ids: {sorted(dup)}")
    by_id = {c["claim_id"]: c for c in claims}
    prefix = {"A_extraction": "A", "B_analysis": "B", "C_critical_review": "C"}
    for st, pfx in prefix.items():
        key = "claims" if st == "A_extraction" else "additional_claims"
        for c in (outputs.get(st) or {}).get(key, []):
            if not c["claim_id"].startswith(pfx):
                errors.append(f"{c['claim_id']}: claim id prefix must be {pfx} in {st}")
    valid_cited = set()
    for c in claims:
        cid, status = c["claim_id"], c["evidence_status"]
        good = 0
        for cit in c["citations"]:
            if cit["doc_id"] not in docs:
                errors.append(f"{cid}: citation to doc {cit['doc_id']} not in the evidence pack")
                continue
            txt = pages.get((cit["doc_id"], cit["page"]))
            if txt is None:
                errors.append(f"{cid}: doc {cit['doc_id']} page {cit['page']} has no text in the pack")
                continue
            if _norm(cit["quote"]) not in txt and whitespace_insensitive and \
                    re.sub(r"\s", "", _norm(cit["quote"])) in re.sub(r"\s", "", txt):
                WS_MATCHES.append(f"{cid}: doc {cit['doc_id']} p.{cit['page']} matched ignoring whitespace")
            elif _norm(cit["quote"]) not in txt:
                errors.append(f"{cid}: quote not found verbatim on doc {cit['doc_id']} page {cit['page']}: {cit['quote'][:80]!r}")
                continue
            good += 1
        if status in ("issuer_claim", "document_supported_fact", "independently_corroborated") and good == 0:
            errors.append(f"{cid}: status {status} requires at least one valid citation")
        if status == "independently_corroborated" and not any(
                docs.get(x["doc_id"], {}).get("source_type") not in ("sec_primary_xml", "sec_attachment", "sec_filing_index")
                for x in c["citations"]):
            errors.append(f"{cid}: 'independently_corroborated' needs a cited source not prepared by the issuer")
        if status == "analyst_inference" and not c["basis_claim_ids"]:
            errors.append(f"{cid}: analyst_inference requires basis_claim_ids")
        if status == "calculation" and typed_calcs:
            if not c.get("calc_request"):
                errors.append(f"{cid}: calculation status requires a calc_request (typed, allowlisted)")
        elif status == "calculation":
            calc = c.get("calculation")
            if not calc:
                errors.append(f"{cid}: calculation status requires a calculation")
            else:
                try:
                    got = safe_eval(calc["formula"], {i["name"]: i["value"] for i in calc["inputs"]})
                    if abs(got - calc["result"]) > max(0.01, abs(got) * 0.005):
                        errors.append(f"{cid}: calculation result {calc['result']} != recomputed {got:.4f}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{cid}: calculation not evaluable: {exc}")
                for i in calc["inputs"]:
                    if i["claim_id"] not in by_id:
                        errors.append(f"{cid}: calculation input {i['name']} references unknown claim {i['claim_id']}")
        if good:
            valid_cited.add(cid)

    def check_refs(where: str, refs: list[str], forbid_unverified: bool = False):
        for r in refs:
            if r not in by_id:
                errors.append(f"{where}: unknown claim id {r}")
            elif forbid_unverified and by_id[r]["evidence_status"] == "unverified_assertion":
                errors.append(f"{where}: unverified assertion {r} used as support")

    return claims, by_id, valid_cited, check_refs


def validate(pack: dict, outputs: dict) -> tuple[list[str], dict]:
    errors: list[str] = []
    for st in STAGE_ORDER:
        if outputs.get(st) is None:
            errors.append(f"{st}: missing output")
            continue
        for e in jsonschema.Draft202012Validator(STAGES[st]).iter_errors(outputs[st]):
            errors.append(f"{st}: schema: {e.message[:160]} at {'/'.join(map(str, e.absolute_path))}")
    if errors:
        return errors, {}
    claims, by_id, valid_cited, check_refs = claims_checks(pack, outputs, errors)
    for c in claims:
        check_refs(f"{c['claim_id']}.basis", c["basis_claim_ids"])
    for ci in outputs["A_extraction"]["critical_items"]:
        check_refs(f"critical_item {ci['item']}", ci["claim_ids"])
    for k, sec in outputs["B_analysis"].items():
        if isinstance(sec, dict) and "claim_ids" in sec:
            check_refs(f"B.{k}", sec["claim_ids"])
    n_issues = len(outputs["C_critical_review"]["issues"])
    for i, iss in enumerate(outputs["C_critical_review"]["issues"]):
        check_refs(f"C.issue[{i}]", iss["claim_ids"])
    d = outputs["D_final"]
    answered = {r["issue_index"] for r in d["critique_responses"]}
    if set(range(n_issues)) - answered:
        errors.append(f"D: critique issues without a response: {sorted(set(range(n_issues)) - answered)}")
    gates = [g["gate"] for g in d["gates"]]
    if sorted(gates) != sorted(["evidence_sufficiency", "business_thesis", "price_and_contract"]):
        errors.append(f"D: gates must be exactly the three qualitative gates once each, got {gates}")
    for g in d["gates"]:
        check_refs(f"gate {g['gate']}.supporting", g["supporting_claim_ids"], forbid_unverified=True)
        check_refs(f"gate {g['gate']}.counter", g["counterevidence_claim_ids"])
    for j, f in enumerate(d["forecasts"]):
        check_refs(f"forecast[{j}]", f["basis_claim_ids"])
        cited_text = " ".join(_norm(by_id[r]["claim_text"]) + " " + " ".join(_norm(x["quote"]) for x in by_id[r]["citations"])
                              for r in f["basis_claim_ids"] if r in by_id)
        cited_nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", cited_text)]
        cited_nums += [100 * float((by_id[r].get("calculation") or {}).get("result", 0)) for r in f["basis_claim_ids"] if r in by_id]
        for pct in re.findall(r"(\d+(?:\.\d+)?)\s?%", f["probability_basis"]):
            if not any(abs(float(pct) - n) <= 0.5 for n in cited_nums):
                errors.append(f"forecast[{j}]: statistic {pct}% in probability_basis is not supported by any cited basis claim")
    for k, txt in d["briefing_ko"].items():
        for ref in re.findall(r"\[([ABC]\d{1,3})\]", txt):
            if ref not in by_id:
                errors.append(f"briefing_ko.{k}: reference [{ref}] to unknown claim")
    crit = {ci["item"]: ci for ci in outputs["A_extraction"]["critical_items"]}
    critical = {}
    for item in CRITICAL_ITEMS:
        ci = crit.get(item)
        ok = bool(ci and ci["status"] == "confirmed_with_citation" and ci["claim_ids"]
                  and all(r in valid_cited for r in ci["claim_ids"]))
        critical[item] = "confirmed" if ok else ("non_blocking_unknown" if item in NON_BLOCKING_CRITICAL else "not_confirmed")
    return errors, critical


def derive_status(errors: list[str], critical: dict, gates: list[dict]) -> str:
    if errors:
        return "analysis_failed"
    g = {x["gate"]: x["result"] for x in gates}
    if any(v == "not_confirmed" for v in critical.values()) or g.get("evidence_sufficiency") != "pass":
        return "needs_information"
    if "fail" in (g.get("business_thesis"), g.get("price_and_contract")):
        return "fails_research_screen"
    if "unknown" in (g.get("business_thesis"), g.get("price_and_contract")):
        return "needs_information"
    return "passes_research_screen"


def budget_gate(ctx: Ctx, offering_id: str) -> dict:
    o = ctx.con.execute("SELECT issuer_id FROM offerings WHERE offering_id=?", (offering_id,)).fetchone()
    key = ledger.issuer_key_for(ctx, o["issuer_id"])[0]
    stt = ledger.current_state(ctx)
    ar, ir = stt.annual_remaining_cents, stt.issuer_remaining_cents(key)
    return {"gate": "budget_eligibility", "result": "pass" if ar > 0 and ir > 0 else "fail", "source": "software",
            "criteria": f"budget_policy_v1: annual remaining {ledger.usd(ar)} ({stt.period_label}); issuer {key} remaining {ledger.usd(ir)}",
            "uncertainty": "computed at analysis time; re-checked at approval"}


def _errors_by_stage(errors: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in errors:
        m = re.match(r"^(A_extraction|B_analysis|C_critical_review|D_final):", e)
        if m:
            st = m.group(1)
        elif re.match(r"^A\d|^critical_item|^duplicate", e):
            st = "A_extraction"
        elif re.match(r"^B\d|^B\.", e):
            st = "B_analysis"
        elif re.match(r"^C\d|^C\.", e):
            st = "C_critical_review"
        else:
            st = "D_final"
        out.setdefault(st, []).append(e)
    return out


# ---- orchestration --------------------------------------------------------------------------------------
def register_version(ctx: Ctx, version_id: str, role: str, description: str, model_requested: str | None = None,
                     development_offering_ids: list[str] | None = None, prompt_version: str = PROMPT_VERSION,
                     repair_rounds: int = 0) -> None:
    ctx.con.execute("INSERT OR IGNORE INTO analyst_versions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (version_id, role, prompt_version, SCHEMA_VERSION, POLICY_VERSION, model_requested,
                     json.dumps({"tools": "disabled", "max_budget_usd_per_stage": 5.0, "repair_rounds": repair_rounds}),
                     description, ctx.now(),
                     json.dumps(development_offering_ids or [])))
    ctx.con.commit()


def run_analysis(ctx: Ctx, offering_id: str, pack_id: str, adapter, version_id: str, repair_override: int | None = None,
                 note: str = "") -> dict:
    v = ctx.con.execute("SELECT * FROM analyst_versions WHERE version_id=?", (version_id,)).fetchone()
    if v is None:
        raise ValueError(f"analyst version {version_id} is not registered (register before running)")
    pack, pack_sha = load_pack(ctx, pack_id)
    if pack["offering"]["offering_id"] != offering_id:
        raise ValueError("pack belongs to another offering")
    system_prompt = (PROMPT_PATH.parent / f"{v['prompt_version']}.md").read_text()
    settings = json.loads(v["settings"] or "{}")
    started = ctx.now()
    outputs, metas = {}, {}
    out_dir = ctx.root / ctx.cfg.raw["paths"].get("analyses_dir", "data/analyses") / f"{offering_id}_{started.replace(':', '')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for st in STAGE_ORDER:
        out, meta = adapter.run(st, system_prompt, stage_payload(st, pack, outputs), STAGES[st])
        outputs[st], metas[st] = out, meta
        (out_dir / f"{st}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        (out_dir / f"{st}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        if out is None:
            break
    errors, critical = validate(pack, outputs) if all(outputs.get(st) is not None for st in STAGE_ORDER) else (["stage missing"], {})
    for rnd in range(int(settings.get("repair_rounds", 0) if repair_override is None else repair_override)):
        if not errors or errors == ["stage missing"]:
            break
        for st, errs in _errors_by_stage(errors).items():   # one repair request per failing stage, with the exact errors
            payload = json.dumps({"task": "REPAIR: your previous output for this stage failed mechanical validation. Return the "
                                          "complete corrected output for this stage. Keep claim ids unchanged unless an error "
                                          "requires removing a claim; do not add unsupported content.",
                                  "validation_errors": errs, "previous_output": outputs[st],
                                  "original_request": json.loads(stage_payload(st, pack, {k: outputs[k] for k in STAGE_ORDER[:STAGE_ORDER.index(st)]}))},
                                 ensure_ascii=False)
            out, meta = adapter.run(st, system_prompt, payload, STAGES[st])
            metas[f"{st}_repair{rnd + 1}"] = meta
            (out_dir / f"{st}_repair{rnd + 1}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
            (out_dir / f"{st}_repair{rnd + 1}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
            if out is not None:
                outputs[st] = out
        errors, critical = validate(pack, outputs)
    finished = ctx.now()
    gates = (outputs.get("D_final") or {}).get("gates", []) if not errors else []
    status = derive_status(errors, critical, gates)
    combined = json.dumps({"outputs": outputs, "metas": metas}, sort_keys=True, ensure_ascii=False)
    (out_dir / "combined.json").write_text(combined)
    dev = json.loads(v["development_offering_ids"])
    models = sorted({m.get("model_reported") for m in metas.values() if m and m.get("model_reported")})
    cost = sum((m or {}).get("cost_usd") or 0 for m in metas.values())
    cur = ctx.con.execute(
        """INSERT INTO analysis_runs(offering_id, pack_id, pack_sha256, version_id, prompt_version, schema_version, policy_version,
           adapter, model_reported, provider_reported, settings, started_utc, finished_utc, status, split, output_path,
           output_sha256, validation_errors, cost_usd, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (offering_id, pack_id, pack_sha, version_id, v["prompt_version"], SCHEMA_VERSION, POLICY_VERSION, adapter.name,
         ";".join(models) or None, ";".join(sorted({str(m.get('provider_reported')) for m in metas.values() if m})),
         v["settings"], started, finished, status, "development" if offering_id in dev else "evaluation",
         str(out_dir.relative_to(ctx.root)), hashlib.sha256(combined.encode()).hexdigest(), json.dumps(errors), cost,
         json.dumps({"critical": critical, "note": note, "stage_meta": {k: {x: (m or {}).get(x) for x in ("seconds", "num_turns", "is_error",
                                                                                              "models_used", "error")}
                                                          for k, m in metas.items()}})))
    aid = cur.lastrowid
    for st, key in [("A_extraction", "claims"), ("B_analysis", "additional_claims"), ("C_critical_review", "additional_claims")]:
        for c in (outputs.get(st) or {}).get(key, []) if not errors else []:
            ctx.con.execute("""INSERT INTO analysis_claims(analysis_id, claim_id, stage, claim_text, claim_type, evidence_status,
                citations, observed_cutoff_utc, financial_period, calculation_inputs, contradictions, missing) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (aid, c["claim_id"], st, c["claim_text"], c["claim_type"], c["evidence_status"],
                             json.dumps(c["citations"], ensure_ascii=False), pack["cutoff_utc"], c["financial_period"],
                             json.dumps(c.get("calculation")), c["contradictions"], ""))
    for g in gates:
        ctx.con.execute("INSERT INTO analysis_gates(analysis_id, gate, result, source, criteria, supporting, counterevidence, uncertainty) "
                        "VALUES (?,?,?,?,?,?,?,?)", (aid, g["gate"], g["result"], "llm", json.dumps(g["criteria_applied"], ensure_ascii=False),
                                                     json.dumps(g["supporting_claim_ids"]), json.dumps(g["counterevidence_claim_ids"]),
                                                     g["uncertainty"]))
    bg = budget_gate(ctx, offering_id)
    ctx.con.execute("INSERT INTO analysis_gates(analysis_id, gate, result, source, criteria, uncertainty) VALUES (?,?,?,?,?,?)",
                    (aid, bg["gate"], bg["result"], bg["source"], bg["criteria"], bg["uncertainty"]))
    n_fc = 0
    if not errors:
        for f in outputs["D_final"]["forecasts"]:
            pid = journal.add_forecast(ctx, offering_id, f["outcome_definition"], f["event_kind"], f["horizon_months"],
                                       f["probability"], f["resolution_evidence"], f["reporting_lag_days"], f["unknown_treatment"],
                                       forecaster=f"{version_id} ({';'.join(models)})",
                                       permitted_evidence=f"basis claims {f['basis_claim_ids']}; analysis {aid}")
            ctx.con.execute("INSERT INTO prediction_meta VALUES (?,?,?,?,?,?)",
                            (pid, aid, pack_sha, version_id, ";".join(models), f["probability_label"]))
            n_fc += 1
    ctx.con.commit()
    return {"analysis_id": aid, "status": status, "errors": errors[:20], "n_errors": len(errors), "critical": critical,
            "forecasts": n_fc, "models": models, "cost_usd": round(cost, 4), "output_dir": str(out_dir)}


def export_stage_prompts(ctx: Ctx, pack_id: str, out_dir: Path) -> list[str]:
    """Manual route: write the system prompt, schemas and stage-A payload. Later stages need prior outputs; regenerate
    with --prior once each stage's output has been saved as <stage>.json."""
    pack, _ = load_pack(ctx, pack_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "SYSTEM_PROMPT.md").write_text(PROMPT_PATH.read_text())
    written = ["SYSTEM_PROMPT.md"]
    prior = {}
    for st in STAGE_ORDER:
        (out_dir / f"{st}.schema.json").write_text(json.dumps(STAGES[st], indent=1))
        written.append(f"{st}.schema.json")
        f = out_dir / f"{st}.json"
        if st == "A_extraction" or all((out_dir / f"{p}.json").exists() for p in STAGE_ORDER[:STAGE_ORDER.index(st)]):
            (out_dir / f"{st}.payload.json").write_text(stage_payload(st, pack, prior))
            written.append(f"{st}.payload.json")
        if f.exists():
            prior[st] = json.loads(f.read_text())
        else:
            break
    return written


class StoredOutputsAdapter:
    """Replays the FINAL stored outputs of an earlier run (no LLM call) so they can be re-validated under a corrected
    schema. The new run is labelled; the original run is never modified."""
    name = "revalidation_of_stored_outputs"

    def __init__(self, outputs: dict, metas: dict, source_analysis_id: int):
        self.outputs, self.source = outputs, source_analysis_id
        main = sorted({(m or {}).get("model_reported") for m in metas.values() if (m or {}).get("model_reported")})
        self.meta = {"model_reported": ";".join(main), "cost_usd": 0.0, "revalidated_from_analysis": source_analysis_id}

    def run(self, stage, system_prompt, payload, schema):
        return self.outputs.get(stage), dict(self.meta)


def revalidate(ctx: Ctx, analysis_id: int) -> dict:
    a = ctx.con.execute("SELECT * FROM analysis_runs WHERE analysis_id=?", (analysis_id,)).fetchone()
    combined = json.loads((ctx.root / a["output_path"] / "combined.json").read_text())
    adapter = StoredOutputsAdapter(combined["outputs"], combined["metas"], analysis_id)
    v = ctx.con.execute("SELECT version_id FROM analyst_versions WHERE version_id=?", (a["version_id"],)).fetchone()
    # replay without repair rounds: these are the exact outputs the model produced (after any repair in the original run)
    res = run_analysis(ctx, a["offering_id"], a["pack_id"], adapter, v["version_id"], repair_override=0,
                       note=f"revalidation of analysis {analysis_id} outputs under {SCHEMA_VERSION}; no new LLM call")
    return res
