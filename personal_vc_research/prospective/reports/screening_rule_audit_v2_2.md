# Screening rule audit (v2.2)

Audited 2026-10-17 against the checkout on branch `v2.2-screening-thesis`, created from `v2.1-republic-briefs` at
`d1163aa`; analysis 10 lives there.

## Activation state found in the repository and database

| Artifact | Version | sha256 | State |
|---|---|---|---|
| `policies/screening_policy_v1.md` | screening_policy_v1 | `adfdd214…52ae4` | **Used by code** (`analysis_runs.status`, `ledger.approve`). **Never acknowledged**: `policy_acknowledgments` is empty, so every live approval is blocked today. |
| `policies/screening_policy_v1_1_PROPOSED.md` | screening_policy_v1_1 | `e8a988d9…2496` | PROPOSED, not acknowledged. Implemented only as the v2.1 `assessments` labels (`screening_policy_v1_1_proposed_unacknowledged`). |
| `llm/prompts/analyst_prompt_v2.md` | analyst_prompt_v2 | `eaf95211…9bb2` | Defines criteria BT1–BT5 and PC1–PC3 (the texts below). These IDs exist **only** in prompt v2 and `llm/schemas_v2.py`. Policy v1 has gate names and bullets, but no rule IDs. |
| `assess.py` | assessment_classifier_v2_1_2 | `8e36d892…1a05` | The code support rules for v2.1 criteria. |

There are no approvals, ledger events or user decisions. Hope-Neuron analysis 10 assessed BT4, PC1 and PC3 as
decisive under v1_1 (proposed).

## Rule inventory

Columns:
- **Type:** F = factual check, P = investor preference, E = economic judgment, X = execution constraint.
- **Indep.:** whether the rule can cause rejection on its own.

### screening_policy_v1. Policy v1 has no rule IDs; the locators below are audit references only.

| Locator | Exact text (abridged only where marked …) | Type | Evidence needed | Indep. (as implemented) | False-rejection risk | Proposed revision |
|---|---|---|---|---|---|---|
| v1-G1 | "Critical information … A missing item blocks a clean pass" (7 items: identity, security type, contract, price/cap, minimum and fees, financial statements, closing/availability) | F + X mixed | pack checklist | Blocks a pass (→ `needs_information`); does not reject | It mixes execution facts (fees, availability) into research sufficiency | Keep the factual items in the evidence status. Move fees and availability to the execution and budget dimensions (**R-EV1, X-1, X-2**). |
| v1-G2 bullets | Customer/revenue model "comprehensible"; demand "supported by evidence (revenue, contracts, usage, regulatory progress)"; competition; "financial condition and funding needs"; team; pre-revenue "judged on stage-appropriate evidence" | E | claims | **A gate-2 fail gives `fails_research_screen`** | "Regulatory progress" counts as demand. There is no failure threshold, so any weakness can be a fail. | Split into dimensions TECH, DEMAND, REG, TEAM and FIN, each with an explicit adverse-finding definition |
| v1-G3 bullets | "The actual security … what usually prevents that"; "Price relative to the path to value"; "Rights … voting, information, MFN, pro rata, liquidation preference" | E | contract, claims | **A gate-3 fail gives `fails_research_screen`** | "What usually prevents that" invites failing on ordinary Reg CF features | **R-TERMS-1/2/3**: only terms worse than the ordinary form, documented and material, can decide |
| v1-G4 | Budget eligibility (software) | X | ledger | Blocks approval | — | Unchanged (**X-3**) |
| v1 status table | Gate 1 not passing gives `needs_information`, *before* gate 2/3 failures | aggregation | — | — | It hides decisive findings | Replaced by the code aggregation in §5 of the proposal |

### analyst_prompt_v2 criteria (used by v2.1 / proposed v1_1)

| ID | Exact text | Stage/security applicability | Type | Indep. under v2.1 code | False-rejection risk seen | Proposed revision |
|---|---|---|---|---|---|---|
| BT1_customer_and_revenue_model | "who pays, for what, how often." | All; ill-defined pre-commercial | E | Yes, if "supported" | — (unknown in analysis 10) | → **R-DEM-1** (commercial stage) |
| BT2_demand_evidence | "demand is supported by evidence (revenue, contracts, usage, regulatory progress), not only by assertion." | All | E | Yes | **Mixes regulatory and efficacy evidence into demand.** In analysis 10 the mouse study was cited under BT2. | → **R-DEM-1**, with an allowed-evidence list; preclinical efficacy → **R-TECH-1** |
| BT3_competition | "differentiation is explicit, and threats are named." | All | E | Yes | — | → evidence for the thesis question "advantage" |
| **BT4_financial_condition_and_funding** | "the dated cash position, liabilities and burn; future capital needs." | All | E | **Yes: decisive in analyses 10 and 12** | **Rejected on low audited cash from 2025-12-31 and on going-concern language**, both generic for pre-revenue companies. There is no milestone test. | → **R-FIN-1**: adverse only if the documents show the company cannot reach its next milestone even at the maximum raise, using same-period data; or a documented default/insolvency |
| BT5_team_evidence | "documented relevant experience and execution history." | All | E | Yes | — | → **R-TEAM-1**; adverse only on a documented sanction or misstatement |
| **PC1_security_cash_path** | "how THIS security could produce cash, and what prevents it." | All | E | **Yes: decisive in 10, 12 and 14** | **Rejected on "no dividend, buyback or IPO", the transfer restriction and the custodian**: ordinary Reg CF features present in every case | → thesis question "what must happen for this holder to receive value" (not a rejection rule), plus **R-TERMS-1** for terms worse than the norm |
| PC2_price_vs_path_to_value | "price or cap and terms against the path to value." | All | E | Yes | Low: v2.1 kept "arbitrary price" non-decisive | → **R-TERMS-2**; it cannot reject on its own without comparables |
| **PC3_investor_rights_and_dilution** | "rights, limitations and dilution sources." | All | E | **Yes: decisive in 10, 12 and 14** | **Rejected on no anti-dilution, the voting proxy and undisclosed note terms** (missing information) | → **R-TERMS-3** (identify dilution and priority; missing terms = unknown) and **R-TERMS-1** |
| (code) NON_DECISIVE_GROUNDS | `missing_information, pre_revenue_status, absence_of_voting_rights, arbitrary_price_disclosure, comparable_valuation, other` | — | aggregation | — | **The guard works on the model's label for a finding, not on the facts.** "No dividend" was labelled `documented_contract_term` and going concern `documented_adverse_fact`, so the guard never fired. | Tag each fact with its generic trigger; code refuses a decisive finding whose facts are all generic (§4 of the proposal) |

## Analysis 10's decisive reasons, re-read against the source pages

These were checked by the assistant (same agent family as the analyst, so this is **not** independent validation).

| Reason | Facts actually cited | Source check | What the facts establish | Generic? |
|---|---|---|---|---|
| BT4 | A13 (Form C XML: FY2025 revenue $0, net loss $56,126, cash $19,213); A15 (audited liabilities $268,348 incl. $199,875 related-party payable); A18 (going-concern **risk factor**); A21 (notes 4.19%/4.13%); A22 (planned $50k note, MOU) | XML p.1; FS p.45; Form C p.12; pp.33–35; p.52 | Audited cash at 2025-12-31 was low against liabilities; the issuer **reports** $160,487 cash at 2026-06-18 (A17, unaudited); no spending for 2026 | Mostly: stale low cash + going-concern disclosure (G2, G3). The related-party payable with no maturity is company-specific, but no document says it is due. |
| PC1 | A7 (proxy), A9 (transfer restriction), A31 (custodian), A32 (Reg A interest, not assured), A8, A21 | pp.10, 23–24 | Ordinary Reg CF common-stock features; Reg A is not assured | Yes (G4, G6) |
| PC3 | A7, A8 (no anti-dilution), A11 (founder 100% votes), A19 (notes, conversion price not numerically stated), A31, B2 | pp.10, 25, 32–35 | Proxy and no anti-dilution are ordinary; note conversion terms are **missing**, not documented as adverse; the $50k add-on on conversion is a documented term, but its effect cannot be quantified | Mostly (G5, missing information) |
