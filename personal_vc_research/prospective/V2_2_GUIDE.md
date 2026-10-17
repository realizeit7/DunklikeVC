# v2.2 — Screening logic and investment-thesis review

**What it adds**
- A rule audit: `reports/screening_rule_audit_v2_2.md`.
- A **proposed, inactive** policy, `policies/screening_policy_v1_2_PROPOSED.yaml`. Its diff and Korean checklist are
  in `policies/screening_policy_v1_2_CHANGES.md`.
- Analyst v3:
  - prompt `analyst_prompt_v3`, schema `analysis_schema_v3_0`, pipeline `analysis_v3`, classifier `assess_v3`;
  - calculator v1_3: share-count history, existing vs planned notes, a runway withheld on stale spending, and an
    investor-proceeds scenario withheld when inputs are missing;
  - brief `brief_v3`, written to `reports/briefs/v2_2/`.
- Migration 4.

**Commands**

```
python -m prospective policy-status
python -m prospective analyst-register-v3 <version> --description "..." --dev-offering <id> --repair-rounds 1 --max-total-repairs 1
python -m prospective analyze-v3 <offering> --version <version> --pack <pack_id>
python -m prospective resume-v3 <analysis_id>      # continue the same workflow; repairs already used carry over
python -m prospective recalc-v3 <analysis_id>      # current calculator, new rows
python -m prospective brief-v3 <analysis_id>
python -m prospective policy-activate screening_policy_v1_2 --sha256 <hash> --statement "..." --i-am-the-user   # USER ONLY
```

**Rules of the road**
- Code derives every screening result from validated rule findings.
- A finding is decisive only when it meets three conditions:
  - its rule allows independent rejection;
  - it has a company-specific supporting fact that is not a generic trigger and is of an allowed evidence kind;
  - that fact passed the support check.
- Generic early-stage facts (G1–G8) never decide alone, but they stay visible as contributing concerns.
- Results stay `provisional_*`, and the brief says "제안된 정책에 따른 잠정 분류", until the user activates the exact
  policy hash.
- `ledger.approve` refuses non-active policies and analyses screened under them.
- Citation rule 3_1 (v3 only): a whitespace-only difference in a quote is accepted and recorded. v1 and v2 citation
  validation is unchanged.

**Known limitation.** The code cannot check that a valid, specific, support-checked fact actually meets a rule's
adverse definition; that remains the model's interpretation. See `reports/v2_2_hope_neuron_before_after.md`.

## v2.2.1: rule satisfaction and typed calculations

**Policy and classifier**
- Proposed policy `screening_policy_v1_3`: the same rule texts as v1_2, plus authored predicates and compatible
  classifiers.
- Classifier `assessment_classifier_v3_1`. A finding is decisive only if all of the following hold:
  - the authored predicate is `met`, as computed by code from the element assessments, with deterministic elements
    evaluated by code;
  - the stage-E `predicate_reviews` agree;
  - no material review objection is unresolved.
- Under a policy without predicates (v1_2), nothing is decisive.

**Pipeline**
- Analyst `analyst_v3_1`: prompt v3_2, schema v3_1. Free-form formulas are replaced by typed `calc_request` (see
  `typed_calc.py`); no model text is ever evaluated.
- `resume-v3 <id> --version analyst_v3_1 --extra-repairs N --authorized-by-user "..."` creates a child run.
  - Lineage repairs stay counted, and the child gets only the repairs that were explicitly authorized.
  - Cached v3_0 stages are migrated explicitly by `migrate_cached_stage` (logged; numbers are never repaired) and
    then re-validated.

**Approvals**
- `policy.approval_eligible`: the policy must be active, the analysis must be assessed under the same hash, and its
  classifier must be compatible.
- `policy-activate` needs an interactive terminal and a hash prefix typed by hand.
- See `reports/v2_2_1_rule_satisfaction_report.md`.
