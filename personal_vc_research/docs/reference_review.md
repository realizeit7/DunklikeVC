# Focused reference review (first run, 2026-10-11 UTC)

Scope: decide what each starting reference can and cannot contribute to a point-in-time, return-oriented study of
Republic Reg CF offerings (2018–2020). These are research references, not endorsements. Nothing from the repositories
was executed or copied.

## Access log

| # | Reference | What was actually inspected | Access result |
|---|-----------|-----------------------------|---------------|
| 1 | Kingscrowd rating methodology (kingscrowd.com/kingscrowd-startup-rating-methodology/) | **Not the page itself.** Direct fetch → HTTP 403 (Cloudflare challenge) via both curl and WebFetch. Only secondary search snippets were seen (Kingscrowd article on sector scores, a third-party review, issuer press releases). | Blocked; **secondary-source only** |
| 2 | CapitalVX (srdas.github.io/Papers/CapitalVX.pdf) | Full PDF (13 pp., working paper 2020), sha256 `0854833d…`, cached at `data/cache/references/CapitalVX.pdf` | Full text |
| 3 | Gafrej, Gafrej & Bouzgarrou, "Predicting post-campaign scenarios of equity crowdfunded firms: a machine learning approach with interaction effect analysis", *J. Technology Transfer*, published 2026-07-03 (doi 10.1007/s10961-026-10362-7) | Crossref + OpenAlex metadata only. Springer redirects to a login/cookie wall; OpenAlex reports closed access, no abstract indexed. | **Title/metadata only — abstract and full text not seen** |
| 4 | kpzhang/VC-prediction | Shallow clone, commit `e11f33a` (2024-10-03): README, `startup_success_prediction.py`, `Model/utils.py` read (not run) | Code read; no LICENSE file |
| 5 | xisen-w/Startup-Success-Forecasting-Framework (SSFF) | Shallow clone, commit `fa7e1f5` (2025-08-31): README, DATA_CURATION_PIPELINE.md, experiment scripts read (not run) | Code read; no LICENSE file |
| 6 | Republic historical portfolio (republic.com/companies/portfolio) | HTTP 403 (Cloudflare) via curl and WebFetch; Wayback Machine (`web.archive.org`) connections reset by the egress proxy; `archive.org/wayback/available` reachable but returned no snapshot for that URL. | Blocked |

## Comparison

| Dimension | Kingscrowd ratings | CapitalVX | Gafrej et al. 2026 | VC-prediction (MGT) | SSFF |
|---|---|---|---|---|---|
| Population / stage | US Reg CF (and Reg A) deals on many portals; early stage (secondary sources) | ~943k companies in Crunchbase (Apr-2020 dump) + USPTO; all stages | Equity-crowdfunded firms (per title); platform/country/years **unknown** | Global VC-backed companies, PitchBook data (code loads `load_pitchbook`); VC rounds | "Early-stage startups"; curated Successful/Unsuccessful CSVs, provenance described as partly proprietary |
| Inputs & information timestamps | 5 sub-scores (price/valuation, market, team, performance, differentiation; names vary by source) from 170–350+ data points; weights and formula **not published**; whether ratings are frozen at campaign time is undocumented | 370 Crunchbase-derived features (founder counts, degrees, patents, funding-round timing, social links). Exit model uses a *current* snapshot ⇒ features may post-date outcomes; follow-on model uses a July-2018 snapshot vs Apr-2020 | Unknown | Time-stamped graph edges (investor–company–person) by month; features restricted to `edge_date <= t` | Free-text startup descriptions + founder profiles fed to LLMs (GPT-4o family); no point-in-time control documented |
| Target outcome | None stated as a prediction target; a quality score | 3-way exit class (IPO / acquired / closed) and "gets follow-on funding" | "Post-campaign scenarios" (per title) — details unknown | Exit (company appears in PitchBook Exit table within window) | Binary: success = raised >$500M, acquired >$500M, or IPO >$500M; failure = raised $100K–$4M without later success |
| Train/test design | Not applicable / not published | Random out-of-sample split for exits (88–90% accuracy reported); follow-on uses two snapshots | Unknown | Temporal: trains on monthly steps, tests on months 85–96 | LLM prompting on stratified subsets (10%/20% positive) — label-balanced, not time-split |
| Investor cash returns measured? | No | No (exit events only; acquisition ≠ return) | Unknown (not seen) | No | No |
| Code/data availability & licensing | Proprietary, subscription | Paper only; Crunchbase data is licensed/paid | Closed access | Code public, **no license file** ⇒ all rights reserved by default; data = PitchBook samples (proprietary) | Code public, **no license file**; data partly proprietary; requires OpenAI + SerpAPI keys |

## What transfers to our setting

* **Point-in-time discipline (VC-prediction):** the `edge_date <= t` pattern is the right idea; we implement the same
  rule on filing-acceptance dates (`historical facts eligible only if public on or before decision date`). Idea only — no code copied.
* **Two-snapshot labelling (CapitalVX follow-on model):** comparing an older snapshot with a later one is a reasonable
  way to measure *follow-on financing*; our analogue is Form D / later Form C filings dated after the decision date.
* **Feature checklist (Kingscrowd, CapitalVX):** valuation vs. comparables, team, traction/performance, and market are
  plausible feature families; Form C supplies dated versions of price terms, financials and officer histories.

## What does not transfer

* **Outcome definitions.** Every reference predicts exits, follow-on funding or ">$500M" success. None measures investor
  cash flows; an acquisition, follow-on raise or IPO is not a realized return for a Crowd SAFE holder (the instrument may
  convert, be cashed out at the purchase amount, or be wiped out).
* **Population.** VC-backed (PitchBook/Crunchbase) companies differ strongly from Reg CF issuers in size, selection and
  security terms (Crowd SAFEs, no pro-rata, no information rights beyond C-AR).
* **Leakage risk.** CapitalVX's exit model and SSFF's descriptions are not shown to be point-in-time; current
  Crunchbase/LinkedIn bios cannot establish 2018–2020 credentials.
* **LLM conviction scores (SSFF)** are out of scope for this run by specification.
* **Kingscrowd ratings** cannot be used as historical features unless dated, archived ratings are obtained; weights are
  unpublished and access is paid.

## Unknowns we did not fill in

The Gafrej et al. population, features, target definitions and design were **not observed**; nothing above about that
paper goes beyond its title and bibliographic metadata.
