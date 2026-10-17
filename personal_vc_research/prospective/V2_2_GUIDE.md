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
