# v2.2.1 continuation: result (analysis 17)

- **Authorization.** The user's message on 2026-10-18 ("Please go ahead initial run") replied to the request for one
  bounded continuation (analyst_v3_1; stages C–F; at most 4 normal calls plus 1 repair; policies inactive). It is
  recorded verbatim in run 17's notes.
- **Run.** Analysis **17** is a child of 16 (lineage 17 → 16 → 15). Same pack `PACK-RCF-2114933-020-37299-893511c4af2b`,
  cutoff 2026-10-14T16:46:19Z. Policy `screening_policy_v1_3` (`c150371d…`, PROPOSED). Classifier v3_1. Pipeline 0_3.
- **Review.** The review below is by the same assistant and is not independent validation.

## 1. What ran, and the stop

| Stage | Source | Calls | Outcome |
|---|---|---|---|
| A_extraction | reused from run 15 (prompt v3 / schema v3_0, migrated with no changes) | 0 | valid |
| B_analysis | reused from run 16 (B12 → K1 reference, logged migration) | 0 | valid |
| C_critical_review | live | 1 normal (153 s, est. $0.82) | **valid** |
| D_final | live | 1 normal (252 s, est. $1.07) | **no output.** The CLI reported `error_max_structured_output_retries` after 6 internal turns. |
| D_final | live, repair 1 (the single allowed repair) | 1 repair (160 s, est. $0.93) | **invalid, 1 error**: `R-REG-1.unresolved_ko: too much English text (6 Latin vs 10 Hangul)`. The text was `'IRB 제출, FDA 상호작용, 기기 분류.'` |
| E_support_check, F_brief_ko | — | 0 | **not run.** The stop rule applied: a stage failed after the repair allowance |

- **Totals:** 3 model calls (2 normal, 1 repair), about 9.4 minutes, about **$2.82 CLI list-price estimate**. The amount
  actually billed through the subscription is **unknown**.
- **Recorded result:** analysis 17 is `analysis_failed`. The original run records (15, 16) are unchanged.
- **No retry wrapper and no further calls.**

## 2. The blocker and the fix (made after the run, versioned)

**Root cause.** Validator `v2_validator_0_2` counted the standard acronyms IRB and FDA as English text in a short
Korean phrase. That is a false positive.

**Fix.** `v2_validator_0_3`:
- all-caps acronyms of 2–6 letters no longer count toward the Latin ratio;
- the 8-or-more-English-word passage rule is unchanged;
- test added; the relevant tests pass (61).

**Effect of the fix.**
- It does not change the cached A and B stages.
- **Re-validated without model calls:** stored C passes, and stored D (repair 1) passes under validator 0_3 with
  0 errors.
- Analysis 17's recorded failure stands as the historical outcome under the validator it ran with.

The second contributor was provider-side: the first stage-D call produced no structured output (large v3_1 schema),
which used up the normal D call.

## 3. Informational classification of the validated stored stages (A–D only)

`reports/v2_2_1_analysis17_partial_classification.json` holds the classifier v3_1 result on stages A, B, C and
D-repair1. **It is not a completed workflow.** Stage E (the support check and predicate review) and stage F (Korean
prose) never ran, and no brief was generated.

**Stage D's model findings:** none adverse.

| Rule | Model result | Predicate (code) |
|---|---|---|
| R-EV1 | not adverse | contract (Exhibit B) and FY2025 audited statements are readable. Charter, note instruments and interim statements are absent. |
| R-TECH-1 | unknown | issuer-reported mouse study only; no documented negative result or hold |
| R-DEM-1 | not applicable | pre-commercial stage |
| R-REG-1 | not adverse | no documented regulatory action; IRB trial planned only |
| R-TEAM-1 | not adverse | no documented sanction. The no-disqualification statement is an issuer certification. |
| R-FIN-1 | unknown | **unresolved**: FIN1-A1, A2 and A3 unknown; FIN1-B1 not assessed by the model, so code treats it as unknown |
| R-TERMS-1 | unknown | the founder's 75,000,000-share issuance (consideration and date undisclosed), 175M unissued authorized shares and the $50k add-on on note 2 leave "uncapped insider issuance" neither confirmed nor excluded |
| R-TERMS-2, R-TERMS-3 | unknown | arithmetic K1 = $75,000,001 (not a valuation opinion). Dilution sources identified; missing conversion terms = unknown. |

**Resulting classification:** `provisional_unresolved`
- no decisive finding;
- evidence insufficient;
- economic thesis incomplete (Q7: "no substantiated advantage identified"; Q4 financing need unknown; Q5 proceeds
  path withheld, K6);
- availability unknown;
- total cost unverifiable (investor fees not stated).

**R-FIN-1 review of both branches** (source re-check):
- **Branch A.** Milestones are named: more mouse work, next-generation devices, an IRB human trial (p.27). No cost or
  funding requirement is attached. Only FY2025 spending exists against issuer-reported cash on 2026-06-18, so runway
  is withheld (K5). FIN1-A1 to A3 cannot be established.
- **Branch B.** No page states a default, insolvency or acceleration. These words appear only in contract
  boilerplate (pp.57–59). On p.59 the company represents that it is not in default. That is a **dated issuer
  statement**, not independent proof. Not established.
- The founder payable (no maturity), the planned $50k note (MOU), going-concern risk-factor wording (issuer, p.12; the
  audit report has no going-concern paragraph) and boilerplate were not used as substitutes. The model's D output
  treats them the same way.

## 4. Before/after

| Version | Basis | Result |
|---|---|---|
| v2.1 (analysis 10) | criteria BT4, PC1, PC3 | fails_current_screen |
| v2.2 (deterministic transfer of analysis 10 to v1_2) | fact checks only | provisional_reject (R-FIN-1) |
| v2.2.1 (deterministic, classifier v3_1, v1_3) | predicate gate on analysis 10's findings | provisional_unresolved |
| **v2.2.1 live, analysis 17** | fresh C and D under v1_3 | **analysis_failed** at run time (validator false positive after a provider-side empty D output). On the stored stages under validator 0_3: provisional_unresolved, informational only. |

**Attribution, as far as supported.**
- v2.1 → v2.2: policy logic (generic triggers).
- v2.2 → v2.2.1: implementation (the predicate gate). The rule wording was preserved; authored predicate elements
  and implementation gates were added. Whether this operationalization fully matches the original intent remains
  subject to review.
- The live D output reaching no adverse finding on any rule is the **model's new interpretation** under prompt v3_2.
  How much of that is the prompt and how much is model variability cannot be separated from one run.

**A revised unresolved classification is not favorable evidence.**

## 5. Open decision: completing E and F needs a NEW authorization

Planned (read-only check):
- new child run from 17, reusing A, B, C and D (D validated under validator 0_3);
- live E and F only: **2 normal calls, 0 repairs**;
- lineage repair count stays at 2.

```
cd personal_vc_research
python -m prospective resume-v3 17 --version analyst_v3_1 --extra-repairs 0 --authorized-by-user "<your own authorization>"
python -m prospective brief-v3 <new_analysis_id>
```

In earlier runs the CLI's list-price estimates were about $0.30–0.46 for stage E and about $0.11–0.12 for stage F. That is an estimate, not a bill.
