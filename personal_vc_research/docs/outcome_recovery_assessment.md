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
