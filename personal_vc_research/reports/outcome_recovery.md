# Outcome-recovery experiment — 5 pilot offerings (phase 2)

Frozen sample unchanged (seed 42); outcome cutoff 2026-10-10. Source tiers are kept separate: **SEC-issuer** (the company's own filings), **SEC-platform** (Republic's SEC-filed claims about its 2% commission holdings), **external** (company websites, press, observations).

## 1. Before vs after, per company

| company | BEFORE: last observation (phase 1; SEC + 2 Hemster press items) | AFTER: last SEC-issuer obs. | AFTER: last SEC-platform obs. | AFTER: last external obs. | operating evidence (SEC-issuer / external) | legal status | Republic marks (as-of year) | platform mark conflicts SEC | payout visibility | summary BEFORE → AFTER |
|---|---|---|---|---|---|---|---|---|---|---|
| Up Sonder, LLC | 2022-05-02 | 2022-05-02 | 2026-04-30 | 2026-10-05 | 2022-05-02 / 2026-10-05 | unknown — registries not accessible | 2022:no_status_mark; 2023:no_status_mark; 2024:no_status_mark; 2025:no_status_mark | False | none_found | reporting_terminated_status_unknown → reporting_terminated_later_activity_reported |
| Hemster, Inc. | 2024-11-12 | 2019-09-06 | 2026-04-30 | 2024-11-12 | - / 2024-11-12 | unknown — registries not accessible | 2022:security_converted_no_cash; 2023:no_status_mark; 2024:no_status_mark; 2025:no_status_mark | False | none_found | operating_activity_last_evidenced → operating_activity_last_evidenced |
| Janover Ventures LLC | 2026-09-03 | 2026-09-03 | 2026-04-30 | - | 2026-03-30 / - | unknown — registries not accessible | 2022:no_status_mark; 2023:no_status_mark; 2024:no_status_mark; 2025:insolvent_dormant_or_dissolved | True | security_class_conversion_reported_non_cash; security_class_definition_pooled | listed_via_ipo_payout_unknown → listed_via_ipo_payout_unknown |
| SkyHi Travel, Inc. | 2020-05-19 | 2020-05-19 | 2026-04-30 | - | 2020-05-19 / - | unknown — registries not accessible | 2022:no_status_mark; 2023:insolvent_dormant_or_dissolved; 2024:insolvent_dormant_or_dissolved; 2025:insolvent_dormant_or_dissolved | False | none_found | reporting_terminated_status_unknown → platform_claims_insolvent_dormant_or_dissolved |
| People First RH, Inc. | 2023-02-09 | 2023-02-09 | 2026-04-30 | 2020-10-27 | 2022-04-29 / - | unknown — registries not accessible | 2022:no_status_mark; 2023:no_status_mark; 2024:no_status_mark; 2025:no_status_mark | False | none_found | reporting_terminated_status_unknown → reporting_terminated_status_unknown |


Republic legend (verbatim, SEC filings by Republic Core LLC / Republic Note): `*` = "to Republic Crowd-Invest's knowledge the issuer is insolvent, dormant, or has dissolved and [it] does not expect to receive any cash proceeds"; `+` = "security has converted due to a qualifying equity financing, liquidity event ... but [it] has not realized cash proceeds"; numbered notes = liquidation at stated cents on the dollar. These are platform claims about Republic's own commission securities, not registry facts.

## 2. Event counts by source tier (pilot, after phase 2)

| tier | events_after | events_before |
|---|---|---|
| external | 6 | 2 |
| sec_issuer | 54 | 54 |
| sec_platform | 25 | 0 |


## 3. Field coverage by offering (historical, eligible at decision date)

`S` structured filing field · `V` manual, verified (rendered page or native text) · `O` manual from OCR, not visually verified · `-` missing / not extracted. 404 stored fact rows are **not** 404 independent observations: they repeat fields across the initial Form C and pre-decision amendments, and include post-decision rows that are excluded from features.

| group | field | 1745458 | 1758964 | 1769923 | 1783004 | 1805526 |
|---|---|---|---|---|---|---|
| financial | revenue | S | S | S | S | S |
| financial | net_income | S | S | S | S | S |
| financial | total_assets | S | S | S | S | S |
| financial | cash_and_equivalents | S | S | S | S | S |
| offering_terms | target_offering_amount | S | S | S | S | S |
| offering_terms | maximum_offering_amount | S | S | S | S | S |
| offering_terms | offering_deadline | S | S | S | S | S |
| offering_terms | price_per_security | S | S | S | S | S |
| offering_terms | minimum_investment | O | O | V | O | V |
| offering_terms | employees | S | S | S | S | S |
| contract | valuation_cap | V | V | V | V | V |
| contract | discount_rate | - | V | V | V | V |
| contract | cap_basis | V | O | V | O | V |
| contract | conversion_trigger | V | V | V | V | V |
| contract | liquidity_event_treatment | V | V | V | V | V |
| contract | company_repurchase_right | V | V | V | V | V |
| contract | dissolution_treatment | O | - | - | - | - |
| company | fiscal_year_end_most_recent | O | O | V | V | V |
| company | prior_securities_outstanding | O | O | V | O | - |
| company | date_incorporation | S | S | S | S | S |
| founder | officers_directors_listed | O | O | V | O | V |
| founder | founder_count_labelled | O | O | - | - | V |
| founder | prior_ventures_documented | O | O | V | - | V |
| founder | prior_exits_documented | - | - | - | - | - |


## 4. Janover security reconstruction (2020 Republic Crowd SAFE)

| level | event_or_as_of | claim | status | notes |
|---|---|---|---|---|
| 1 | 2022-10 | 218,772 common shares issued for conversion of $668,898 of "the 2020 and 2021 SAFEs" | documented | implied average $3.0575/share; event type triggering conversion not stated |
| 1 | 2023-07 (IPO, forward-looking at prospectus date) | 75,207 shares on automatic conversion of $176,326 of 2020/2021 SAFEs; 89,375 shares for $286,000 of 2022 SAFEs (= 164,582) | documented | implied $2.3445/share (2020/2021) and $3.20/share (2022 = $4.00 x 0.8) |
| 1 | 2022-10 notice for IPO | $14,734 of 2020/2021 SAFEs to convert into 5,358 shares at IPO closing | documented_conflicting | CONFLICTS with $176,326 -> 75,207 in the same prospectus |
| 1 | 2023-07 | all remaining outstanding SAFEs converted into 165,861 shares at IPO | documented | differs from 164,582 (prospectus) by 1,279 shares; unexplained |
| 1 | 2024-12-30 | same conversion restated as 20,733 shares after 1-for-8 reverse split | documented | 165,861 / 8 = 20,732.6 -> consistent |
| 2 | 2020-08 / 2021-02 | "2020/2021 SAFEs" = Reg CF SAFEs sold from Aug 2020 at $20M cap / 10% discount (the Republic Crowd SAFE terms) PLUS one $50,000 SAFE sold to one investor in Feb 2021 on the same terms; total $779,334 | documented | class is pooled: not purely Republic |
| 2 |  | Republic-offering principal candidates: $779,334 - $50,000 = $729,334 (derived); C-U commitments $827,927; Republic Core "capital raised" $714,053; "net proceeds" $685,737; converted principal $668,898 + $176,326 = $845,224 | conflicting | amounts do not reconcile; converted principal exceeds stated class total |
| 2 |  | Shares attributable to the Republic offering | NOT RECOVERABLE | pooled with non-Republic $50k SAFE and internal amount conflicts; no per-investor or per-closing conversion schedule disclosed |
| 3 |  | Shares per original investment dollar | NOT RECOVERABLE | missing: event type & date per conversion batch; FDC or Liquidity Capitalization immediately prior; round price; which investors converted in 2022 vs at IPO; investor elections (cash vs shares); effect of 2022 LLC->corp restructuring and Class A/B exchange. Implied batch averages ($3.06, $2.34, $2.75) are arithmetic only |
| 4 | 2023-07 | Legal tradability: shares issuable on conversion of 2020/2021 SAFEs registered for resale (Reg. No. 333-267907); SAFE investors named as selling stockholders; "selling stockholders have not entered into lock-up agreements with the underwriters" | documented | the Crowd SAFE itself also says converted IPO stock may be locked up up to 180 days; practical delivery mechanics (transfer agent book-entry vs broker, any Republic nominee/custody) not documented |
| 5 |  | Actual investor cash proceeds | NOT FOUND | no sale, distribution or cash-out record for any 2020 Republic investor in accessible sources; unknown, not zero |


Levels: 1 issuer-wide aggregate conversions · 2 shares attributable to the Republic offering · 3 shares per original dollar · 4 legal/practical tradability · 5 actual investor cash proceeds. **Stopped at level 1**: the conversion class pools the Republic SAFEs with a $50,000 non-Republic SAFE and the disclosed amounts conflict, so no proportional allocation was made. No price history was retrieved; no hypothetical liquidation was computed.

## 5. Targeted high-impact checks (separate from the random audit)

| claim | offering_id | evidence_checked | result | note |
|---|---|---|---|---|
| liquidity_event_treatment | RCF-1758964-020-25095 | p69 rendered | verified | investor election; default = automatic conversion (wording corrected) |
| liquidity_event_treatment | RCF-1783004-020-25792 | p67 rendered | verified | same; wording corrected |
| liquidity_event_treatment | RCF-1745458-020-24457 | p31 rendered (memorandum summary) | verified_summary_only | at Purchaser option; default not stated; instrument not located |
| liquidity_event_treatment | RCF-1769923-020-26464 | p62 native text | verified_native | default = conversion if no cash election |
| liquidity_event_treatment | RCF-1805526-020-26437 | p64 native text | verified_native | default = conversion if no cash election |
| company_repurchase_right | RCF-1758964-020-25095 | p29 rendered | verified | none |
| company_repurchase_right | RCF-1783004-020-25792 | p27 rendered | verified | none |
| company_repurchase_right | RCF-1745458-020-24457 | p33 rendered | verified | none |
| company_repurchase_right | RCF-1769923-020-26464 | p31 native | verified_native | none |
| company_repurchase_right | RCF-1805526-020-26437 | p27 native | verified_native | none |
| conversion_trigger | RCF-1758964-020-25095 | p27 rendered | verified | >$1M equity financing, company option |
| conversion_trigger | RCF-1783004-020-25792 | p25 rendered | verified | >$1M, company option |
| conversion_trigger | RCF-1745458-020-24457 | p30 rendered (phase 1) | verified | >$1M, company option |
| valuation_cap/discount | RCF-1758964-020-25095 | p68 rendered (phase 1) | verified | $6M / 20% |
| valuation_cap/discount | RCF-1783004-020-25792 | p66 rendered (phase 1) | verified | $10M / 20% |
| valuation_cap/discount | RCF-1745458-020-24457 | p30 rendered (phase 1) | verified | $5M via Safe Price / none stated |
| janover_conversion_numbers | RCF-1805526-020-26437 | cached 10-K FY2023, 10-K FY2024, 424B4, resale 424B4 (exact-string search) | verified_documents | 218,772 / $668,898; 75,207 / $176,326; 5,358 / $14,734; 165,861; 20,733; 1-for-6.82 and 1-for-8 splits; $779,334 and $50,000 SAFE all present verbatim; amounts conflict with each other (see trace) |
| janover_pooling | RCF-1805526-020-26437 | resale 424B4 description of capital stock | verified_documents | 2020/2021 SAFE class includes one $50,000 non-Republic SAFE -> Republic attribution not separable |
| payout_calculation | ALL | all pilot offerings | not_applicable | no payout calculation performed; no investor cash flows were recovered from accessible sources |


## 6. Time and source yield

| task | start | end | agent_minutes_measured |
|---|---|---|---|
| janover_security_trace | 2026-10-11T15:09:29Z | 2026-10-11T15:11:25Z | 1.9 |
| janover_trace_writeup | 2026-10-11T15:17:51Z | 2026-10-11T15:20:16Z | 2.4 |
| registry_lookups | 2026-10-11T15:11:25Z | 2026-10-11T15:14:18Z | 2.9 |
| republic_core_car_review | 2026-10-11T15:05:47Z | 2026-10-11T15:15:37Z | 9.8 |
| republic_core_sample_coverage | 2026-10-11T15:22:32Z | 2026-10-11T15:23:15Z | 0.7 |
| source_access_probe | 2026-10-11T15:04:09Z | 2026-10-11T15:05:47Z | 1.6 |
| targeted_audit_render | 2026-10-11T15:14:18Z | 2026-10-11T15:15:37Z | 1.3 |
| targeted_audit_writeup | 2026-10-11T15:20:16Z | 2026-10-11T15:20:23Z | 0.1 |
| web_evidence_capture | 2026-10-11T15:15:57Z | 2026-10-11T15:17:51Z | 1.9 |


Measured agent wall-clock for the experiment: **23 minutes** (container clock; excludes report writing). This is not analyst time; see the assessment for a labelled analyst-equivalent estimate.

| source | companies_attempted | companies_with_new_dated_evidence | yield | access_barrier |
|---|---|---|---|---|
| Republic Core / Republic Note SEC filings (holdings tables, 4 as-of dates 2022-2025) | 5 | 5 | dated platform rows for 5/5; informative status marks for 3/5 (SkyHi *, Hemster +, Janover * conflicting); capital-raised figures for 5/5 | none |
| Issuer SEC filings beyond phase 1 (Janover 424B4 x2, 10-K x2) | 1 | 1 | security-class conversion detail; class pooling; tradability registration | none |
| EDGAR full-text search for later mentions (2021-2026) | 5 | 2 (via Republic Core) | found Republic Core link; "Up Sonder" hit in a SPAC S-1 was a name collision (not used) | none |
| State business registries (DE, CA, NY, FL) and OpenCorporates | 5 | 0 | none | DE CAPTCHA; CA Imperva block (HTTP 429); NY empty reply; FL HTTP 403; OpenCorporates search disallowed by robots.txt, API needs key |
| Company websites (raw HTML captured) | 5 | 2 | Up Sonder dated posts to 2026-10-05; People First newest post 2020-10-27 | hemster.com domain-sale redirect then 403; flyskyhi.com TLS failure (not bypassed); Janover n/a |
| Press articles (raw HTML captured with embedded datePublished) | 1 | 1 | Hemster: 2019-10-17 $4M round; 2024-11-12 rebrand to (Re)vive (press-reported link only) | none |
| Web searches this phase | 5 | 0 | no new evidence (budget now 3/offering for 4 companies) | search results were aggregator profiles / unrelated entities |
| Wayback Machine | 2 attempts | 0 | none | connection reset by egress proxy |
| Republic campaign/update pages | 0 (not attempted again) | 0 | none | Cloudflare challenge; user-import pathway prepared instead |


## 7. What phase 2 changed

| Company | Before (phase 1) | After (phase 2) | What still is unknown |
|---|---|---|---|
| Hemster | Form D 2019 (SEC); 2 press items (2019 round, 2024 rebrand), captured only as summaries | Same press items, now preserved as raw HTML with embedded dates. Republic marked the security **converted, no cash** as of 2022-12-31; the mark is **absent** as of 2023–2025 (inconsistent) | Legal-entity link Hemster, Inc. → (Re)vive (press-reported only); registry status; why the Crowd SAFE "converted" and into what; no C-AR was ever filed |
| Up Sonder | Last SEC observation 2022-05-02 (C-AR + C-TR, no reason stated) | Company site publishes dated posts through **2026-10-05** (company claim; dates are company-controlled). Republic: no status mark 2022–2025 | Revenue/legal status after 2022; whether the posts reflect a going business |
| SkyHi | Last SEC observation 2020-05-19 (C-AR + C-TR) | Republic marks it **"insolvent, dormant, or dissolved"** from the 2023-12-31 list (published 2024-04-30), and in every list since; website fails TLS | Registry status; any recovery for holders; the date of the actual business event (the mark dates Republic's *knowledge*, not the event) |
| People First RH | Last SEC observation 2023-02-09 (C-TR citing 227.202(b)(2)) | Website still served, newest dated content **2020-10-27**; Republic: no status mark 2022–2025 | Essentially everything after the 2021 annual report (FY2021 revenue $251) |
| Janover | IPO July 2023; pooled SAFE conversions in 10-Ks | Conversion class defined (Republic Reg CF SAFEs + one $50,000 private SAFE), conversion mechanics and resale registration documented, and the disclosed amounts **conflict**. Republic marks Janover **"insolvent, dormant, or dissolved" as of 2025-12-31** although it is a listed, reporting company: a platform mark that **contradicts** SEC evidence | Shares attributable to Republic investors; shares per dollar; delivery mechanics; any investor sale proceeds |

**Net effect.** 2 of the 3 "unknown after C-TR" companies gained dated post-2022 evidence:

* SkyHi: a platform insolvency/dormancy claim.
* Up Sonder: company-published activity.

People First remains unknown. No company gained a registry record, because every registry tried was blocked from
this environment. No company gained investor cash-flow evidence.

## 8. Recommendation A — business-outcome research

**Expand, but as an outcome-first pass with a changed protocol. Detailed historical-feature extraction comes
later.**

* **Consistency.** Two cheap, dated, systematic sources now exist.
  1. Issuer SEC filings: C-U, C-AR, C-TR, Form D and later offerings. These are automated, but go dark after a C-TR.
  2. Republic's SEC-filed holdings tables, with as-of dates 2022-12-31 through 2025-12-31. They cover essentially
     every Republic offering (24/40 sampled offerings matched by an automatic name match, with known misses due to
     brand names) and give coarse status marks: insolvent/dormant/dissolved, converted, or liquidated at X¢.
* **Reliability.** These marks are *platform claims*. In the pilot, 1 of 5 contradicts SEC evidence (Janover)
  and 1 of 5 changes without explanation (Hemster). They are useful as dated signals and must not be treated as
  facts on their own.
* **Event counts.** Pilot outcome events: 54 SEC-issuer, 25 SEC-platform, 6 external. Among the 40 sampled
  offerings, at least 8 carry an insolvent/dormant/dissolved mark (6 auto-matched, plus SkyHi and A Boring Life).
  Variation therefore exists in the outcome signal, which a business-outcome study needs.
* **Follow-up.** 6.3–8.2 years from decision date to cutoff for the pilot offerings.
* **Missingness and its causes.**
  * Legal status: 0/5 recovered, because the registries are blocked here (DE CAPTCHA, CA bot protection, NY and FL
    refused). The user can do these lookups manually in a browser in about 2 minutes per company, or a paid
    registry API could.
  * Operating status: depends on company websites and press, which are weak and company-controlled.
* **Will more collection resolve the gaps?**
  * Partly yes: Republic marks and SEC filings scale automatically, and user registry lookups are cheap.
  * No for "why" and "when exactly": the mark dates Republic's *knowledge*, not the business event.
* **Cost re-estimate for the remaining 35:**
  * **Outcome-first pass: about 6–10 analyst hours.** This covers automated SEC and Republic-table parsing for
    all 4 years, a manual alias table (about 2 minutes per offering), one website check, and optional user
    registry lookups (about 2 minutes per company).
  * **The earlier 25–30-hour estimate for full historical-feature extraction is not yet justified.** Run it only
    if the outcome-first pass shows enough resolved, non-conflicting outcomes to make features worth building.
    That is a judgment on counts and conflicts, not a fixed percentage.

## 9. Recommendation B — investor-return research

**Not supportable from accessible historical sources. Business outcomes may be recoverable; investor returns are
not.**

* Investor cash flows: 0/5 offerings.
* The best case, Janover (an IPO with registered resale shares), stops at **level 1** (issuer-wide pooled
  conversions):
  * The conversion class mixes Republic SAFEs with a $50,000 private SAFE.
  * The disclosed dollar amounts conflict ($779,334 class total vs $845,224 converted).
  * There is no per-investor or per-closing conversion schedule, no investor elections, and no sale data.
  * Levels 2–5 (Republic-attributable shares, shares per dollar, tradability in practice, cash proceeds) are not
    reconstructable.
  * No proportional allocation was made, and no price history or hypothetical liquidation was computed.
* Republic's numbered liquidation footnotes ("approximate cash payout of N cents on the dollar") are the only
  security-level payoff figures found at scale. They describe Republic's own liquidation of its commission
  securities, which may be secondary sales, not crowd investors' proceeds. At most they are a weak proxy, and
  none of the five pilot offerings has one.
* **Prospective tracking as data collection:** for future offerings the user only observes or holds, record:
  * a dated deal snapshot and the contract PDF;
  * platform updates captured on their publication date;
  * for any position actually held, the user's own contribution, conversion and distribution records.
* This is a way to *collect* the return data that history does not provide. It is not a reason to invest, and
  it is not a quick substitute for historical validation: payoffs from 2026 deals will take 5–10 years to
  mature.
* Business-outcome prediction from the historical sample would remain an intermediate research task. It is not
  evidence of investment profitability.

## 10. Time and effort for this phase

* **Measured agent wall-clock** for the experiment tasks: 23 minutes (see the table above). This excludes report
  and code writing, and is not analyst time.
* **Analyst-equivalent estimate (not measured), if a person did the same work: about 5.5 hours**, within the
  6-hour budget.

| Task | Estimate (hours) |
|---|---|
| Source access probing | 0.5 |
| Finding and parsing the Republic Core/Note holdings tables across 4 filings | 1.0 |
| Janover prospectus and 10-K trace | 1.5 |
| Registry attempts | 0.5 |
| Web capture and searches | 0.5 |
| Targeted rendered-page checks | 0.75 |
| Write-up of evidence records | 0.75 |
| **Total** | **≈5.5** |

* Automated compute: the final pilot `collect` made 0 network requests (fully cached), and the Republic
  filings' PDF parsing took about 4 minutes in total.

## 11. Collection checklist for the user (optional; nothing above waits for it)

See `data/user_imports/README.md`. In short, in your own browser:

1. Save Republic campaign "Updates" for the 5 pilot companies as PDFs, noting each displayed date.
2. Look up the 4 Delaware entities on the Delaware Division of Corporations site (Hemster, Inc.; Up Sonder;
   SkyHi Travel, Inc.; People First RH, Inc.) and screenshot status and dates (public).
3. If you hold any of these: portfolio status screenshots and any conversion or share-delivery notices, redacted
   (investor-only; kept out of git).
