"""Schema analysis_schema_v3_1 (v2.2.1), for screening_policy_v1_3 (proposed). It changes three things in v3_0.

1. Claims carry `calc_request` (an allowlisted kind plus typed inputs, or a K-id reference) instead of a free-form
   `calculation` formula.
2. Every rule finding carries `predicate`: one assessment per AUTHORED element of the rule's predicate (policy
   v1_3), with evidence for and against, reasoning, missing facts and temporal conflicts. Code recomputes the
   overall predicate.
3. Stage E (the existing post-finding review) adds `predicate_reviews`: a second model pass over every adverse
   candidate against the exact rule text and the original cited evidence. Objections are preserved, and a material
   unresolved objection blocks decisiveness. This is not independent verification.

v3_0 outputs are not valid v3_1 outputs. Cached v3_0 stages enter a v3_1 run only through the explicit, logged
migration in analysis_v3.migrate_cached_stage.
"""
import copy

from . import schemas_v3 as v3
from .schemas_v1 import IDS, STR, _obj

SCHEMA_VERSION = "analysis_schema_v3_1"
QUESTIONS, RULE_IDS = v3.QUESTIONS, v3.RULE_IDS
CALC_KINDS = ["implied_equity", "post_money", "ownership_percent", "runway_months", "ref"]

CALC_INPUT = _obj({"role": STR, "claim_id": STR, "value": {"type": "string"},
                   "unit": {"enum": ["USD", "USD_per_share", "shares", "percent"]},
                   "as_of": v3.DATE_OR_EMPTY, "period_start": v3.DATE_OR_EMPTY, "period_end": v3.DATE_OR_EMPTY,
                   "security_class": STR})
CALC_REQUEST = {"anyOf": [{"type": "null"}, _obj({"kind": {"enum": CALC_KINDS}, "k_ref": STR,
                                                  "inputs": {"type": "array", "items": CALC_INPUT}})]}

CLAIM = copy.deepcopy(v3.CLAIM)
del CLAIM["properties"]["calculation"]
CLAIM["properties"]["calc_request"] = CALC_REQUEST
CLAIM["required"] = list(CLAIM["properties"])


def _with_claims(stage: dict, key: str) -> dict:
    s = copy.deepcopy(stage)
    s["properties"][key] = {"type": "array", "items": CLAIM, **({"minItems": 1} if key == "claims" else {})}
    return s


STAGE_A = _with_claims(v3.STAGE_A, "claims")
STAGE_B = _with_claims(v3.STAGE_B, "additional_claims")
STAGE_C = _with_claims(v3.STAGE_C, "additional_claims")

ELEMENT = _obj({"element_id": STR, "assessment": {"enum": ["established", "contradicted", "unknown"]},
                "evidence_for": IDS, "evidence_against": IDS, "reasoning_ko": STR})
PREDICATE = _obj({"elements": {"type": "array", "items": ELEMENT}, "branch": STR,
                  "overall": {"enum": ["met", "not_met", "unresolved", "not_applicable"]},
                  "missing_facts_ko": STR, "temporal_conflicts_ko": STR})
FINDING = copy.deepcopy(v3.FINDING)
FINDING["properties"]["predicate"] = PREDICATE
FINDING["required"] = list(FINDING["properties"])
STAGE_D = copy.deepcopy(v3.STAGE_D)
STAGE_D["properties"]["rule_findings"]["items"] = FINDING

OBJECTION = _obj({"element_id": STR, "objection_ko": STR, "material": {"type": "boolean"}, "resolved": {"type": "boolean"}})
REVIEW = _obj({"rule_id": STR, "review_overall": {"enum": ["met", "not_met", "unresolved", "not_applicable"]},
               "agrees_with_finding": {"type": "boolean"}, "objections": {"type": "array", "items": OBJECTION}})
STAGE_E = copy.deepcopy(v3.STAGE_E)
STAGE_E["properties"]["predicate_reviews"] = {"type": "array", "items": REVIEW}
STAGE_E["required"] = list(STAGE_E["properties"])

STAGES = {"A_extraction": STAGE_A, "B_analysis": STAGE_B, "C_critical_review": STAGE_C, "D_final": STAGE_D,
          "E_support_check": STAGE_E, "F_brief_ko": v3.STAGE_F}
STAGE_ORDER = list(STAGES)
