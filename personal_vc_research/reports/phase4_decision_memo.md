# Research decision memo — close the feasibility study; alternative-data check

Date: 2026-10-13. Scope: US Reg CF offerings on Republic with an initial Form C filed 2018–2020. Frozen sample of
40 (seed 42, 13/13/14) drawn from a 224-offering frame. Outcome cutoff 2026-10-10.

**Decision: close the current study. Park quantitative return modeling (option 3).** No promising historical
return-data route was established.

## 1. What the existing research established

* **Historical company and contract information can be recovered.**
  * EDGAR and the DERA Form C datasets identify every sampled offering, its security and its terms.
  * Point-in-time facts can be pinned to dated filings (pilot: 5 offerings extracted with page locators; 22/40
    Form C PDFs needed OCR).
* **Business-outcome ascertainment is sparse and potentially selective.**
  * Strict definitive labels were found for **2 of the 36** offerings with an issuer-reported close (one exchange
    listing, one documented operational closure). 34 are unresolved.
  * Which outcomes become visible depends on the outcome type: listings leave SEC filings, while quiet failures
    leave nothing once Reg CF reporting stops (25 C-TRs across 23 offerings).
  * Legal status was not observed (registries blocked).
  * The most common adverse signal is a composite platform claim (Republic's `*`: insolvent OR dormant OR
    dissolved). Only the first appearance of the mark is datable, not the event.
* **Investor cash flows were not recovered from accessible sources** for any of the 40 offerings.
  * The only payoff-like items are platform notes on Republic's own commission holding, an unquantified company
    announcement (Linen), and an issuer-wide pooled SAFE conversion with conflicting amounts (Janover).
* **Predictive investment performance cannot be evaluated with this dataset.** 40 offerings, 2 ascertained
  definitive outcomes and 0 investor cash flows do not support estimating or validating returns.
* **These are limitations of this dataset and collection route.** They are not evidence that systematic startup
  investing is impossible, and not evidence about how often Reg CF companies succeed or fail.

**Statistical interpretation** (`docs/statistical_interpretation_review.md`):
* The phase-3 full-frame projections (about 11 strict events with a Wilson interval; about 50 `*` events) are
  **withdrawn**.
* They were unweighted despite year-stratified sampling. Stratum weights would give about 13.5 instead of 11.2.
* With 0–1 events per stratum, no interval is defensible.
* They measured *ascertainment under this collection process*, not outcome frequency.
* Only observed counts by cohort are retained. None are presented as base rates.

**Wording clarifications:**
* **The 36 "completed" offerings** are offerings with an **issuer-reported close** (Form C-U), not verified
  completions.
* **The 4 withdrawn offerings** filed a bare Form C-W: no reason and no commitment or refund information. None
  filed anything afterwards or appears in Republic's holdings tables.
  * No evidence of issued securities was found.
  * **Whether commitments were ever received is unknown.**

**Preserved:**
* frozen frame and sample (hashes in `data/frame/frame_freeze.json` and `data/sample/sample_freeze.json`);
* all evidence tables and the retrieval manifest;
* corrections C1–C8 (`reports/phase3_audit_corrections.csv`);
* the audits;
* reproducibility instructions (`README.md`).

The raw cache is not in git; the phase-2 evidence export preserves the documents behind verified facts.

## 2. What the alternative-source check established

**Budget.** Public documentation only; no purchases, accounts, outreach or workarounds.
* **Logged** (`data/manual/phase4_time_log.csv`): 2 min 26 s of container-clock time for the assessment
  (10:34:21–10:36:47 UTC). The container clock appears to advance only while tools run, so this understates
  elapsed time. The assessment is far inside the 2-hour cap either way.
* **Work done:** 10 web searches, 6 page fetches (4 blocked: 403 or 525, not retried) and 3 SEC documents. Sources
  are in `data/manual/phase4_alt_data_sources.csv`.
* No human-effort estimate is derived from this.

**Key:** V = verified in public documentation. C = provider's own claim or marketing, unverified. U = unknown or
not documented. "—" = not offered.

| Requirement | A. Commercial (KingsCrowd; also CCLEAR, Audit Analytics) | B. Academic datasets / replication packages | C. Investor records / platform exports (Republic) |
|---|---|---|---|
| Historical roster incl. failures and withdrawals | **C**: "over 9,000 … offerings tracked … 100% coverage of Reg CF and Reg A", since 2016 (KingsCrowd 1-K/A, 2025). Exits/failures only as "a growing body". Third-hand summary: tracks only exits/failures that are publicly announced, shared, or visible on websites (selective). CCLEAR **C**: "every … offering and investment since market inception" | **V** for non-US samples only (UK/DE: 212–413 successful campaigns, 2011–2016; follow-on funding and failure). No US Reg CF dataset or replication package found | **U**. An investor sees only their own positions |
| Features as known at the investment date | **U**. "300 data points" and ratings, but no documentation of vintage or point-in-time snapshots (ratings may be recomputed) | **U** | **U** |
| Security terms and conversion history | Terms: **C** (derived from filings). Conversion history: **U** | **U** | Terms: in the investor's documents (issuer). Conversions: issuer or transfer agent handles them (search-indexed help text, **C/U**) |
| Original investment basis | CCLEAR **C**: "transaction-level", meaning commitments. KingsCrowd **U** | **U** | Investor's own records only |
| Dated investor distributions | **U** (nothing documented) | **U** (UK platform IRRs are self-reported and largely notional) | **U**. Republic says it does not issue tax forms; issuer/transfer agent/trustee does (**C**) |
| Residual positions and observation cutoff | **U** | **U** | **U** |
| Data-use rights and export format | API exists (**V**: listed); terms and schema **U**. Data is "monetize[d] … to major FINRA registered CF portals" (**C**) | **U** | No documented investor export (**U**) |
| Price / access (if stated) | KingsCrowd Edge $14.99/month or $149/year; Pro (planned July 2025) $2,500/year for 3 licences (**V** in 1-K/A). API/institutional pricing **U**. Audit Analytics: subscription, price **U** | Free if published; none found | Requires positions the user does not hold. Pooled investor-contributed records would be **self-selected**: winners are reported more, missing positions are invisible |

**Assessment by route:**
* **A** could improve a *business-outcome roster* (exits and failures), but it is self-described as tracking only
  what is visible or reported. That is the same selective ascertainment found here, at larger scale. Nothing
  documents investor cash flows or point-in-time features. A dataset of rounds, valuations, exits and ratings is
  not a return dataset.
* **B** offers methods (registry-linked outcome panels), not US Reg CF investor returns.
* **C** depends on positions held. Platform docs point conversions and tax documents to issuers and transfer
  agents. Any pooled investor-contributed records would be non-representative.

## 3. Decision

**Option 3: no promising historical return-data route was established. Park quantitative return modeling.**

* **Why not option 1** (a data-access request is worth making). No route documents dated investor distributions
  or conversion outcomes. A request would ask a provider to reveal data that nothing in its public material
  suggests it has.
* **Why not option 2** (inspect a dataset before purchase). The only purchasable product with public pricing
  (KingsCrowd Edge/Pro) is a ratings and deal-search subscription. Its outcome data is self-described as partial.

## 4. Smallest next action that could change the decision

One cheap, optional, non-committal step could falsify the "no return data" conclusion for route A. Send the
message below to KingsCrowd (or the CCLEAR maintainer), which asks for a field list and a de-identified linked
example.

* **If the reply shows** dated investor-level or security-level cash flows linked to original offerings, with
  documented coverage of failures, reconsider option 2.
* **Otherwise**, the stop stands.

The message was **not sent**.

> Subject: Data documentation request — Reg CF offering-to-outcome linkage
>
> Hello. I am evaluating historical data on US Regulation Crowdfunding offerings (2018–2020 cohorts) for
> non-commercial research on investor outcomes. Before considering any purchase or licence, could you share your
> data dictionary and answer the following?
>
> 1. Does your dataset include every offering in a cohort, including failed, withdrawn and cancelled ones? How
>    are exits and failures identified, and what share of offerings have a known current status?
> 2. Are offering attributes and ratings stored as of the investment date (point-in-time snapshots), or
>    recomputed later?
> 3. Do you record security terms and later conversion events (date, conversion price or ratio, resulting
>    security)?
> 4. Do you record any dated cash flows to investors (repurchases, acquisition proceeds, dividends,
>    liquidations), at the investor, security or offering level? What are the sources?
> 5. What is each record's observation cutoff, and how are still-held positions represented?
> 6. What are the licence terms (research use, export format, redistribution) and the price?
>
> If possible, please include **one de-identified example record** that links an original offering (terms,
> amount raised, investment date) to its later security conversion and any investor cash flows.
>
> Thank you.

## 5. Stop recommendation

**Stop the current study here.**
* Do not expand to the 224-offering frame.
* Do not extract further historical features.
* Do not train models.
* Do not request registry lookups.

Prospective, public deal snapshots (offering documents captured on their publication date) can be archived
without buying securities, if the user wants a long-horizon record. They will not solve the missing-return
problem soon: payoffs take many years to mature, and cash flows remain unobservable without holder records.
Investing in order to generate training data is not recommended.
