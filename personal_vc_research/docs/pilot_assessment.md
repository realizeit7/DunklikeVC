## 8. Assessment of the four pilot questions

Five offerings test the workflow; nothing below is a statistical estimate.

### Q1. Can we reconstruct what was publicly available at the decision date (initial Form C + 30 days)?

**Mostly yes for SEC-filed content, with three caveats.**

* For 5/5 offerings, the dated sources were retrievable: the original Form C XML (structured cover-page financials,
  target/max, deadline, price, intermediary), the offering-memorandum PDF (officer histories, capitalization,
  securities summary, reviewed financial statements), and every C/A with its filing date. Point-in-time
  eligibility is enforced by publication date: 256/403 pilot facts are eligible, while 147 (from C/As, C-Us and
  later filings) are stored but excluded from features. Example: Up Sonder's deadline extension (C/A
  2019-01-23) counts at its 2019-02-21 decision date. Janover's minimum-investment cut (C/A 2020-11-13) does not,
  so $250 stays the decision-time minimum.
* **Caveat 1: availability is inferred, not verified.** For 5/5, the filings show an open offering at day 30
  (deadline in effect, no withdrawal, no closing update). No dated snapshot of the Republic campaign page was
  reachable: Republic is behind Cloudflare and the Wayback Machine is unreachable from this environment. The
  Exhibit D "offering page" printed inside the Form C is a filing-date snapshot only.
* **Caveat 2: the financials are stale and their periods are not in the structured data.** The fiscal-year end
  had to be read from the PDF. Statements were 5–13 months old at filing: Hemster's FY2017 at July 2018; Up
  Sonder's FY2017 at January 2019; SkyHi's FY2018 at October 2019; FY2019 for both 2020 offerings. Revenue growth
  was **not** computed. Janover's prior year (organized 2018-11-28) is a one-month stub and not comparable, and
  comparability was not established for the others.
* **Caveat 3: about half of the PDFs have no usable text layer.** 22/40 sampled Form C documents (12/13 in 2018)
  are garbled and need OCR; 15 are natively readable and 3 partially. Targeted OCR worked: 84 pages in 155 s over
  three documents. Pages were chosen from a free structural map (characters per page survive the garbling, so
  exhibit covers and dense risk-factor blocks are visible) in batches of at most 10. The 30-page cap was enough to
  reach terms, officers and financial statements for 3/3 garbled pilot documents. It was a resource limit, not
  full coverage: 137 of 221 pages in those three documents were never extracted ("not extracted within budget").

### Q2. Can we interpret the actual investment contract?

**Yes, at key-term level, for 5/5. The standardization is high.**

* All five are Republic Crowd SAFEs:
  * Valuation caps: $5M (Hemster), $6M (Up Sonder), $10M (SkyHi), $6M (People First), $20M (Janover).
  * Discounts: none stated (Hemster), 20%, 20%, 10%, 10%.
  * Conversion: at the **company's option** on an equity financing over $1M ($2M for Janover).
  * Caps are on a pre-money basis that excludes SAFEs and convertible notes.
  * Liquidity event: cash-out of the purchase amount or conversion, pro rata among cash-out holders if funds
    fall short.
  * No company repurchase right, and no voting rights.
* The instrument text itself was read for 4/5. Hemster's form of SAFE was not found among the pages processed,
  so its terms come from the memorandum summary only.
* Cap and discount were checked against the rendered page for the three OCR'd documents. 42 OCR-derived facts
  remain "OCR read, not visually verified"; the 14 of them that are contract terms are in the manual review
  queue.
* **The limit: interpreting the contract is not the same as valuing it.** What a Crowd SAFE holder receives
  depends on the terms of the *next* round (price, preferences, whether the company converts at all), and those
  are not public for private rounds. Form D gives only aggregate amounts.

### Q3. Can we trace subsequent business events?

**Partially. SEC filings trace the first 1–3 years well, then visibility stops.**

* Completion: 5/5 have a C-U stating the amount raised at close ($99,522 to $827,927). This is completion
  evidence, not investor profit.
* Reporting: 4/5 filed at least one C-AR, whose revenue and net income give operating-activity evidence. Hemster
  never filed a C-AR (possible non-compliance).
* Financing: 4/5 filed a later Form D. These are notices, not proof the amount was raised. Hemster's Form D
  reports $4,281,637 sold, which is consistent with independent reporting of a $4M post-seed round. 2/5 ran later
  Reg CF offerings on another portal.
* Termination: 4/5 filed a C-TR. Only one states a reason: People First RH cites 17 CFR 227.202(b)(2), at least
  one annual report filed and fewer than 300 holders of record. That is a reporting-relief basis, not failure.
* Listing: 1/5 (Janover) went public via a Nasdaq IPO in July 2023 (424B4 and 8-A12B filings).
* **After a C-TR the SEC trail usually ends.** 3/5 have no observation since 2020–2023: SkyHi (last
  2020-05-19), Up Sonder (2022-05-02) and People First (2023-02-09). Their status is *unknown*, not failed and
  not operating.
* Bounded web searches (2 per company at most) added independent post-offering evidence for 1/5. Hemster
  rebranded as (Re)vive in 2024; legal-entity continuity is not confirmed.
* An SEC-only run therefore under-observes later company updates. Republic investor updates were not accessible.

### Q4. Can we find investor-specific payout evidence?

**No for 4/5: none was found in accessible sources within budget, which means unknown, not zero.**

* For Janover (1/5), the issuer's 10-Ks report **non-cash conversions at a pooled class level**:
  * Oct 2022: 218,772 shares for $668,898 of the 2020 and 2021 SAFEs.
  * At the July 2023 IPO: the remaining SAFEs converted into 165,861 shares. The FY2024 10-K restates this as
    20,733, consistent with the 1-for-8 reverse split on 2024-12-30.
* This is evidence that holders received listed shares. The disclosures pool the 2020 Republic round with a
  2021 round and a separate SAFE class, and give no per-investor basis, conversion price by round, sale dates or
  proceeds.
* **No investor cash flow was documented for any pilot offering, and no real return was calculated.** The
  return module is exercised only on labelled synthetic fixtures.

## 9. Bottlenecks found

1. **Garbled PDF text layers** (55% of sampled filings, 92% of 2018 filings). Targeted OCR is cheap in CPU
   (about 2 s/page), but choosing pages and verifying numbers is analyst work.
2. **No point-in-time platform record.** Day-30 availability and campaign-page content can only be inferred.
3. **The outcome horizon ends at C-TR.** Most post-termination statuses are unknown from SEC data alone.
4. **The payout layer is essentially absent from public sources.** It surfaces only where the issuer later
   becomes an SEC reporting company, and even then it is pooled.
5. **Manual extraction cost.** The pilot's analyst extraction (about 90 facts across 5 offerings) was not
   instrumented. A rough estimate for a person doing the same work is 30–60 minutes per offering for terms,
   officers and financials with page locators, plus about 15 minutes for outcome searches.
6. **Source access.** Republic (Cloudflare), the Wayback Machine (connection reset), Kingscrowd (403) and
   Springer (login wall) were all unreachable. These are limitations of this run's environment, not proof the
   data does not exist.

## 10. Recommendation: **2. Modify collection methods before expanding** (and scope the expansion to business outcomes)

The pilot supports continuing the historical work for **point-in-time features, contract terms and business
events**. It does not support **historical investor-return research** with public sources. Expanding the current
pipeline to all 40 unchanged (option 1) would mostly add OCR-and-review labour and a larger pile of "unknown"
outcomes. Pausing entirely (option 4) is premature, because Q1–Q2 worked. Restricting to business outcomes
(option 3) is the realistic *target* of the expansion, but the outcome-collection method has to change first or
the business-outcome labels will be dominated by "unknown after C-TR".

**Modifications before expanding (about 1 week of part-time work)**

* Make page targeting a reusable step:
  * Auto-detect exhibit covers and the Crowd SAFE first page from the structural map.
  * Run OCR in batches of at most 10 pages.
  * Apply regexes for cap, discount and conversion trigger to the OCR text.
  * Queue every extracted number for rendered-page verification.
* Handle filings split across several PDFs (6/40) by screening all attachments; this is already done in
  `screen`.
* Add at least one non-SEC outcome source per offering that is free and allowed. Candidates:
  * State business-registry status (active / dissolved / forfeited) with the registry's own date.
  * Republic campaign updates, if the user can view them in their own browser. This run must not bypass
    Cloudflare.
  * Wayback snapshots from an environment where `web.archive.org` is reachable.
* Record "after C-TR" status explicitly as one of: registry-confirmed, independent report, or unknown.

**Expansion to the remaining 35 (after the modifications)**

* Data needed per offering: Form C XML and PDF; up to 30 OCR pages for garbled documents; DERA C/A, C-U, C-AR and
  C-TR rows; the EDGAR filing index; Form D XMLs; one registry lookup; up to 3 web searches.
* Approximate effort, as an estimate:
  * Automated SEC collection: minutes.
  * OCR: about 20 garbled documents × up to 30 pages × about 2 s, roughly 20 minutes of CPU.
  * Analyst extraction and verification: about 45 minutes per offering, roughly 25–30 hours in total, or 4–5 weeks
    at 6 hours per week.

**Key unresolved risks**

* Whether a registry or archive source can resolve post-C-TR status at reasonable cost.
* Survivorship and selection bias in which offerings leave traces.
* Pooled or absent payout disclosure, which makes even the "investor-relevant events" thin.
* Frame completeness beyond EDGAR-named intermediaries.

**What would make us stop (switch to option 4: prospective collection)**

* After the modified collection, "unknown" remains the most common post-offering status across the 40.
* Or the added outcome source cannot be accessed lawfully and repeatably within the time budget.

In either case, historical outcome labels would mostly measure *visibility* rather than business results. The
better path would then be to document the user's own future Reg CF investments prospectively: dated deal
snapshots, the contract PDF, and the user's own contribution and distribution records. That is the only route
here to traceable investor cash flows.
