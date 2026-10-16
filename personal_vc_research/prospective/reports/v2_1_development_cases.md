# v2.1 development cases: Mightylicious and TradeFunded (plus usage accounting)

All three analysed companies are **development cases** for `analyst_v2_0`: Hope-Neuron, Mightylicious and
TradeFunded. The rules were changed while looking at them, so these runs are excluded from evaluating v2.0 and say
nothing about performance on new offerings. Each company got **one bounded live rerun**. The one exception is
TradeFunded, retried once after an infrastructure failure (below).

## Mightylicious (Crowd SAFE): same frozen pack `PACK-RCF-2147043-020-37424-7e1d749b1f6d`

| Run | What | Result |
|---|---|---|
| 4, 5, 7–9 (v2) | v1 baseline and v1.1, plus revalidations | all `analysis_failed` (cited quote on the wrong page; invalid formula syntax) |
| **11** (v2.1, live) | stages A–F, cap of 2 repairs per stage | A–E validated after targeted repairs: A 1, B 2, D 2. **F (Korean summary) failed**: 241 words against the 250 floor, after 2 repairs. Pipeline 0_1 then marked the whole run `analysis_failed`. Estimated $8.50, 13 calls. |
| **12** (replay, no model call) | the final outputs of run 11 re-processed under pipeline 0_2, where an F failure is a presentation error | **`fails_current_screen`**; evidence `sufficient_for_current_conclusion`; availability `availability_unknown`; budget `incomplete_cost_information`; legacy v1 `fails_research_screen`. No Korean summary is shown (F stays rejected). |

**Blockers addressed.** The two v2 failure causes (page mismatch; formula syntax) were fixed by targeted repair with
explicit errors in stage A. Validation was not weakened.

**Criteria.**
- BT1 and BT2 pass: reviewed revenue was $347,602 in FY2024 and $459,216 in FY2025.
- **BT4 fail**: the accountant's review report contains a going-concern paragraph (p.42). The FY2025 operating cash
  outflow was $960,595, and the stockholders' deficit $(3,507,862), mostly SAFEs carried as a liability.
- **PC1 fail**: conversion requires a $1M+ equity round.
- **PC3 fail**: the CEO controls amendments and acts as proxy; there is no anti-dilution protection; earlier SAFEs
  are about 25% of the fully diluted count.
- BT3, BT5 and PC2 unresolved.

**Manual spot checks** (6 rows; one corrects a shell-quoting error in an earlier row): A24, A25, A22 and A9 are
supported; A35 is partially supported (it omits the good-faith duty).

**Calculator defect found here.** v1 multiplied the $1.00 SAFE purchase unit by 1,000,000 common shares and showed a
"$1.0M implied equity". No criterion cited it. Calculator v1_1 withholds per-share equity math for SAFEs and notes,
and for mismatched classes. The rows were recomputed (`recalc 12`); the v1 rows are kept.

**Forecasts** (#9, #10, `issuer_announces`):
- #9: target reached by 2026-12-18 (0.70);
- #10: Form C-W withdrawal by 2026-12-18 (0.07).

## TradeFunded (LLC Units): NEW pack `PACK-RCF-2128340-020-37393-23c6990906f5` (targeted OCR)

The original pack had only the Form C XML. The 61.7 MB PDF is image-only: 172 pages, no text layer.

**Targeting** (`target-ocr 15 --cap 60`):
1. A 100-dpi OCR page map of all 172 pages (about 1 minute with 4 workers).
2. Selection of 60 pages, in priority order:
   - contract: 48 pages;
   - financial statements: 14 pages;
   - offering terms: 13 pages.

   Many pages carry more than one tag.
3. 200-dpi OCR of the selected pages.

The **112 unprocessed pages** are recorded as a pack gap: pages 1–2, 4–7, 12–19, 22, 28–31, 33–36, 40–46, 72–73,
76–84, 88–90, 93–97, 99–134, 136–139, 141–144, 147–148, 151–159, 163–165 and 168–172. Both OCR passes are cached by
document hash.

| Run | What | Result |
|---|---|---|
| **13** (live) | stage A on the new pack | **The CLI returned no structured output.** Stage A errored after 125 s; both repairs errored in about 2 s at $0. The CLI's error text was not saved (adapter gap, fixed: `cli_result_text` is now kept). A probe call right after succeeded. Recorded `analysis_failed`; $0.55. |
| **14** (live retry) | same pack and version; labelled as a retry of run 13 because of an infrastructure error with no model output to judge | **`fails_current_screen`**. Classifier v2_1_2 gives evidence `extraction_incomplete` (v2_1_1 had said `sufficient`). Availability `availability_unknown`, budget `incomplete_cost_information`, legacy v1 `needs_information`. Estimated $3.58, 9 calls (3 repairs). |

**Criteria.**
- **PC1 fail**:
  - distributions are at the managers' sole discretion;
  - **5% of pre-distribution cash goes first to an affiliate** (Operating Agreement §10.1, p.85; also p.20);
  - transfers need the Manager Committee's consent;
  - there is no market and no repurchase right.
- **PC3 fail**:
  - a 10-year irrevocable proxy;
  - unlimited new Units without member consent;
  - no anti-dilution protection "except as stated in the Operating Agreement".
- Everything else is unresolved, because the business and team sections were among the unread pages.

**Classifier defect found here.** v2_1_1 let a supported failure override extraction gaps, so the result said
"sufficient" while most of the Operating Agreement was unread. That includes the exception that A26 itself points
to. v2_1_2 always reports `extraction_incomplete` when pages are unread. The brief's first next action is now to
check the unread pages (76–84, 88–90, 93–97, 99–134) for anything that changes PC1/PC3.

**Manual spot checks:** A20 (5% affiliate allocation) is supported; this is the most company-specific adverse term
in any of the three cases. A24 and A23 are supported. A26 is partially supported (its exception is unverifiable).

**Calculations.**
- K1: $2,625,000 pre-money ($0.35 × 7,500,000 Units).
- K2 and K3: post-money $2.70M at the offering minimum and $3.30M at the maximum.
- K4: fully diluted value withheld. The model listed the SAFEs (converted in April 2026) with undisclosed terms;
  since they are already converted, this is conservative but arguably mislabelled.

**Forecasts:**
- #11 `event_occurs`: first closing at the target or above by 2026-12-15 (0.40);
- #12 `issuer_announces`: Form C-W withdrawal by 2026-12-15 (0.07).

## Cross-case finding: PC1 and PC3 fail in all three cases

PC1 (security cash path) and PC3 (rights and dilution) were supported failures in **every** case. The cited terms
are mostly features that almost every Reg CF offering shares:
- the one-year transfer restriction plus consent requirements;
- discretionary or no distributions;
- custodian or nominee holding;
- voting proxies;
- no anti-dilution protection;
- conversion that depends on a future round.

As implemented, these two criteria do not separate one offering from another. Under the proposed v1.1 aggregation,
almost any Reg CF offering would come out `fails_current_screen`. That would make the screen uninformative.

Genuinely company-specific adverse terms did appear: TradeFunded's 5% affiliate allocation, the size of
Mightylicious's SAFE overhang, and Hope-Neuron's notes with undisclosed terms plus a $50k add-on. The criteria do
not currently distinguish these from boilerplate.

**This is a policy question for you, not an implementation fix.** It is listed in
`policies/screening_policy_v1_1_PROPOSED.md`. Options include judging PC1/PC3 *relative to the typical Reg CF
security* (a fail only for terms worse than the standard form), or making PC1/PC3 informational. Nothing was changed.

## Usage accounting (v2.1 model calls only)

Costs are CLI-reported **estimates at list price**. You use Claude through a subscription, so they are not billed
amounts; usage counts against your plan limits.

| Analysis | Company | Stage calls | Repair calls | Invalid outputs | Seconds | Output tokens | Est. USD |
|---|---|---|---|---|---|---|---|
| 10 | Hope-Neuron | 9 | 3 | 3 | 477 | 74,398 | 3.43 |
| 11 | Mightylicious | 13 | 7 | 8 | 803 | 126,769 | 8.50 |
| 12 | Mightylicious (replay) | 6 | 0 | 1 | 0 | 0 | 0.00 |
| 13 | TradeFunded (CLI error) | 3 | 2 | 3 | 129 | 21,059 | 0.55 |
| 14 | TradeFunded (retry) | 9 | 3 | 3 | 608 | 96,363 | 3.58 |
| **v2.1 total** | | **40** | **15** | | **~34 min** | **318,589** | **16.06** |

All-time estimate across every analysis run (v2 plus v2.1): $32.05. The per-call breakdown is in table `stage_usage`.
Repairs were 15 of the 34 live calls. Most were schema limits, Korean-length limits or citation mismatches, and each
repair sent only the explicit errors.
