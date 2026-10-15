# Research screening policy — `screening_policy_v1`

> **Status: initial, UNVALIDATED research convention.** These criteria are a structured reading checklist. They are
> not a validated predictor of company success or investment returns.
>
> * A **pass** means only "eligible for user review".
> * A pass never creates a user decision, a budget reservation, an investment or an assumed fill.
> * The user must acknowledge this policy (`python -m prospective ack-policy screening`) before recording any live
>   approval. Drafts and analyses may run beforehand.

There are four separate gates. There is **no composite score**. Each qualitative gate reports **pass / fail /
unknown**, together with:
* the criteria applied;
* the supporting evidence and the counterevidence, with citations into the frozen evidence pack;
* the remaining uncertainty.

The final AI status is derived deterministically by software (`analysis.derive_status`):

| Condition | AI status |
|---|---|
| Output failed schema or citation validation | `analysis_failed` |
| Any critical-information item missing, or gate 1 not `pass` | `needs_information` |
| Gate 1 passes, and gate 2 or gate 3 is `fail` | `fails_research_screen` |
| Gate 1 passes, and gate 2 or gate 3 is `unknown` | `needs_information` |
| Gates 1–3 pass | `passes_research_screen` (gate 4 is shown separately and may still block an approval) |

## Gate 1 — Evidence sufficiency

**Critical information.** The software checks these items in the evidence pack before any LLM runs. A missing item
blocks a clean pass:

1. Issuer and offering identity: legal name, CIK, offering file number.
2. Security type.
3. The original contract or operative instrument, present **and readable** in the pack. A summary does not
   substitute for it, and an unparsed or oversized PDF is a visible gap.
4. Relevant price or valuation cap, and conversion terms. These come from the contract text, including any tiers or
   early-bird terms.
5. Applicable minimum investment and investor-paid fees. If they are not disclosed, the item is `unknown` and the
   user must confirm it at approval.
6. Available financial statements and their dates. The age of the data is shown; stale figures are labelled.
7. Closing or availability evidence. The platform is unreachable, so availability is usually `unknown`, and that is
   always stated.

**The LLM must also check that:**
* each material claim is linked to a source and locator in the pack;
* issuer claims are separated from document-supported facts, calculations and inferences;
* contradictions are listed.

## Gate 2 — Business thesis

Criteria, all qualitative and judged on cited evidence only:
* **Customer and revenue model.** It is comprehensible: who pays, for what, how often.
* **Demand.** Demand claims are supported by evidence (revenue, contracts, usage, regulatory progress), not only by
  assertion.
* **Competition.** Differentiation is explicit, and competitive threats are named.
* **Financial condition and funding needs.** The analysis covers the dated cash position, burn and liabilities, and
  how much more capital is likely needed. No current runway is fabricated from stale cash and incomparable expense
  figures.
* **Team.** Founder and team capabilities are supported by the documents: relevant experience and execution
  history only. There is no demographic or personality assessment.
* **Pre-revenue companies.** They are labelled as such and judged on stage-appropriate evidence; revenue is not
  required for every model.

## Gate 3 — Price and contract

Criteria:
* **The actual security.** The analysis identifies the security (Crowd SAFE, common stock, convertible note, …),
  how it could produce cash for the investor (conversion plus a liquidity event, dividends, repurchase), and what
  usually prevents that (no liquidity event, dilution, nominee or proxy structures, transfer restrictions).
* **Price relative to the path to value.** The price or cap, the discount, any tiers, and pre- vs post-money basis
  are considered against that path.
* **Rights.** Material investor rights and limitations are covered: voting, information, MFN, pro rata,
  liquidation preference.

**Sensitivity scenarios.** These are optional. Every assumption (exit value, dilution, timing) must be explicit, and
the output is labelled "illustrative scenario, not an expected return".

## Gate 4 — Investment-budget eligibility (software only)

This is computed deterministically from `policies/budget_policy_v1.yaml` and the ledger:
* remaining annual capacity;
* remaining per-issuer capacity.

The LLM never computes or overrides budget balances.

## Proposed research conventions (developer-introduced, unvalidated)

* **Financial data staleness.** The most recent fiscal-year figures are labelled stale when the fiscal year ended
  more than 15 months before the analysis date.
* **Analysis staleness.** A brief is labelled stale when the analysis is older than 30 days, or when any new filing
  has been observed since the evidence cutoff.
