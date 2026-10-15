"""Structured-output schemas for analyst v2 (schema version analysis_schema_v2_0).

Changes from v1 (v1 files are unchanged and v1 analyses remain valid under v1):
* Stage A adds `valuation_inputs` (price, share counts by kind/class/date, convertibles with a terms-disclosed flag)
  and `financial_statements` (period end, assurance level). Valuation arithmetic is done in code (calc.py), never by
  the model; results are passed to later stages as K-ids.
* Stage D replaces the three gate verdicts with per-criterion results (pass/fail/unknown) carrying failure grounds,
  supporting and counter claim ids and a Korean reason. Gate results and the assessment are derived in code.
* Stage D forecasts use FORECAST_V2: one event (no "or"), a target type (event occurs / issuer announces /
  independently corroborated), an explicit deadline, allowed evidence, assumptions and cancellation treatment.
* Stage E (new) is a structured support check of the decisive claims, labelled as model judgment.
* Stage F (new) writes the Korean top summary AFTER the assessment is computed, so the prose cannot contradict it.
"""
from .schemas_v1 import CLAIM, CRITICAL_ITEMS, IDS, STAGE_B, STAGE_C, STR, _obj

SCHEMA_VERSION = "analysis_schema_v2_0"

# criterion -> gate. All are REQUIRED under the proposed screening_policy_v1_1 (see policies/).
CRITERIA = {
    "BT1_customer_and_revenue_model": "business_thesis",
    "BT2_demand_evidence": "business_thesis",
    "BT3_competition": "business_thesis",
    "BT4_financial_condition_and_funding": "business_thesis",
    "BT5_team_evidence": "business_thesis",
    "PC1_security_cash_path": "price_and_contract",
    "PC2_price_vs_path_to_value": "price_and_contract",
    "PC3_investor_rights_and_dilution": "price_and_contract",
}
FAILURE_GROUNDS = ["documented_adverse_fact", "documented_contract_term", "deterministic_calculation",
                   "internal_inconsistency_in_documents", "missing_information", "pre_revenue_status",
                   "absence_of_voting_rights", "arbitrary_price_disclosure", "comparable_valuation", "other"]
# grounds that can never on their own make a failure "supported" (proposed policy v1.1, section 3)
NON_DECISIVE_GROUNDS = {"missing_information", "pre_revenue_status", "absence_of_voting_rights",
                        "arbitrary_price_disclosure", "comparable_valuation", "other"}

NUM_OR_NULL = {"anyOf": [{"type": "null"}, {"type": "number"}]}
STAGE_A = _obj({
    "claims": {"type": "array", "items": CLAIM, "minItems": 1},
    "critical_items": {"type": "array", "items": _obj({
        "item": {"enum": CRITICAL_ITEMS},
        "status": {"enum": ["confirmed_with_citation", "not_found_in_pack", "contradictory", "not_readable_in_pack"]},
        "claim_ids": IDS, "note": STR})},
    "missing_information": IDS,
    "valuation_inputs": _obj({
        "price_per_share_usd": NUM_OR_NULL, "price_claim_id": STR,
        "share_counts": {"type": "array", "items": _obj({
            "kind": {"enum": ["issued_outstanding", "authorized", "offered_minimum", "offered_maximum",
                              "reserved_or_options"]},
            "share_class": STR, "value": {"type": "number"}, "as_of": STR, "claim_id": STR})},
        "convertible_instruments": {"type": "array", "items": _obj({
            "instrument": STR, "principal_usd": NUM_OR_NULL, "conversion_terms_disclosed": {"type": "boolean"},
            "claim_ids": IDS, "note": STR})},
        "note": STR}),
    "financial_statements": _obj({
        "period_end": {"type": "string", "pattern": "^(\\d{4}-\\d{2}-\\d{2})?$"},
        "assurance": {"enum": ["audited", "reviewed", "self_certified", "unknown"]}, "claim_ids": IDS}),
})

CRITERION = _obj({
    "criterion_id": {"enum": list(CRITERIA)}, "result": {"enum": ["pass", "fail", "unknown"]},
    "failure_grounds": {"type": "array", "items": {"enum": FAILURE_GROUNDS}},
    "claim_ids": IDS, "counter_claim_ids": IDS, "reason_ko": STR, "what_would_change_ko": STR})

FORECAST_V2 = _obj({
    "event_kind": {"enum": ["business", "disclosure"]},
    "target_type": {"enum": ["event_occurs", "issuer_announces", "independently_corroborated"]},
    "event": STR, "target_scope": STR,
    "deadline_date": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
    "reporting_lag_days": {"type": "integer", "minimum": 0, "maximum": 365},
    "allowed_evidence": {"type": "array", "items": STR, "minItems": 1},
    "probability": {"type": "number", "minimum": 0, "maximum": 1},
    "probability_label": {"const": "model_judgment_uncalibrated"},
    "rationale": STR, "assumptions": {"type": "array", "items": STR},
    "unknown_treatment": STR, "cancellation_treatment": STR,
    "early_resolution": {"const": "true_may_resolve_before_deadline"},
    "silence_treatment": {"const": "silence_is_not_false"},
    "basis_claim_ids": IDS})

STAGE_D = _obj({
    "criteria": {"type": "array", "items": CRITERION, "minItems": len(CRITERIA), "maxItems": len(CRITERIA)},
    "critique_responses": {"type": "array", "items": _obj({"issue_index": {"type": "integer"}, "accepted": {"type": "boolean"},
                                                            "response": STR})},
    "forecasts": {"type": "array", "items": FORECAST_V2, "maxItems": 3},
})

SUPPORT_CHECK = _obj({
    "claim_id": STR,
    "passage_supports": {"enum": ["yes", "partly", "no"]},
    "omitted_qualifications": STR,
    "evidence_type": {"enum": ["issuer_statement", "audited_financial_statement", "unaudited_financial_figure",
                               "contract_text", "regulatory_form_field", "third_party_source", "calculation", "inference"]},
    "conflicts": STR,
    "overstatement": {"enum": ["none", "minor", "material"]},
    "verdict": {"enum": ["supported", "partially_supported", "not_supported"]},
    "note_ko": STR})
STAGE_E = _obj({"judgment_label": {"const": "model_judgment_not_verification"},
                "checks": {"type": "array", "items": SUPPORT_CHECK}})

STAGE_F = _obj({
    "business_one_liner_ko": STR,
    "summary_ko": STR,
    "decisive_reasons_ko": {"type": "array", "items": STR, "minItems": 1, "maxItems": 3},
    "material_missing_ko": {"type": "array", "items": STR, "maxItems": 5},
    "what_would_change_ko": {"type": "array", "items": STR, "minItems": 1, "maxItems": 4},
    "terms_explained_ko": {"type": "array", "items": _obj({"term": STR, "explanation_ko": STR}), "maxItems": 6},
})

STAGES = {"A_extraction": STAGE_A, "B_analysis": STAGE_B, "C_critical_review": STAGE_C, "D_final": STAGE_D,
          "E_support_check": STAGE_E, "F_brief_ko": STAGE_F}
STAGE_ORDER = list(STAGES)
