# Handoff — first run, pilot phase (2026-10-11)

## Implemented and actually executed
* `discover` → frame of **244** initial Republic Form Cs (2018: 48, 2019: 69, 2020: 127). **224** are eligible and
  **20** excluded with reasons: 10 crypto/DPA, 7 real estate, 1 pure debt, 2 same-day duplicate filings. The frame
  is frozen (sha256 `702cf561…`).
* `sample` → 40 offerings, seed 42 (2018: 13, 2019: 13, 2020: 14; 38 Crowd SAFE and 2 LLC-unit equity). Frozen
  (sha256 `cd1a66c7…`) and unchanged in the pilot phase.
* `ocr` → 84 targeted pages over 3 garbled pilot documents, 155 s total, in batches of at most 10 pages, each
  with a recorded rationale.
* `collect --only pilot` → 5 offerings, 403 facts (256 eligible at the decision date), 53 outcome events,
  90 sources, a payout-evidence table, and an empty cash-flow table (nothing documented).
* `audit --only pilot` → 77 checks and 2 discrepancies, both real data issues rather than extraction errors.
* `screen` → native-text screen of all 40 sampled Form Cs: 22 garbled, 15 readable, 3 partial.
* `report` → `reports/pilot_feasibility.md` and `reports/manual_review_queue.csv` (31 items).
* `pytest -q` → **36 passed**, all on synthetic fixtures. Covered: point-in-time eligibility, amendment and round
  linkage, same-day duplicates, cross-intermediary guard, missing ≠ 0, C-TR ≠ failure, acquisition ≠ return,
  outstanding ≠ zero return, deterministic sampling, frozen-cohort protection, return-math edge cases, OCR guards.

## Not done in this phase
* Detailed extraction for the 35 non-pilot offerings (screening only).
* The 5-offering audit set designated in `sample_freeze.json` (the pilot was audited instead).
* `reports/first_run.md` for all 40.
* Any real return calculation: no qualifying cash flows were recovered from accessible sources.

## Recoverable / not recoverable (pilot evidence)
| Layer | Pilot result |
|---|---|
| Point-in-time Form C content (terms, cover financials, officers, statements) | 5/5 recoverable; 3/5 need OCR |
| Day-30 availability | 5/5 inferred open from filings; 0/5 verified (no archived campaign page) |
| Contract key terms | 5/5 offerings: 4 underlying SAFE instruments read; 1 (Hemster) from offering summary only |
| Founder facts (dated 3-year roles from Form C) | 5/5 officers listed; prior exits 0/5 (not a Form C field) |
| Completion amount (C-U) | 5/5 |
| Later business events (SEC) | 5/5 have some; 3/5 unobserved for over 3 years after a C-TR |
| Investor payout evidence | 1/5, non-cash and pooled (Janover SAFE conversions to listed shares); 4/5 none found (unknown) |
| Complete investor returns | 0/5 |

## Reproduce
```bash
cd personal_vc_research
export SEC_USER_AGENT="personal_vc_research your.name@example.com"
python -m personal_vc_research discover --config config.yaml
python -m personal_vc_research sample   --config config.yaml
python -m personal_vc_research ocr      --config config.yaml
python -m personal_vc_research collect  --config config.yaml --only pilot
python -m personal_vc_research audit    --config config.yaml --only pilot
python -m personal_vc_research screen   --config config.yaml
python -m personal_vc_research report   --config config.yaml
pytest -q
```

## Remaining blockers
1. Republic pages (Cloudflare), the Wayback Machine (connection reset), and Kingscrowd and Springer (403/login)
   are unreachable from this environment.
2. No free, repeatable source of post-C-TR company status has been tested yet.
3. Investor-level payout data is absent from public sources.
4. 22/40 sampled PDFs need OCR, and every OCR'd number needs page verification.

## Message to the spec author (paste-ready)

> First-run pilot done. Five frozen Republic Reg CF offerings (2018–2020) were traced end-to-end from SEC data; the
> frozen 224-offering frame and 40-offering sample are unchanged.
>
> **Findings**
> 1. Point-in-time reconstruction mostly works:
>    * Form C XML, the memorandum PDF and dated C/As give terms, cover-page financials, dated officer histories and
>      reviewed statements.
>    * Eligibility by publication date is enforced and tested.
>    * Day-30 availability can only be *inferred* from filings; no archived campaign page was reachable.
>    * Financials are 5–13 months stale at filing.
>    * 22/40 sampled Form C PDFs (12/13 from 2018) have garbled text layers. Targeted OCR (≤30 pages per offering,
>      about 2 s per page) recovered terms, officers and statements for 3/3 garbled pilot documents.
> 2. Contract interpretation works at key-term level (5/5 Crowd SAFEs):
>    * Caps $5M–$20M; discounts none, 10% or 20%.
>    * Company-option conversion above a $1M or $2M equity financing; cash-out at liquidity events; no repurchase
>      right.
>    * Valuing the SAFE still depends on the next private round's terms, which are not public.
> 3. Business events are traceable for 1–3 years:
>    * C-U closing amounts 5/5, C-ARs 4/5, Form Ds 4/5, C-TRs 4/5 (one states 227.202(b)(2)), and one Nasdaq IPO.
>    * After a C-TR the SEC trail ends: 3/5 are unobserved for more than 3 years, so their status is unknown.
>    * External evidence: 2 Hemster press articles (bounded web search); all other outcome evidence is SEC-supported.
> 4. Investor payout evidence:
>    * Janover (1/5) reported pooled SAFE-to-common conversions in its 10-Ks: 218,772 shares in Oct 2022, then
>      165,861 shares at the July 2023 IPO (20,733 after a 1:8 reverse split).
>    * The other 4/5 have none found (unknown, not zero).
>    * No investor cash flows were recovered from accessible sources, and no real return was computed.
>
> **Recommendation:** option 2, modify collection before expanding, and scope the expansion to business outcomes.
> * Changes needed: automated page targeting and verification for garbled PDFs, and one free non-SEC status source
>   per offering (e.g. a state registry) to resolve post-C-TR status.
> * Stop condition: if "unknown" is still the most common post-offering status after that change, stop historical
>   outcome work and switch to prospective collection of the user's own deals and cash flows.
>
> **Questions for you**
> * (a) Is a state-registry lookup acceptable as the added outcome source?
> * (b) Can the user view Republic campaign and update pages in their own browser, so that dated snapshots can be
>   recorded manually?
> * (c) Should the second-pass audit set be the frozen random 5 (`sample_freeze.json`) when expanding?


_Phase 2 (outcome recovery) supersedes parts of this handoff: see `reports/outcome_recovery.md` and `reports/phase2_handoff.md`._
