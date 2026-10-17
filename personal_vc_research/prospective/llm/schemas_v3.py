"""Structured-output schemas for analyst v3 (schema version analysis_schema_v3_0), for screening_policy_v1_2 (proposed).

Changes from v2 (v2 files are unchanged and v2 analyses stay valid under v2):
* Every claim carries an `evidence_kind` and one or more `dimensions` (TECH, DEMAND, REG, TEAM, FIN, TERMS). A claim
  in more than one dimension must explain why (`dimension_rationale`).
* Stage A extracts dated cash points, spending points and share counts with their basis. It also separates existing
  from planned convertibles, and issuer-paid from investor-paid fees. Arithmetic is done in calc.py.
* Stage D gives one finding per policy rule. Each finding lists every fact with its role (supporting / counter) and
  its generic trigger (G1–G8 or none), plus an interpretation, counterevidence, unresolved facts, scope and what would
  change it. Code decides whether a finding is decisive.
* Stage D answers the seven thesis questions (upside, milestones, advantage, financing, holder value, terms, SCHG).
* No forecasts are generated in v3. Existing forecasts are untouched.
* Stage E is the structured support check (model judgment). Stage F writes the Korean prose sections after the
  classification is computed.
"""
from .schemas_v1 import CRITICAL_ITEMS, IDS, STR, _obj
from .schemas_v2 import STAGE_E

SCHEMA_VERSION = "analysis_schema_v3_0"
DIMENSIONS = ["TECH", "DEMAND", "REG", "TEAM", "FIN", "TERMS"]
EVIDENCE_KINDS = ["preclinical_efficacy", "clinical_human_data", "technical_validation", "customer_commercial",
                  "payer_reimbursement", "regulatory_status", "team_record", "audited_financials", "unaudited_financials",
                  "issuer_projection", "contract_term", "form_field", "third_party", "calculation", "analyst_inference"]
EVIDENCE_STATUS = ["issuer_claim", "document_supported_fact", "independently_corroborated", "calculation",
                   "analyst_inference", "unverified_assertion"]
RULE_IDS = ["R-EV1", "R-TECH-1", "R-DEM-1", "R-REG-1", "R-TEAM-1", "R-FIN-1", "R-TERMS-1", "R-TERMS-2", "R-TERMS-3"]
GENERIC = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "none"]
QUESTIONS = {
    "Q1_value_creation": "What must go right for this company to create substantial value?",
    "Q2_next_milestones": "What are the next one or two meaningful milestones?",
    "Q3_advantage_evidence": "What evidence supports the proposed advantage?",
    "Q4_financing_needed": "What financing may be needed to reach those milestones?",
    "Q5_holder_value_path": "What has to happen for THIS security holder to receive value?",
    "Q6_terms_affecting_proceeds": "What price, conversion, priority, dilution or fee terms materially affect proceeds?",
    "Q7_vs_schg": "What specific reason, if any, supports choosing this investment over the SCHG alternative?",
}

NUM_OR_NULL = {"anyOf": [{"type": "null"}, {"type": "number"}]}
DATE_OR_EMPTY = {"type": "string", "pattern": "^(\\d{4}-\\d{2}-\\d{2})?$"}
CITATION = _obj({"doc_id": {"type": "integer"}, "page": {"type": "integer"},
                 "quote": {"type": "string", "minLength": 8, "maxLength": 400}})
CLAIM = _obj({
    "claim_id": {"type": "string", "pattern": "^[A-Z][0-9]{1,3}$"},
    "claim_text": STR, "evidence_status": {"enum": EVIDENCE_STATUS}, "evidence_kind": {"enum": EVIDENCE_KINDS},
    "dimensions": {"type": "array", "items": {"enum": DIMENSIONS}, "minItems": 1},
    "dimension_rationale": STR, "attribution": STR, "as_of": DATE_OR_EMPTY,
    "citations": {"type": "array", "items": CITATION},
    "financial_period": STR,
    "calculation": {"anyOf": [{"type": "null"}, _obj({
        "formula": STR, "inputs": {"type": "array", "items": _obj({"name": {"type": "string", "pattern": "^[a-z_][a-z0-9_]*$"},
                                                                    "value": {"type": "number"}, "claim_id": STR})},
        "result": {"type": "number"}})]},
    "basis_claim_ids": IDS, "contradictions": STR,
    # schemas_v1 validation code reads claim_type; v3 keeps the key for compatibility
    "claim_type": {"enum": ["identity", "security_terms", "contract_provision", "financial", "traction", "market",
                            "competition", "team", "risk", "use_of_proceeds", "availability", "regulatory", "science",
                            "other"]}})

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
            "kind": {"enum": ["issued_outstanding", "authorized", "offered_minimum", "offered_maximum", "reserved_or_options"]},
            "share_class": STR, "value": {"type": "number"}, "as_of": DATE_OR_EMPTY,
            "basis": {"enum": ["audited_balance_sheet", "reviewed_balance_sheet", "form_c_capitalization_table",
                               "board_ratification_or_issuance", "offering_terms", "other"]},
            "claim_id": STR})},
        "convertible_instruments": {"type": "array", "items": _obj({
            "instrument": STR, "status": {"enum": ["existing", "planned"]}, "principal_usd": NUM_OR_NULL,
            "as_of": DATE_OR_EMPTY, "conversion_terms_disclosed": {"type": "boolean"}, "claim_ids": IDS, "note": STR})},
        "note": STR}),
    "cash_points": {"type": "array", "items": _obj({
        "amount_usd": {"type": "number"}, "as_of": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "assurance": {"enum": ["audited", "reviewed", "unaudited_issuer_statement"]}, "claim_id": STR})},
    "spending_points": {"type": "array", "items": _obj({
        "kind": {"enum": ["net_loss", "operating_expenses", "operating_cash_outflow", "issuer_stated_monthly_burn"]},
        "amount_usd": {"type": "number"},
        "period_start": DATE_OR_EMPTY, "period_end": {"type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
        "assurance": {"enum": ["audited", "reviewed", "unaudited_issuer_statement"]}, "claim_id": STR})},
    "financial_statements": _obj({"period_end": DATE_OR_EMPTY,
                                  "assurance": {"enum": ["audited", "reviewed", "self_certified", "unknown"]}, "claim_ids": IDS}),
    "fees": _obj({"investor_paid_fee_stated": {"type": "boolean"}, "investor_fee_claim_ids": IDS,
                  "issuer_paid_fee_claim_ids": IDS, "minimum_investment_usd": NUM_OR_NULL, "minimum_claim_id": STR}),
    "document_conflicts": {"type": "array", "items": _obj({"topic": STR, "claim_ids": IDS, "material": {"type": "boolean"},
                                                            "explanation": STR})},
})

SECTION = _obj({"assessment": STR, "claim_ids": IDS})
STAGE_B = _obj({
    "technical_and_efficacy": SECTION, "commercial_demand": SECTION, "regulatory_progress": SECTION, "team_execution": SECTION,
    "financing_and_runway": SECTION, "terms_and_investor_proceeds": SECTION, "competition_and_advantage": SECTION,
    "stage": {"enum": ["concept", "preclinical_or_prototype", "clinical_or_pilot", "early_commercial", "growth_commercial"]},
    "additional_claims": {"type": "array", "items": CLAIM}})
STAGE_C = _obj({
    "issues": {"type": "array", "items": _obj({
        "issue_type": {"enum": ["unsupported_conclusion", "contradictory_evidence", "optimistic_assumption", "missing_fact",
                                "dimension_misclassification", "generic_trigger_used_as_decisive", "overstatement"]},
        "target": STR, "explanation": STR, "claim_ids": IDS, "severity": {"enum": ["high", "medium", "low"]}})},
    "additional_claims": {"type": "array", "items": CLAIM}})

FACT = _obj({"claim_id": STR, "role": {"enum": ["supporting", "counter"]}, "generic_trigger": {"enum": GENERIC}})
FINDING = _obj({
    "rule_id": {"enum": RULE_IDS},
    "result": {"enum": ["adverse", "not_adverse", "unknown", "not_applicable"]},
    "scope": {"enum": ["economic_concern", "execution_blocker", "factual_gap", "none"]},
    "claims_independently_decisive": {"type": "boolean"},
    "facts": {"type": "array", "items": FACT},
    "interpretation_ko": STR, "counterevidence_ko": STR, "unresolved_ko": STR, "what_would_change_ko": STR})
PREF_FINDING = _obj({"pref_id": STR, "breached": {"enum": ["yes", "no", "unknown"]}, "claim_ids": IDS, "note_ko": STR})
THESIS = _obj({"question_id": {"enum": list(QUESTIONS)},
               "status": {"enum": ["supported", "unknown", "contradicted", "specific_reason_supported",
                                   "no_substantiated_advantage_identified"]},
               "answer_ko": STR, "claim_ids": IDS})
STAGE_D = _obj({
    "rule_findings": {"type": "array", "items": FINDING, "minItems": len(RULE_IDS), "maxItems": len(RULE_IDS)},
    "preference_findings": {"type": "array", "items": PREF_FINDING},
    "thesis": {"type": "array", "items": THESIS, "minItems": len(QUESTIONS), "maxItems": len(QUESTIONS)},
    "critique_responses": {"type": "array", "items": _obj({"issue_index": {"type": "integer"}, "accepted": {"type": "boolean"},
                                                            "response": STR})}})

STAGE_F = _obj({
    "company_ko": STR,                  # what the company does, attributed to the issuer
    "why_could_work_ko": STR,
    "unknowns_ko": {"type": "array", "items": STR, "maxItems": 6},
    "what_would_change_ko": {"type": "array", "items": STR, "minItems": 1, "maxItems": 5},
})

STAGES = {"A_extraction": STAGE_A, "B_analysis": STAGE_B, "C_critical_review": STAGE_C, "D_final": STAGE_D,
          "E_support_check": STAGE_E, "F_brief_ko": STAGE_F}
STAGE_ORDER = list(STAGES)
