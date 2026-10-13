# Statistical interpretation review (phase 4)

Phase 3 projected about 11 strict events in the full frame (95% Wilson interval about 3–37), and about 50
platform-`*` events (interval 28–83). This note reviews those numbers. **Both projections and both intervals are
withdrawn.** Only the observed counts below are retained.

## What the phase-3 calculation did

* **Numerator:** 2 strict definitive labels (Janover `listed_public`, 2020 cohort; Linen
  `operational_closure_documented`, 2019 cohort).
* **Denominator:** 36, the 40 sampled offerings minus 4 with a Form C-W and no C-U.
* **Withdrawn offerings:** removed from the denominator. Then 224 × 36/40 ≈ 202 "non-withdrawn" frame offerings
  was multiplied by 2/36, giving 11.2. This applied the sample's overall withdrawal share to every cohort.
* **Sampling weights:** **none.** The sample is year-stratified (13/13/14) but the frame is not (40/64/120). The
  sampling fractions are 32.5%, 20.3% and 11.7%, so an unweighted ratio over-represents the 2018 cohort.
  * With stratum weights N_h/n_h (40/13, 64/13, 120/14), the same two labels project to
    0 + 1×64/13 + 1×120/14 ≈ **13.5**, not 11.2.
  * Withdrawn offerings project to about 17.8 (3 in 2018, 1 in 2020), not 22.4.
* **Interval:** a Wilson score interval for a single binomial proportion. It assumes:
  * simple random sampling (false here: the sample is stratified);
  * independent, identically ascertained outcomes;
  * an infinite population (no finite-population correction).

## Why it cannot be justified

1. **Too few events.** Each stratum contains 0 or 1 event. Stratum variance estimates are degenerate (zero), and
   no design-based interval with useful coverage is available for 2 events spread across 3 strata.
2. **The quantity is ascertainment, not occurrence.** A strict label requires that a specific kind of evidence was
   *found and accessible* through this collection route (issuer 424B4 + 8-A12B; company announcement plus a
   report). Ascertainment depends on the outcome type and the cohort:
   * listings leave SEC filings;
   * quiet failures leave nothing;
   * registries were blocked.
   The observed rate is a property of the collection process, so it cannot be read as the frequency of business
   outcomes, and it is likely selective.
3. **Composite sensitivity events.** The `*` projection multiplies a composite, platform-reported, interval-dated
   claim. It inherits all of the above and adds entity-matching uncertainty.

## What is retained (observed counts only; not population base rates)

| Cohort | Sampled | Form C-W, no C-U | Issuer-reported close (C-U) | Strict definitive label | Offering-level `*` (sensitivity) |
|---|---|---|---|---|---|
| 2018 | 13 | 3 | 10 | 0 | 2 |
| 2019 | 13 | 0 | 13 | 1 (Linen, closure) | 3 |
| 2020 | 14 | 1 | 13 | 1 (Janover, listing) | 4 |
| All | 40 | 4 | 36 | 2 | 9 |

If a projection is ever quoted, it must:
* be called a **projection of ascertainable labels under the current collection process**;
* use stratum weights;
* show its counts, never just a rate.

It is not an estimate of how often businesses fail, close, list or are acquired.

## Platform-mark timing (correction)

* **What phase 3 did.** It dated a Republic `*` as an interval (last unmarked as-of date, first marked as-of
  date]. That interval brackets the **first appearance of the mark in Republic's lists**. It does not bracket the
  underlying business event.
* **Why the event can be earlier:**
  * Republic's knowledge can lag the event by any amount.
  * An earlier unmarked row does not establish that the event had not yet occurred.
* **What changed.**
  * The field is now `star_first_report_window`, and the evidence text reads "mark first-appearance window …;
    underlying event date unknown, may precede it".
  * The rules doc is updated to match.

## "Completed" and "withdrawn" wording (clarification)

* **The 36 non-withdrawn offerings.** Each has a Form C-U in which the issuer states that the offering closed
  successfully or reports amounts raised. These are **issuer-reported closes**, often with the phrase "although a
  final accounting has not taken place". They are not independently verified completions or issuances.
  * For 34 of them, a Republic commission holding is listed at offering level. That is consistent with securities
    being issued, but it is a platform claim.
  * The table code `completion_reported_C-U` is kept. Prose should say "issuer-reported close".
* **The 4 withdrawn offerings** (SmarterD, Avoke, BX Spaces, Organic Amazon). Each filed a Form C-W
  (re-retrieved in phase 4). The C-W contains only:
  * the issuer;
  * the file number;
  * signatures and a date.
  It gives no reason and says nothing about commitments, cancellations or refunds.
  * None of the 4 filed any later C-U, C-AR or other offering filing, and none appears in Republic's holdings
    tables.
  * So **no evidence was found that securities were issued**. Whether investment commitments were received (and
    then cancelled or returned) **remains unknown**.
  * It is not established that they "never accepted investments".
