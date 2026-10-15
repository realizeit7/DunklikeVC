# Screening policy v1.1 — PROPOSED, NOT IN FORCE

> **Status: proposal. It requires your acknowledgment and is not acknowledged.** `screening_policy_v1` remains the
> policy of record:
> * `analysis_runs.status` is still computed under v1;
> * the approval path (`ledger.approve`) still reads that v1 status;
> * the budget policy is unchanged.
>
> The v2.1 classifier writes its four-dimension result to the separate `assessments` table, labelled
> `screening_policy_v1_1_proposed_unacknowledged`. Briefs show it with that label.
>
> To adopt v1.1, review this file and say so. Recording that acknowledgment, and switching the approval path to v1.1,
> is a separate future change; it is not made in v2.1.

Like v1, this is an unvalidated research checklist. A "pass" only means "eligible for your review".

## What changes from v1 (policy changes, need acknowledgment)

| # | v1 rule | Proposed v1.1 rule | Why |
|---|---|---|---|
| 1 | Any missing critical item, or gate 1 not `pass`, gives `needs_information`, even when gate 2 or 3 fails. | A **supported** failure of a required criterion gives `fails_current_screen`. Missing information does not erase it. | v1 hid decisive failures behind "needs information". For Hope-Neuron analysis 3, gate 3 = fail was reported as `needs_information`. |
| 2 | Gates 2 and 3 are judged as whole gates. | Each gate is split into required criteria: BT1–BT5 and PC1–PC3. A gate fails if any of its criteria has a supported failure. A pass requires every criterion to pass. | Makes the decisive reason explicit and auditable. |
| 3 | Investor fees and availability are critical items. They block a clean pass, and so they block the status. | Investor fees go to **budget status** (`incomplete_cost_information`). Availability goes to **operational readiness** (`availability_unknown`). Both stay visible as execution blockers at approval. Neither changes the research assessment. | Both are execution facts, not research findings. The approval checks in `ledger.approve` are unchanged and still require both. |
| 4 | (Not stated.) | These cannot on their own support a failure: missing information, pre-revenue status, absence of voting rights, an "arbitrary price" disclosure, comparables. A failure needs at least one decisive ground: a documented adverse fact, a documented contract term, a computed calculation, or an internal inconsistency in the documents. | Prevents rejecting companies for stage or structure alone. Implements your instruction not to auto-reject pre-revenue or non-voting offerings. |
| 5 | Status values: `passes_research_screen`, `fails_research_screen`, `needs_information`, `analysis_failed`. | Four separate dimensions, described below. | Separates research, evidence, execution and budget questions. |

## Four dimensions

- **Assessment:** `fails_current_screen` / `passes_current_screen` / `indeterminate` / `analysis_failed`.
- **Evidence completeness:** `sufficient_for_current_conclusion` / `material_gaps` / `extraction_incomplete`.
  - `extraction_incomplete` means a document in the pack could not be read, or the analysis did not validate. It is
    never read as the issuer not disclosing something.
- **Operational readiness:** `available_verified` / `availability_unknown` / `unavailable_or_closed` / `not_checked`.
- **Budget status:** `eligible` / `ineligible` / `incomplete_cost_information`.

## Implementation fixes (no policy change; already in force in v2.1)

- A failure counts as "supported" only when all of these hold:
  - it has a decisive ground;
  - it rests on a valid cited claim or a computed calculation;
  - the structured support check did not reject it.

  Otherwise the criterion is `unresolved`. This applies v1's own rule that unverified material cannot support a
  gate.
- Valuation arithmetic is deterministic code (`calc.py`) with provenance. Authorized shares are never used.
  Convertibles with undisclosed terms make the fully diluted figure `withheld`.
- Freshness: "no new filings" is stated only for an interval covered by a successful EDGAR check.
- Forecast definitions are structured; the originals are kept.
- Repair is capped, and both original and repaired outputs are kept.
- The brief layout is new.
