# v2.2.1 final result: Hope-Neuron analysis 18 (development case)

- **Authorization.** The user's message on 2026-10-18 ("Go ahead and fix as you mentioned") replied to the proposed
  E–F completion. It is recorded in run 18's notes.
- **Run 18.** Child of 17 (lineage 18 → 17 → 16 → 15). Same pack `PACK-RCF-2114933-020-37299-893511c4af2b`
  (cutoff 2026-10-14T16:46:19Z). Policy `screening_policy_v1_3` `c150371d…` (PROPOSED). Classifier v3_1, validator
  0_3, pipeline 0_3.
- **Provenance.**
  - Reused: A (from run 15), B (run 16, B12 migrated to a K1 reference), C and D (run 17; D accepted under
    validator 0_3).
  - Live: E (valid) and F.
  - F was rejected by the schema (more unknowns and what-would-change items than the maxima of 6 and 5); with 0
    repairs authorized it is recorded as a presentation error.
  - The classification is computed by code from the validated A–E outputs.

## Result (provisional, proposed policy)

| Dimension | Result |
|---|---|
| Screening | **provisional_unresolved** (제안된 정책에 따른 잠정 분류: 미결). No decisive finding. |
| Evidence | insufficient for any screening decision under v1_3 |
| Economic thesis | incomplete. Q7: "no substantiated advantage identified" over SCHG (not "proven inferior"). Q4 financing need unknown. Q5 proceeds path withheld (K6). |
| Execution | availability unknown (Republic not reachable; no verified availability) |
| Budget | $12,000 annual / $1,200 issuer remaining. Investor fees not stated, so total cost cannot be verified (not zero, not exceeded). |

**Findings.**
- Not adverse: R-EV1, R-REG-1, R-TEAM-1.
- Not applicable: R-DEM-1 (pre-commercial).
- Unknown: R-TECH-1, R-FIN-1, R-TERMS-1, R-TERMS-2, R-TERMS-3.
- **R-FIN-1, both branches:**
  - (A) next-milestone costs and same-period spending are not stated, so the runway is withheld;
  - (B) no document states a default, insolvency or acceleration. The p.59 "not in default" representation is a dated
    issuer claim.
- **R-TERMS-1:** unresolved. The founder's 75,000,000 shares have no stated consideration or date; there are 175M
  unissued authorized shares; note 2 carries a $50k add-on.

**Stage E** (model judgment, not independent verification): 22 claims checked; 13 supported, 3 supported with minor
caveats, 6 partially supported (minor); 0 rejected. There were no adverse candidates, so no predicate reviews were
needed.

**Brief.** `reports/briefs/v2_2/brief_RCF-2114933-020-37299_analysis18.md`.
- Without F, the brief renderer fills sections 2 and 5 from the validated D-stage thesis answers and rule findings,
  labelled as such.
- Section 1 points to the attributed claim list.
- Brief renderer change: Korean scope labels and the fallback. No model text is generated.

## Before/after

| Version | Result |
|---|---|
| v2.1 (analysis 10) | fails_current_screen (BT4, PC1, PC3) |
| v2.2 (mechanical transfer to v1_2) | provisional_reject (R-FIN-1) |
| v2.2.1 deterministic (analysis 10's findings, v1_3/v3_1) | provisional_unresolved |
| v2.2.1 live (17 failed at D; 18 completed E–F) | **provisional_unresolved**; no rule assessed adverse by the new D stage |

**Attribution, as far as supported.**
- **Implementation (the predicate gate):** removed the earlier decisive status.
- **New interpretation by the model under prompt v3_2:** assessed no rule as adverse. One run cannot separate the
  prompt's effect from model variability.

The rule wording was preserved. Authored predicate elements and implementation gates were added. Whether this
operationalization fully matches the original intent remains subject to review.

**This is not favorable evidence.** The adverse facts all remain visible, and nothing establishes an advantage over
SCHG.

## Calls and cost (this continuation)

| Run | Calls | List-price estimate |
|---|---|---|
| 17 | C, D, D-repair (3 calls) | $2.82 |
| 18 | E, F (2 calls) | $0.75 |
| **Total** | **5 calls: 4 normal, 1 repair**, within the authorized 4 + 1 | **$3.57** |

These are CLI list-price estimates. The amount actually billed through the subscription is **unknown**.

## State

- Policies v1, v1_2 and v1_3 are all inactive.
- P-1 and P-2 are disabled.
- 0 activations, 0 approvals, 0 ledger entries.
- Runs 15–17 are preserved unchanged.

Hope-Neuron remains a development case. Evaluation on other cases would be a separate, later task.
