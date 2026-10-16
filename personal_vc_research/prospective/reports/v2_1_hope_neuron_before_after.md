# Hope-Neuron — before/after (v2 analysis 3 → v2.1 analysis 10)

**Development case.** Hope-Neuron was used to design the v2.1 rules (prompt v2, classifier, calculator), so this
comparison shows behavior on a known case. It is **not** evidence that v2.1 performs better on new offerings.

Both runs use the **same frozen evidence pack**, `PACK-RCF-2114933-020-37299-893511c4af2b`: cutoff
2026-10-14T16:46:19Z, 67 pages, hash-checked on load. No Republic material was added; Republic stayed inaccessible
(see `republic_access_assessment.md`). The issuer-website capture of 2026-10-15 is current evidence and was **not** used.

| | Before: analysis 3 (`analyst_v1_1`, prompt v1.1, schema v1_0_x) | After: analysis 10 (`analyst_v2_0`, prompt v2, schema v2_0) |
|---|---|---|
| Brief | `reports/briefs/brief_RCF-2114933-020-37299_analysis3.md` (preserved) | `reports/briefs/v2_1/brief_RCF-2114933-020-37299_analysis10.md` |
| Model reported | claude-sonnet-5-5 | claude-sonnet-5-5 |
| CLI cost estimate (list-price equivalent, not billed) | $3.03 | $3.43 (9 stage calls, including 3 repair calls) |
| Wall time | 7 min 17 s | 7 min 57 s |

## 1. Classification

| | Before | After |
|---|---|---|
| Status / assessment | `needs_information` (v1 rule: an evidence gate that is not a pass outranks a gate-3 fail) | **`fails_current_screen`**, under the proposed `screening_policy_v1_1`, not acknowledged |
| Gate / criteria | evidence = unknown, business = unknown, price & contract = **fail** | BT4 **fail**, PC1 **fail**, PC3 **fail** (all supported); BT1, BT2, BT3, BT5, PC2 unresolved (model "unknown") |
| Evidence completeness | (not a separate dimension) | `sufficient_for_current_conclusion` |
| Operational readiness | inside "needs information" | `availability_unknown` (Republic blocked; no availability observation) |
| Budget | gate 4 pass | `incomplete_cost_information`. Classifier v2_1_1 made this change after my spot check (§3). The first v2_1 row said `eligible`; it is preserved. |
| Legacy v1 status, used by approvals | `needs_information` | `fails_research_screen` (gates derived from the criteria) |

**What changed and why.**
- Before, the decisive problem (gate 3 fail) was hidden behind "needs information". The brief then suggested
  collecting fees and availability, information that could not change a failing result.
- After, the failure is decisive and named. Missing fees and availability appear in their own dimensions.
- PC2 (price) moved from being part of a fail to **unresolved**. The "arbitrary price" wording is treated as a
  disclosure, and the $75M figure as arithmetic, not as proof of overvaluation.

## 2. Revisited issues (spec list) — before vs after

| Issue | Before (analysis 3) | After (analysis 10) | Manual check against the page |
|---|---|---|---|
| R&D $0 | C4: R&D $0 is "thin financial evidence ... against the Form C's claim of 'extensive testing'". This is an inference from a zero line. | A16 states the figure and period only ($0 FY2025, $26,836 FY2024), cites p.46, and draws no mismatch inference. It is not used in any decisive criterion. | p.46 matches. **Fixed.** |
| Audit vs efficacy | A17/C1 describe the audit correctly but never separate it from technology validation. | A14: "The audit addresses the accounts only, not the technology." | p.43 matches. The going-concern wording on p.44 is standard auditor-responsibility text, not a finding; the brief does not claim otherwise. **Fixed.** |
| Liquidity routes / Reg A | A34 listed "acquisition, IPO, Reg A conversion or later private sale" together as cash routes. | PC1 separates the routes: no dividend, repurchase or listing; a 1-year transfer restriction; no market. Reg A is called "only an interest, with no assurance" (A32). | p.24 matches. **Fixed.** Buyer liquidity is still not discussed separately. |
| Debt priority | B2: "described as senior debt..." with no qualifier. | A21 says the notes are called senior "without stating a waterfall". It still omits the source's "in certain scenarios". | p.33 says "in certain scenarios". **Partly fixed** (minor overstatement remains). |
| IRB / FDA / IND / first human | A24 is fine. Forecast #4 merged IRB, FDA, IND and first human dosing with "or". | A24 names each milestone separately. Forecast #7 is IRB approval only, `independently_corroborated`. | p.27 matches. **Fixed.** Forecast #4 is flagged `flagged_compound` (lineage row 1) and stays scorable as written. |
| p-value | C9 criticized the issuer's reading of p=0.008. A23 noted the missing sample size. | A25 says there is no sample size, design, controls or endpoint. BT2 is unresolved, not a pass. | p.28–29 match. **Holds.** |
| Calculations | A9/B1 were LLM arithmetic ($75.0M implied equity; 6.2% ownership at max) with no as-of dates. Convertibles were "excluded". | K1–K3 are computed in code from cited inputs: pre-money $75,000,001; post-money $75,075,001 (min) and $80,000,001 (max). Authorized 250M shares are listed as excluded. **K4 fully diluted is withheld**, naming the three notes with undisclosed terms. | The inputs match p.32 and p.8. **Defect:** the pack also shows 1 share at 2025-12-31 (p.45), but stage A put only 75,000,001 into `valuation_inputs`, so K1 is labelled `computed` instead of `illustrative`. The conflict is disclosed in A10, in PC2's reason and in the summary, but not in the K1 label. |
| Fees | A6 noted investor-side fees "are not stated". The critical item was not confirmed. | Stage A marked the fee item **confirmed** using A6, which is the *issuer-paid* intermediary fee. | **Defect found by manual check.** Fixed in classifier v2_1_1 (budget `eligible` now requires a user-confirmed investor fee). The prompt still needs to separate issuer-paid from investor-paid fees (next version). |
| New company evidence | — | None. Same pack. | — |

## 3. Overstated claims (model support check plus manual check)

- **Stage E (model judgment)** checked 13 claims cited by the failing criteria: 8 supported, 5 partially supported
  (A9, A19, A21, A31, B2; minor overstatement each), none not supported.
- **Manual comparison** (10 claims, labelled `manual_source_comparison_by_assistant_not_user`, done outside the
  pipeline): 8 supported, and 2 partially supported:
  - A6: its *use* as the fee confirmation is material;
  - A21: missing qualifier.

  One judgment concern: **PC3 rests largely on the voting proxy (A7)**. The proposed policy says that the absence of
  voting rights cannot by itself support a failure. The model labelled the ground `documented_contract_term`, so the
  code accepted it. Its other parts (no anti-dilution right; notes with undisclosed conversion terms) are generic or
  closer to missing information. PC1 also rests on features common to most Reg CF common stock. **BT4 alone keeps
  the result at `fails_current_screen`**, but the PC1/PC3 failures are contestable. A threshold rule for "fail vs
  unknown" is a policy question for you (see the handoff).

## 4. Forecasts

| Before (preserved, scorable as written) | After (new rows, explicit definitions) |
|---|---|
| #1 C-AR by 2027-10-14 (0.5) | — |
| #2 revenue > 0 (0.04) | — |
| #3 closing ≥ $75k by 2027-04-14 (0.35) | #6 `issuer_announces`: target reached with ≥ 1 closing, by 2026-12-31 (0.35) |
| #4 compound "IRB **or** FDA **or** IND **or** first human" (0.12), now flagged `flagged_compound` | #7 `independently_corroborated`: IRB approval for a human ALS trial, by 2026-12-31 (0.07) |
| — | #8 `issuer_announces`: conversion of either outstanding note, by 2026-12-31 (0.03) |

- v2 forecasts carry the target type, scope, allowed evidence, rationale, assumptions, unknown treatment and
  cancellation treatment.
- `silence_is_false` = 0 is enforced by a database check; early true resolution is allowed.
- Note: #8 ("either note") is a single event class, but it is borderline compound. The "or" check does not catch
  "either".

## 5. Readability and next actions

| | Before | After |
|---|---|---|
| Length before the decision content | Long sections 1–9; gates in a table with cells truncated at 300 characters | A 4-row dimension table, then a ~260-word Korean summary, decisive reasons, missing items and what would change the result |
| Truncation | Yes (gate cells) | None; the appendix uses lists. The test checks a 640-character reason survives |
| English in Korean fields | 17 English passages of 8+ words (gate criteria and uncertainty text shown in English) | Korean only, enforced by validator (English allowed inside parentheses since validator 0_2) |
| Next action | Collect fees and availability, which could not change a failing result | "Further collection is low priority; to revisit, check the cited sources of BT4/PC1/PC3 first". Fees and availability appear only as dimensions |
| Override | Not prominent | Not mentioned |

The summary is about 260 words, below the 300–500 target. The validator's hard floor is 250. Stage F needed two
repairs: the first output listed 8 "missing" items against a maximum of 5.

## 6. Later classifier versions

`reassess 10` under v2_1_2 (gaps always mean `extraction_incomplete`) changed nothing for Hope-Neuron, which has no
pack gaps. Every assessment row is kept: v2_1 (budget `eligible`), v2_1_1 and v2_1_2.

## 7. Defects found in this run, and their status

1. **Korean validator** counted parenthesized English terms (fixed: validator 0_2). This caused 1 unneeded repair
   round (E).
2. **Investor fee confirmed from an issuer-paid fee** (fixed in classifier v2_1_1. The prompt fix is pending, so the
   model still makes this mistake).
3. **Conflicting share counts** not passed to the calculator. K1 should be `illustrative` (open; prompt fix
   pending).
4. **PC1/PC3 failure threshold** (policy question; reported, not changed).
