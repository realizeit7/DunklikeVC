# v2.2.1: rule satisfaction and reliable calculations

**Branch:** `v2.2.1-rule-satisfaction`, created from `v2.2-screening-thesis` at `eba492c`, which is itself based on
`v2.1-republic-briefs` (verified with `git merge-base`). The repository has no AGENTS.md.

**Live model calls in this revision: none.** No continuation was authorized; see §5.

## 1. Five checks, kept distinct

| # | Check | Implemented by | Can it alone make a finding decisive? |
|---|---|---|---|
| 1 | The citation exists and matches its locator | `claims_checks` (verbatim; v3 whitespace-only rule 3_1) | No |
| 2 | The source supports the factual claim | stage E support check (model judgment) and manual checks | No |
| 3 | The fact is relevant and applicable (issuer, security, date; generic triggers G1–G8; allowed evidence kind) | `assess_v3.evaluate_findings` | No |
| 4 | **The facts satisfy the rule's authored predicate** | new: policy v1_3 `predicates`, `assess_v3.predicate_overall`, stage-E `predicate_reviews` | No |
| 5 | The rule permits independent rejection | policy flag | No |

A finding is decisive only when 1–5 all hold, the code-computed predicate is `met`, the review agrees, no material
objection is unresolved, and the finding does not rest only on generic triggers.

## 2. Rule-predicate mapping (independent-rejection rules)

- **Policy:** `screening_policy_v1_3`, PROPOSED, sha256 `c150371d0990b86766ce097afd62ac1a982b294996f3de9ef5c09e8fac635e0c`.
- **Rule texts:** byte-identical to v1_2. v1_2 itself (`112318fa…fb32`) is untouched.
- **What v1_3 adds:**
  - authored elements for each independent-rejection rule;
  - `evidence_must_mention` floors on factual elements;
  - `compatible_classifiers: [assessment_classifier_v3_1]`.

| Rule | Exact adverse definition (v1_2 = v1_3) | Authored elements (logic) | Deterministic parts |
|---|---|---|---|
| **R-FIN-1** | "Same-period figures show the company cannot reach its next milestone even with the maximum raise, or there is a documented default, insolvency or acceleration. Low cash in an older statement (G2) and going-concern language (G3) are not adverse on their own." | **any_branch.** *milestone_shortfall*: FIN1-A1 next milestone and its funding requirement stated; FIN1-A2 same-period cash and spending exist; FIN1-A3 cash plus maximum raise does not cover the requirement. *documented_distress*: FIN1-B1 a document states an existing default, insolvency or acceleration (not a missing maturity date; not a planned instrument). | FIN1-A2 is established only if the software runway calculation was not withheld. FIN1-B1 needs distress wording in an evidence fact (floor). |
| R-TECH-1 | "A documented negative result, a clinical hold, or a documented inability of the product to work as described." | all: TECH1-1 (factual, floor), TECH1-2 product relevance | floor on TECH1-1 |
| R-DEM-1 | "Documented loss of key customers, documented collapsing revenue, or a documented payer refusal material to the plan." Applies to commercial-stage companies only. | all: DEM1-1 commercial stage; DEM1-2 event (floor); DEM1-3 material | floor on DEM1-2 |
| R-REG-1 | "A documented regulatory action against the company or product (clinical hold, refusal, warning letter, consent order) that is material to the plan." | all: REG1-1 (floor), REG1-2 against company or product, REG1-3 material | floor on REG1-1 |
| R-TEAM-1 | "A documented sanction, bad-actor event or material misstatement by a key person, material to this investment." | all: TEAM1-1 (floor), TEAM1-2 current key person, TEAM1-3 material | floor on TEAM1-1 |
| R-TERMS-1 | "Such a term is documented in the contract or Form C and is material; the generic features G4–G8 do not qualify." | all: TERMS1-1 stated; TERMS1-2 transfers value away from this holder; TERMS1-3 worse than the ordinary form, not G4–G8; TERMS1-4 material | — |

**The floors are necessary, not sufficient.** In the Hope-Neuron pack, the words "insolvency", "bankruptcy" and
"acceleration" appear only in contract boilerplate (pp.57–59: enforceability exceptions; the company's
representation that it is *not* in violation or default) and on p.28 ("accelerating the path to commercialization").
Such text would pass a keyword floor. The element judgment, the review and the source check remain required, and
they are recorded as model judgment or as the assistant's comparison, never as independent verification.

**The predicate analysis 10 originally applied.**
- BT4 was judged under prompt v2's criterion text "the dated cash position, liabilities and burn; future capital
  needs", which has **no adverse threshold**.
- The predicate that can be inferred from its reason is roughly "financial condition is weak and capital needs exceed
  current resources". That is neither of R-FIN-1's two branches.
- The v2.2 handoff discussed "default"; that was one branch, not the whole rule. Both branches are mapped above.

## 3. Hope-Neuron: deterministic before/after

- **Pack:** `PACK-RCF-2114933-020-37299-893511c4af2b`, the same frozen pack. No new evidence was added.
- **Output:** `reports/v2_2_1_analysis10_deterministic_reclassification.json` (classifier v3_1, policy v1_3, no model
  call).

| Original finding (analysis 10) | Original inferred predicate | Supporting facts | Predicate assessment (code; analysis 10 has no element assessments) | Objection (assistant source check; not independent) | New decisive status | Reason |
|---|---|---|---|---|---|---|
| BT4 → **R-FIN-1** | "weak finances; needs exceed resources" (no threshold) | A13 (XML FY2025: revenue $0, net loss $56,126, cash $19,213; G1, G2), A15 (audited liabilities $268,348 incl. $199,875 founder payable, no interest or maturity, pp.36, 45), A18 (issuer going-concern risk factor, p.12; G3), A21 (notes 4.19%/4.13%, maturities 2030/2031), A22 (MOU for a $50k note, not issued, p.34) | **unresolved.** FIN1-A1: no milestone funding requirement in the findings. FIN1-A2: **unknown, evaluated by code**: runway withheld, since only FY2025 spending exists against cash dated 2026-06-18. FIN1-A3: unknown. FIN1-B1: unknown. | No page states a default, insolvency or acceleration. A missing maturity is not a default, and not proof that no default exists. A22 is planned, not a liability. The going-concern wording is the **issuer's**: the audit report (pp.43–44) has only standard responsibility wording, no going-concern paragraph, and Note 4 is prepared on a going-concern basis. | **adverse_contributing** (was decisive in v2.1 and mechanically in v2.2) | predicate unresolved: required elements unknown |
| PC1 → R-TERMS-1 | "obstacles to this security producing cash" | A7 (G8), A9 (G6), A31 (G6), A32 (G4), A8 (G5), A21 | not reached | Generic Reg CF features. A9's p.24 citation concerns Reg A, not transfer. | **adverse_contributing** (unchanged since v2.2) | no company-specific fact passed the support check |
| PC3 → R-TERMS-3 | "rights limits and dilution sources" | A7, A8, A19, A31, A11, B2 | not applicable (the rule cannot reject alone) | Note conversion prices are **missing** (not adverse). The Form C (pp.32–33, "only upon a liquidity event"; "cannot take place before a Reg A or similar") **conflicts** with audited Note 5 (p.52: change of control, **private replacement financing**, recapitalization). | **adverse_contributing** (unchanged) | R-TERMS-3 cannot independently reject |

**Provisional classification.**
- Under the proposed v1_3 with classifier v3_1: **`provisional_unresolved`** (research-only).
- v2.1 said `fails_current_screen`, and v2.2's mechanical v1_2 transfer said `provisional_reject` on R-FIN-1.
- The change comes from the **implementation**: the predicate gate. The rule meaning and the facts are unchanged.
- **This is not a favorable thesis.** Every adverse fact stays visible as a contributing concern, and the economic
  thesis remains incomplete:
  - no substantiated advantage over SCHG;
  - financing needs unknown;
  - investor-proceeds pathway withheld.

**Preserved distinctions.**
- Audited cash $19,213 (2025-12-31) vs issuer-reported, unaudited $160,487.20 (2026-06-18, p.35).
- Audited 1 share (2025-12-31, p.45) vs 75,000,001 after the 2026-06-25 ratification (p.35). K1 = $75,000,001
  (arithmetic).
- K4 (fully diluted) withheld: the existing notes have no conversion price. The planned note is excluded.
- The mouse study is TECH (preclinical, issuer-reported, no sample size), not DEMAND. The IRB trial is planned only.

## 4. Typed calculations and legacy compatibility

- `typed_calc.py`: allowlisted kinds `implied_equity`, `post_money`, `ownership_percent`, `runway_months` and `ref`.
  - Decimal arithmetic. Values must appear in the cited claim.
  - Units, base security class and period alignment are checked. Planned instruments are refused as issued shares.
  - **No model expression is ever evaluated.**
- Legacy (v3_0) outputs are immutable. `migrate_cached_stage` converts a cached stage explicitly:
  - `calculation: null` becomes `calc_request: null`;
  - a legacy formula is accepted only if, after stripping a display label or whitespace, it reproduces a software
    calculation exactly (formula, inputs and result). The original and normalized text are logged.
  - Anything else is rejected, not guessed.
  - Dry run on the real outputs: run 15 stage A migrates with no changes; run 16 B12 `"K1: price_per_share *
    issued_shares"` maps to `{kind: ref, k_ref: K1}`. Both validate under schema v3_1.

## 5. Continuation: ready, NOT executed (needs your explicit authorization)

- Registered (DB record only): `analyst_v3_1`
  - prompt `analyst_prompt_v3_2` (sha256 `a1cdef4e…`);
  - schema `analysis_schema_v3_1`;
  - policy `screening_policy_v1_3`;
  - repair cap 1 for the whole continuation.
- The v3_1 draft prompt from v2.2 is **not** used.
- Lineage: runs 15 → 16 → child.
  - Stages A (run 15, repair1) and B (run 16) are reused through the logged v3_0→v3_1 migration and re-validated.
  - Live calls: C, D, E, F (4 calls, plus at most 1 repair).
  - The lineage repair count (1) stays recorded and cannot reset; the child may make only the repairs you authorize.

```
cd personal_vc_research
python -m prospective resume-v3 16 --version analyst_v3_1 --extra-repairs 1 \
  --authorized-by-user "I authorize one bounded Hope-Neuron continuation (stages C-F, max 1 repair) on the frozen pack" \
  --note "v2.2.1 continuation"
python -m prospective brief-v3 <new_analysis_id>
```

- **Cost:** the earlier $2–4 figure was a CLI list-price *estimate*. The amount actually billed through your
  subscription is not known to this system.
- **Stop rule:** if a stage fails after the one authorized repair, the run stops and records the blocker.

## 6. Approval isolation

`approve()` requires all of the following:
- the legacy v1 acknowledgment (never given);
- for v3 analyses, `policy.approval_eligible`: an active policy, the same hash as the analysis, and a compatible
  classifier.

v1_2 lists no compatible classifiers, so activating it would never make v2.2 results eligible. `policy-activate`
refuses to run without an interactive terminal and a hand-typed hash prefix. `actor='user'` is recorded as
provenance only, and no analysis module calls `activate`.

## 7. Tests

- `tests/prospective/test_v221.py`: 16 cases covering the 14 required behaviours.
- The full suite was run once after the changes; the result is in the handoff.
- These tests check logic. They do not establish that any interpretation is semantically correct, or anything about
  investment performance.
