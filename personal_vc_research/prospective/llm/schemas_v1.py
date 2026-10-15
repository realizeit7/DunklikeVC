"""Structured-output schemas for the four analysis stages (schema version analysis_schema_v1).

Every object sets additionalProperties=false: any field outside the schema (for example a 'tool_call' smuggled in
by injected document text) makes the output invalid. Citations are checked mechanically against the frozen pack.
"""
SCHEMA_VERSION = "analysis_schema_v1_0_2"
# v1_0_2 (validator fix, 2026-10-14): a percentage in a forecast's probability_basis is accepted when it is within
# 0.5 points of a number (or a calculation result x 100) in the cited basis claims; v1_0_1 required the literal string,
# which rejected "about 32%" backed by a cited calculation of 32.1%.
# v1_0_1 (defect fix, 2026-10-14): calculation input names may contain digits after the first character
# (^[a-z_][a-z0-9_]*$). The v1 pattern ^[a-z_]+$ was enforced locally but never sent to the model (patterns are
# stripped from the CLI schema), so valid outputs such as 'revenue_2025' failed validation.

EVIDENCE_STATUS = ["issuer_claim", "document_supported_fact", "independently_corroborated", "calculation",
                   "analyst_inference", "unverified_assertion"]
CLAIM_TYPES = ["identity", "security_terms", "contract_provision", "financial", "traction", "market", "competition",
               "team", "risk", "use_of_proceeds", "availability", "other"]
CRITICAL_ITEMS = ["issuer_and_offering_identity", "security_type", "operative_contract", "price_cap_and_conversion_terms",
                  "minimum_investment_and_fees", "financial_statements_and_dates", "closing_or_availability_evidence"]


def _obj(props: dict, required: list | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or list(props), "additionalProperties": False}


STR = {"type": "string"}
IDS = {"type": "array", "items": STR}
CITATION = _obj({"doc_id": {"type": "integer"}, "page": {"type": "integer"},
                 "quote": {"type": "string", "minLength": 8, "maxLength": 400}})
CLAIM = _obj({
    "claim_id": {"type": "string", "pattern": "^[A-Z][0-9]{1,3}$"},
    "claim_text": STR, "claim_type": {"enum": CLAIM_TYPES}, "evidence_status": {"enum": EVIDENCE_STATUS},
    "citations": {"type": "array", "items": CITATION},
    "financial_period": STR,
    "calculation": {"anyOf": [{"type": "null"}, _obj({
        "formula": STR, "inputs": {"type": "array", "items": _obj({"name": {"type": "string", "pattern": "^[a-z_][a-z0-9_]*$"},
                                                                    "value": {"type": "number"}, "claim_id": STR})},
        "result": {"type": "number"}})]},
    "basis_claim_ids": IDS, "contradictions": STR})

STAGE_A = _obj({
    "claims": {"type": "array", "items": CLAIM, "minItems": 1},
    "critical_items": {"type": "array", "items": _obj({
        "item": {"enum": CRITICAL_ITEMS}, "status": {"enum": ["confirmed_with_citation", "not_found_in_pack", "contradictory"]},
        "claim_ids": IDS, "note": STR})},
    "missing_information": IDS})

SECTION = _obj({"assessment": STR, "claim_ids": IDS})
STAGE_B = _obj({
    "business_model": SECTION, "demand_evidence": SECTION, "competition": SECTION, "economics_and_funding": SECTION,
    "execution_risks": SECTION, "team_evidence": SECTION, "security_path_to_proceeds": SECTION, "price_and_terms": SECTION,
    "is_pre_revenue": {"type": "boolean"}, "additional_claims": {"type": "array", "items": CLAIM}})

STAGE_C = _obj({
    "issues": {"type": "array", "items": _obj({
        "issue_type": {"enum": ["unsupported_conclusion", "contradictory_evidence", "optimistic_assumption", "missing_fact"]},
        "target": STR, "explanation": STR, "claim_ids": IDS, "severity": {"enum": ["high", "medium", "low"]}})},
    "additional_claims": {"type": "array", "items": CLAIM}})

GATE = _obj({"gate": {"enum": ["evidence_sufficiency", "business_thesis", "price_and_contract"]},
             "result": {"enum": ["pass", "fail", "unknown"]}, "criteria_applied": IDS,
             "supporting_claim_ids": IDS, "counterevidence_claim_ids": IDS, "uncertainty": STR})
FORECAST = _obj({
    "outcome_definition": STR, "event_kind": {"enum": ["business", "disclosure"]}, "horizon_months": {"enum": [6, 12]},
    "probability": {"type": "number", "minimum": 0, "maximum": 1},
    "probability_label": {"const": "model_judgment_uncalibrated"}, "probability_basis": STR,
    "reporting_lag_days": {"type": "integer", "minimum": 0, "maximum": 365}, "resolution_evidence": STR,
    "unknown_treatment": STR, "basis_claim_ids": IDS})
BRIEF_KO = _obj({k: STR for k in ["summary", "what_it_does", "strongest_evidence", "failure_reasons",
                                   "investor_proceeds_path", "price_and_contract", "unknowns", "future_evidence"]})
STAGE_D = _obj({
    "gates": {"type": "array", "items": GATE, "minItems": 3, "maxItems": 3},
    "critique_responses": {"type": "array", "items": _obj({"issue_index": {"type": "integer"}, "accepted": {"type": "boolean"},
                                                            "response": STR})},
    "briefing_ko": BRIEF_KO,
    "forecasts": {"type": "array", "items": FORECAST, "maxItems": 3},
    "scenario": {"anyOf": [{"type": "null"}, _obj({
        "label": {"const": "illustrative scenario, not an expected return"},
        "assumptions": _obj({"exit_value_usd": {"type": "number"}, "dilution_pct": {"type": "number"},
                             "years_to_exit": {"type": "number"}, "other": STR}),
        "explanation_ko": STR})]}})

STAGES = {"A_extraction": STAGE_A, "B_analysis": STAGE_B, "C_critical_review": STAGE_C, "D_final": STAGE_D}
