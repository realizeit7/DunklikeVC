# Phase 2 handoff — preservation and outcome-recovery experiment (2026-10-11)

* The frozen frame and sample are unchanged: frame sha256 `702cf561…`, sample `cd1a66c7…`.
* Detailed extraction was **not** expanded to the remaining 35.
* Nothing was pushed.

## Delivered
* `reports/outcome_recovery.md`: before/after outcome table per company, event counts by source tier, field
  coverage by offering, the Janover security trace, targeted checks, time and source yield, and
  recommendations A and B.
* `reports/pilot_feasibility.md`: regenerated with clarifications covering:
  * 4 SAFE instruments read vs 1 summary;
  * availability inferred, not verified;
  * SEC-supported vs external outcomes (phase 1 was not SEC-only: 2 Hemster press items);
  * the facts-vs-observations caveat.
* `reports/phase2_targeted_high_impact_checks.csv`: 19 targeted checks, separate from the pilot second-pass audit
  (77 checks, 2 data discrepancies).
* User-import pathway: `python -m personal_vc_research import` plus `data/user_imports/README.md`, with a
  collection checklist.
* Tests: 42 passing, all on synthetic fixtures. They verify logic only.
* Exports (outside git, in `../exports/`): a git bundle, a reports/tables/config/manual export, and an evidence
  archive with SHA-256 checksums.

## Findings in one paragraph
Republic's own SEC filings (Republic Core / Republic Note holdings tables, as of 2022-12-31 to 2025-12-31) are a
new, dated, systematic outcome signal for every Republic offering:

* **SkyHi** has been marked insolvent, dormant or dissolved since the 2023-12-31 list.
* **Hemster** was marked converted with no cash as of 2022-12-31, and the mark then disappears.
* **Janover** is marked insolvent, dormant or dissolved as of 2025-12-31, which **contradicts** its SEC filings as
  a listed company.

Company websites added dated activity for Up Sonder (posts through 2026-10-05) and showed that People First's
newest content is from 2020. All registries were blocked from this environment.

For Janover, the 2020 Republic SAFE can be traced only to issuer-wide pooled conversions (level 1): the class
includes a $50,000 non-Republic SAFE and the disclosed amounts conflict. No investor cash flows exist for any
pilot offering.

## Decisions
* **A. Business outcomes:** expand with an *outcome-first* pass for the remaining 35, at about 6–10 analyst hours.
  It combines SEC filings, Republic holdings marks (all 4 years), an alias table, a website check and optional
  user registry lookups.
* **Defer the 25–30-hour detailed extraction** until that pass shows enough resolved, non-conflicting outcomes.
* **B. Investor returns:** not reconstructable from accessible historical sources. Prospective tracking is
  proposed as data collection only.
