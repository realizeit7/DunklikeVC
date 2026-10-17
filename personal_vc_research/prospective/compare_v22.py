"""Deterministic comparison (v2.2): analysis 10's STORED findings re-classified by the v3 classifier code, with no
model call.

Compatibility limits, stated rather than hidden:
* Analysis 10 has no rule findings for policy v1_2. Its decisive criteria are mapped to the nearest v1_2 rule
  (MAPPING below). The model's adverse JUDGMENT was made against the old criterion text, not against the v1_2 adverse
  definition, so that judgment is reused as it stands.
* Evidence kinds and as-of dates were not extracted in v2. EVIDENCE_KIND below is the assistant's mapping, recorded
  as such.
* Support verdicts are analysis 10's own stage-E model verdicts.
"""
from __future__ import annotations

import json

from . import assess_v3
from . import policy as policy_mod
from .core import Ctx

MAPPING = {  # v2.1 criterion -> v1_2 rule (assistant mapping)
    "BT4_financial_condition_and_funding": "R-FIN-1",
    "PC1_security_cash_path": "R-TERMS-1",          # holder-value obstacles; only worse-than-norm terms can decide
    "PC3_investor_rights_and_dilution": "R-TERMS-3",  # dilution/priority identification; cannot reject on its own
}
EVIDENCE_KIND = {"A13": ("form_field", "2025-12-31"), "A15": ("audited_financials", "2025-12-31"), "A18": ("form_field", ""),
                 "A21": ("contract_term", ""), "A22": ("contract_term", "2026-05-04"), "A7": ("contract_term", ""),
                 "A9": ("contract_term", ""), "A31": ("form_field", ""), "A32": ("form_field", ""), "A8": ("contract_term", ""),
                 "A19": ("contract_term", ""), "A11": ("form_field", "2026-06-25"), "B2": ("analyst_inference", "")}


def compare_analysis(ctx: Ctx, analysis_id: int = 10, policy_version: str = "screening_policy_v1_2") -> dict:
    """policy_version='screening_policy_v1_3' + classifier v3_1: analysis 10 has no predicate assessments, so every
    authored element is 'unknown' and no finding can be decisive (v2.2.1 reclassification)."""
    pol = policy_mod.load(policy_version)
    rows = [dict(r) for r in ctx.con.execute("SELECT * FROM criterion_results WHERE analysis_id=?", (analysis_id,))]
    claims = {r["claim_id"]: dict(r) for r in ctx.con.execute("SELECT * FROM analysis_claims WHERE analysis_id=?", (analysis_id,))}
    by_id = {}
    for cid, c in claims.items():
        kind, as_of = EVIDENCE_KIND.get(cid, ("analyst_inference", ""))
        by_id[cid] = {"claim_id": cid, "claim_text": c["claim_text"], "evidence_kind": kind, "as_of": as_of,
                      "attribution": "analysis 10 claim", "citations": json.loads(c["citations"]),
                      "evidence_status": c["evidence_status"]}
    valid = {cid for cid, c in by_id.items() if c["citations"] or c["evidence_status"] == "analyst_inference"}
    checks = {r["claim_id"]: {"verdict": r["verdict"], "overstatement": r["overstatement"]}
              for r in ctx.con.execute("SELECT * FROM support_checks WHERE analysis_id=? AND checker LIKE 'model:%'", (analysis_id,))}
    findings = {rid: {"rule_id": rid, "result": "unknown", "scope": "none", "claims_independently_decisive": False, "facts": [],
                      "interpretation_ko": "", "counterevidence_ko": "", "unresolved_ko": "", "what_would_change_ko": ""}
                for rid in pol["_rules"]}
    for r in rows:
        rid = MAPPING.get(r["criterion_id"])
        if rid and r["final_result"] == "fail":
            f = findings[rid]
            f.update(result="adverse", scope="economic_concern", claims_independently_decisive=True,
                     interpretation_ko=r["reason_ko"])
            f["facts"] += [{"claim_id": c, "role": "supporting", "generic_trigger": "none"} for c in json.loads(r["claim_ids"])
                           if c not in {x["claim_id"] for x in f["facts"]}]
    outs = {"D_final": {"rule_findings": list(findings.values())}}
    res = assess_v3.evaluate_findings(pol, outs, by_id, valid, {}, checks, "2026-10-14T16:46:19+00:00")
    decisive = [r["rule_id"] for r in res if r["independently_decisive"]]
    return {"classifier": assess_v3.CLASSIFIER_VERSION, "policy": pol["version"], "policy_sha256": pol["_sha256"],
            "screening": ("provisional_reject" if decisive else "provisional_unresolved"), "decisive": decisive,
            "findings": [{k: r[k] for k in ("rule_id", "model_result", "final_result", "validator_notes", "predicate_elements")} |
                         {"facts": [{k: x[k] for k in ("claim_id", "generic_effective", "evidence_kind", "support_check")} for x in r["facts"]]}
                         for r in res if r["model_result"] != "unknown"]}
