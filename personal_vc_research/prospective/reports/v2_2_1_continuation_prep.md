# v2.2.1 continuation: verification, cached-stage validation and predicate review (prep)

**Status: no live model call has been made.** The continuation in §5 waits for your explicit authorization. This
review is by the same assistant and is not independent validation.

## 1. State verified locally (2026-10-17)

| Item | Expected | Found |
|---|---|---|
| Branch / commit | `v2.2.1-rule-satisfaction` / `f2cff8d` | same; clean worktree before this prep |
| Activations / acknowledgments / approvals / ledger / decisions | 0 / 0 / 0 / 0 / 0 | same |
| `screening_policy_v1_3` sha256 | `c150371d…635e0c` | `c150371d0990b86766ce097afd62ac1a982b294996f3de9ef5c09e8fac635e0c` (proposed) |
| `screening_policy_v1_2` sha256 | `112318fa…fb32` | unchanged |
| `analyst_v3_1` | prompt v3_2, schema v3_1, policy v1_3, repair cap 1 | same; registered 2026-10-17T19:22:21Z, dev case Hope-Neuron |
| Prompt `analyst_prompt_v3_2` | — | sha256 `a1cdef4e…5a61b597` |
| Schema `analysis_schema_v3_1` (`schemas_v3_1.py`) | — | sha256 `ff0cff49…1e7d1dd6` |
| Classifier | `assessment_classifier_v3_1` | same |
| Pack | `PACK-RCF-2114933-020-37299-893511c4af2b` | sha256 `893511c4…2f11d28`, cutoff 2026-10-14T16:46:19Z; runs 15 and 16 use the same pack |

No material discrepancy was found.

**One prep-only code change** (pipeline `analysis_v3_pipeline_0_3`):
- a read-only `plan_resume()`, which `resume()` now uses;
- explicit provenance of reused stages.

Validation and classification are unchanged. It does not invalidate the cached stages or the planned run. The
directly relevant tests pass (37: test_v22 and test_v221). The full suite was not rerun; the documented result is
166 passed at `f2cff8d`.

## 2. Cached-stage reuse (read-only plan, same code path as the live command)

**Reused stages**
- **A_extraction:** generated in run 15 (repair 1) by claude-sonnet-5-5 under prompt v3 / schema v3_0. It is
  byte-identical to `A_extraction.reused.json` in run 16 (sha256 `381c4d37…`). It migrates to v3_1 with no changes
  and validates.
- **B_analysis:** generated in run 16 by claude-sonnet-5-5 under prompt v3 / schema v3_0. It validates after the
  logged migration of **B12**:
  - original: `"K1: price_per_share * issued_shares"`;
  - normalized: `price_per_share * issued_shares` (label removed);
  - mapped to `{kind: ref, k_ref: K1}`, because the formula, inputs (A03 price $1, A13 75,000,001 shares) and result
    ($75,000,001) are identical to software calculation K1.
  - K1 is recomputed under calculator v1_3 as `computed` 75,000,001. The other values: K2 75,075,001, K3 80,000,001;
    K4, K5 and K6 withheld.

**Remaining stages (live):** C_critical_review, D_final, E_support_check, F_brief_ko.
- C needs A and B, which are supplied.
- D needs A–C plus the K calculations.
- E needs D.
- F needs the computed classification.

Nothing else is missing.

**Provenance.** The child run will record `reused_stage_provenance`: origin run, original prompt, schema and model,
with the note "conclusions in this stage are NOT new-model outputs". All policy-dependent findings (D, E) and the
classification are produced fresh under v1_3 / classifier v3_1.

**Caveat.** Passing schema validation shows only that A and B are well-formed and correctly cited. It does not show
their conclusions are true.

## 3. Change-attribution correction (replaces the wording in earlier v2.2.1 reports, which are kept as written)

Earlier text said the interpretation was "unchanged" because the rule texts are byte-identical. Correct wording:

> The rule wording was preserved. Authored predicate elements and implementation gates were added. Whether this
> operationalization fully matches the original intent remains subject to review.

## 4. Adverse definitions mapped to predicate elements, with flags

Flag key: **NEW-T** new threshold · **NAR** narrows · **BRD** broadens · **UNRES** material interpretation left
open · **OK** close paraphrase.

| Rule | Adverse definition (exact) | Element | Flag | Note |
|---|---|---|---|---|
| R-FIN-1 | "Same-period figures show the company cannot reach its next milestone even with the maximum raise, or there is a documented default, insolvency or acceleration. Low cash in an older statement (G2) and going-concern language (G3) are not adverse on their own." | FIN1-A1: next milestone and funding requirement *stated in the documents* | **NAR** | The definition does not say the requirement must be stated by the issuer; a well-supported analyst estimate is excluded |
| | | FIN1-A2: same-period cash and spending (deterministic; calculator: spending period ending ≤92 days before the cash date, ≥28 days long) | **NEW-T** | "same-period" is operationalized as a 92-day window |
| | | FIN1-A3: cash + maximum raise, *net of stated fees*, does not cover the requirement | OK / **UNRES** | Fee netting is a reasonable addition. Whether burn until the milestone counts in the "requirement" is open. |
| | | FIN1-B1: a document states an existing default, insolvency or acceleration; plus a keyword floor | **NAR** | The floor can miss paraphrases (e.g. "failed to make a scheduled payment"), so false negatives are possible. Boilerplate also passes it (pp.57–59), so the floor is not sufficient. |
| | | `not_sufficient_alone` adds "obligation without stated maturity" and "planned financing" | **BRD** (of exclusions) | Interpretive additions beyond the G2/G3 sentence |
| R-TECH-1 | "A documented negative result, a clinical hold, or a documented inability of the product to work as described." | TECH1-1 (floor) | **NAR** | The keyword floor can miss paraphrased negative results |
| | | TECH1-2: concerns the product the investment depends on | **NAR** | A relevance condition not in the text |
| R-DEM-1 | "Documented loss of key customers, documented collapsing revenue, or a documented payer refusal material to the plan." | DEM1-1: commercial stage | OK | Taken from the rule's applicability line |
| | | DEM1-2 (floor) | **UNRES** | The floor terms (e.g. "declin", "decreas") are broad and weak |
| | | DEM1-3: material | OK | |
| R-REG-1 | "A documented regulatory action against the company or product (clinical hold, refusal, warning letter, consent order) that is material to the plan." | REG1-1 (floor), REG1-2, REG1-3 | OK / **NAR** | The floor can miss paraphrases |
| R-TEAM-1 | "A documented sanction, bad-actor event or material misstatement by a key person, material to this investment." | TEAM1-2: *current* key person | **NAR** | "current" is added |
| R-TERMS-1 | "Such a term is documented in the contract or Form C and is material; the generic features G4–G8 do not qualify." | TERMS1-3: worse than the *ordinary Reg CF form* | **UNRES** | The baseline "ordinary form" is not defined anywhere in the policy |
| all six | (aggregation text: "support-checked") | Classifier gate: stage-E review must agree, with no material unresolved objection | **NAR** (implementation) | Stricter than the policy text. Disclosed; it can only reduce decisiveness |

No flag is serious enough to require a policy edit before the run. The NAR, UNRES and NEW-T items are listed for
your policy review. The policy was **not** edited.

## 5. Continuation: requires your separate explicit authorization

Limits:
- one child workflow linked to runs 15 → 16;
- stages C, D, E, F: at most 4 normal calls plus 1 repair in total;
- existing provider and spending controls (`max_budget_usd_per_stage` 5.0);
- no retry wrapper.

If a call returns no structured output, that counts as an invalid output and may use the single repair. After that,
the run stops.

```
cd personal_vc_research
python -m prospective resume-v3 16 --version analyst_v3_1 --extra-repairs 1 --authorized-by-user "<your own authorization text>"
python -m prospective brief-v3 <new_analysis_id>
```

The earlier $2–4 is a list-price estimate. The amount actually billed through your subscription is unknown to this
system.
