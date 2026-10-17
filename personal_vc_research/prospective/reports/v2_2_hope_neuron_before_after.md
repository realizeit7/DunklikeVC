# Hope-Neuron: before/after (v2.2)

**Hope-Neuron is a development case.** Nothing here is evidence of predictive or selection skill. No version is
promoted on the basis of this case.

All runs use the same frozen pack: `PACK-RCF-2114933-020-37299-893511c4af2b` (cutoff 2026-10-14T16:46:19Z, 67 pages,
hash-checked on every load). No new evidence was collected and nothing was added to the pack.

## Runs

| Run | What | Versions | Result |
|---|---|---|---|
| 10 (v2.1, kept unchanged) | full v2 workflow | analyst_v2_0, prompt v2 (`eaf95211…`), proposed policy v1_1 | `fails_current_screen`; decisive BT4, PC1, PC3 |
| **Deterministic comparison** (no model call) | analysis 10's stored findings and stage-E verdicts re-classified by `assess_v3` (v3_0_1) under **screening_policy_v1_2** (`112318fa…fb32`, PROPOSED) | `compare_v22.py`; output `reports/v2_2_analysis10_deterministic_comparison.json` | `provisional_reject`, decisive **R-FIN-1 only**; see the compatibility caveat below |
| 15 (live) | v3 workflow, stage A | analyst_v3_0, prompt v3 (`e47b3f09…`), schema v3_0, calculator v1_2, whole-run repair cap 1 | **analysis_failed in stage A.** 45 errors, one repair (cap used), 1 error left: a whitespace-only quote difference on p.45 (`CommonStock` vs `Common Stock`) |
| 16 (live, resume of 15) | stage A reused (it validates under citation rule 3_1, recorded as 1 whitespace-insensitive match); stages B–F called once, no repairs left | pipeline 0_2 | **analysis_failed in stage B.** Claim B12's formula `"K1: price_per_share * issued_shares"` is not an expression (label prefix). The arithmetic itself is correct. No repair budget left. |

**Execution blocker (precise).** The bounded live scope is "one full workflow plus at most one repair". It was used
up before stage B validated, so no v3 rule findings, thesis answers or v3 brief exist for Hope-Neuron. The root cause
is a prompt gap: the model restated a code calculation as its own calculation claim. This is fixed in
`analyst_prompt_v3_1.md`, which is **not registered or used**. Completing the workflow needs your authorization for
one more bounded continuation: stage B again plus C–F, with repair cap 1, at an estimated $2–4 CLI list-price
equivalent.

## Decisive reasons: removed, retained, changed

| Analysis 10 reason | Maps to (v1_2) | Deterministic result | Why | What the sources actually establish (checked by the assistant; not independent) |
|---|---|---|---|---|
| **PC1** security cash path | R-TERMS-1 (only terms worse than the ordinary form) | **Removed as decisive** → `adverse_contributing` | A7 (proxy, G8), A9 (transfer limit, G6), A31 (custodian, G6), A32 (Reg A with "no assurance", G4) and A8 (no anti-dilution, G5) are generic. A21 (notes) is company-specific but only partially supported. | All are ordinary Reg CF common-stock features (pp.10, 23–24). A9's second citation (p.24) is about Reg A, not transfer, so a verbatim quote did not support its claim. |
| **PC3** rights and dilution | R-TERMS-3 (cannot reject on its own) | **Removed as decisive** → `adverse_contributing` | The rule identifies dilution sources and does not decide | The two notes ($60k 2025-07-22; $150k 2026-06-12) have **undisclosed conversion prices**: missing, not adverse. The $50k MOU note is **planned, not issued** (p.34). Audited Note 5 (p.52) lists private replacement financing as a conversion trigger, which **conflicts** with the Form C's "only on a Reg A or similar event" (pp.32–33). |
| **BT4** financial condition | R-FIN-1 | **Retained mechanically** (A15, A22 are non-generic and support-checked) | The code can verify that facts are valid, specific and support-checked. It cannot verify that they meet R-FIN-1's adverse definition. The model's "adverse" was judged under the old BT4 text. | Audited 2025-12-31: cash $19,213 against liabilities $268,348, including $199,875 owed to the founder with **no stated interest or maturity** (pp.36, 45). This is not a documented default. A22 is a *planned* $50k financing. Issuer-reported cash was $160,487 on 2026-06-18 (unaudited), and there is no same-period spending. The going-concern language is the **issuer's risk factor** (p.12). The audit report (pp.43–44) has only the standard responsibilities wording and **no going-concern paragraph**, and Note 4 is prepared on a going-concern basis. **Assistant reading:** the cited facts do not show that the company cannot reach its next milestone even at the maximum raise, so R-FIN-1's adverse definition does not appear to be met. A fresh v3 interpretation would be needed to settle this. |

**Provisional conclusion under the proposed v1_2.**
- **Mechanically:** `provisional_reject` on R-FIN-1 alone.
- **Taking the source checks into account:** that last decisive reason is doubtful, so the honest status is
  **"제안된 정책에 따른 잠정 분류: 미결에 가까움(R-FIN-1 해석 미확정)"**.
- **What would settle it:** a completed v3 run, or your own reading of pp.12, 34–36, 43–45 and 52.

Nothing here reverses into a favorable conclusion. The unfavorable facts all remain as contributing concerns.

## Attribution of changes (best effort, not causal proof)

| Change | Attributed to |
|---|---|
| PC1 and PC3 no longer decisive | **Policy logic**: the fact-level generic guard and R-TERMS-3's non-independence. Same stored findings, no model call. |
| Mouse study kept as TECH (`preclinical_efficacy`), never DEMAND | **Schema/validator**. Run 15's stage A classified A29–A31 as preclinical_efficacy/TECH and the IRB plan (A32) as REG. |
| Share-count history recognized (1 share audited at 2025-12-31 vs 75,000,001 after the 2026-06-25 ratification) | **New extraction** (stage A, v3) plus **calculator v1_3**. K1 = $75,000,001 is computed as arithmetic, not a valuation judgment. K2/K3 = $75,075,001 / $80,000,001. K4 (fully diluted) is **withheld**: the two existing notes have undisclosed terms. The planned note is listed but not counted. |
| Runway | **Calculator v1_2/v1_3**: withheld. The only spending figures are for FY2025, against cash dated 2026-06-18. The issuer's "six months of runway" stays an issuer claim. |
| Investor proceeds | Withheld. Exit value, conversion terms, senior claims, holding period and investor fees are not established. Nothing is assumed. |
| Audit vs going-concern conflict, note-trigger conflict | **New extraction** (stage A, v3, `document_conflicts`), confirmed on the pages. Not seen in analysis 10. |
| Stage-A error count (45 → 1 after repair) and the B12 formula label | **Model variability and prompt gaps**, not policy |

## Evidence classification (spec items)

- **Mouse experiment.** It is preclinical efficacy evidence, attributed to the issuer, with p=0.008 and no sample
  size, protocol or controls (pp.28–29). Human translation is unknown per the issuer. It is not demand evidence.
- **Demand evidence** (customers, clinics, payers, commitments, reimbursement, revenue) is **absent**: there is no
  revenue and no contracts. For a preclinical company this is `unknown`/stage-appropriate, not adverse.
- **Regulatory.** An IRB human trial is a *planned* step (p.27). No IRB approval, FDA interaction or authorization,
  trial initiation or human efficacy is documented, and no pathway is assumed.
- **Forecasts.** None were changed. v3 generates no forecasts, and the earlier forecasts and the compound flag on #4
  are untouched.

## Costs and versions

- **Live calls this task** (CLI estimates at list price, not billed; your subscription limits apply):
  - run 15: stage A $1.27 plus repair $0.74;
  - run 16: stage B $0.69;
  - **total $2.69**, about 9 minutes. The model reported was claude-sonnet-5-5.
- **Deterministic comparison:** $0.
- **Policy:** `screening_policy_v1_2` sha256 `112318fa43f87223a95973fd8638f4a0d03aeb035b9ddb615415fff2d5d8fb32`,
  state **proposed**.
- **Prompts:** v3 `e47b3f09…`, v3_1 `b80b5fce…` (unused).
- **Code versions:** classifier assessment_classifier_v3_0_1; calculator calculator_v1_3; citation rule
  citation_rule_3_1 (v3 only); pipeline analysis_v3_pipeline_0_2.
