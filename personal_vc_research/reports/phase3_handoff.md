# Phase 3 handoff — outcome coverage and label validation

**What was done.** An outcome-first pass over all 40 frozen offerings, with outcome cutoff 2026-10-10.
* **Preserved:** the frame, sample, pilot tables and earlier evidence (the manual evidence file was only
  appended to).
* **Not done:** feature extraction, models, inferred returns, push.

**Results** (full report: `reports/outcome_coverage_phase3.md`):

* **Republic holdings tables** (4 SEC filings, as of 2022-12-31 to 2025-12-31, 2,184 rows):
  * They list Republic's own ~2% commission holdings and are internally prepared and unaudited.
  * `*` is a composite "insolvent, dormant, or dissolved" platform claim, dated only as an interval.
  * Numbered notes describe Republic's liquidation of its own holding, not retail recovery.
* **Entity matching:** 34/40 offerings linked at offering level after manual review (28 exact, 6 corroborated
  brand aliases). Linen is linked at issuer level only, Gesture is ambiguous (unused), and 4 are unmatched (all
  withdrawn). No ambiguous alias is used in any label.
* **Strict labels (36 non-withdrawn):**
  * 1 `listed_public` (Janover).
  * 1 `operational_closure_documented` (Linen). This is a company announcement relayed by one outlet; legal
    dissolution is not established.
  * 34 `unresolved`, by reason:
    * reporting terminated with no later evidence: 13
    * platform adverse claim only: 8
    * no terminal evidence: 7
    * recent operating evidence only: 3
    * conflicting sources: 2
    * insolvency proceeding: 1
  * 4 offerings were withdrawn.
* **Sensitivity labels:**
  * `*` at offering level: 9
  * unobserved for more than 3 years: 23
  * conflicted: 3 (Janover `*` vs listing; Hemster `+` instability; DDL identity)
* **Legal status:** 0/40. Every registry is blocked from this environment.
* **Investor cash flows:** none recovered from accessible sources for any offering.
* **Audit** (same agent, so a second pass, not independent):
  * Random set: 55/55 agree after corrections. The first run agreed on 51/55; of the 4 discrepancies, 1 was a
    real pipeline omission (another round's C-U) and 3 came from the audit script.
  * Targeted checks: 11, all confirmed or retained as uncertain.
  * Corrections C1–C8 are logged. No definitive label changed.
* **Effort:**
  * Analyst-equivalent estimate: about 9.3 h (unit-time method; range 6.5–12 h). This is an estimate, not a
    measurement.
  * Measured: about 26 minutes of logged agent wall-clock. The log is incomplete.

**Recommendations:**
* **A (business outcomes):** do not start feature extraction or ML.
  * Next, user registry imports for the 36 completed issuers (about 1.2 h of user time).
  * Expand to the 224-offering frame (about 34 analyst-hours plus about 6 user-hours) only if those imports
    convert meaningful numbers of unresolved offerings. The expected yield is about 11 strict definitive events
    (95% interval about 3–37): descriptive base rates at best, not prediction.
* **B (investor returns):** not supportable from accessible historical sources. Only prospective, documented
  tracking could supply the data.

**Re-run:** `holdings` → `collect --only all --outcomes-only` → `adjudicate` → `audit-p3` → `report-p3`;
`pytest -q` (52 synthetic tests).

**Not authorized / not done:** pushing (local commit only), circumventing registry or platform blocks, paid
APIs.
