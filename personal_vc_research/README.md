# personal_vc_research — Republic Reg CF 2018–2020 data-feasibility study

A small, reproducible pipeline that asks one question: can we reconstruct what a small investor could know and buy
on Republic (US Reg CF) at a fixed decision date, and connect it to later outcomes and investor cash flows?
This is a **feasibility study**. It is not a trading system or recommender, and it trains no model.

Main outputs:
* `reports/pilot_feasibility.md`: the pilot report and recommendation.
* `docs/reference_review.md` and `docs/frame_notes.md`: reference review, identifiers, linkage rules and
  completeness limits.

## Setup

```bash
pip install -r requirements.txt          # pandas, requests, PyYAML, pdfplumber, pypdfium2, pytest
sudo apt-get install -y tesseract-ocr poppler-utils   # only for the `ocr` command / pdftotext fallback
export SEC_USER_AGENT="personal_vc_research your.name@example.com"   # required by SEC fair-access policy
```

SEC requests send `SEC_USER_AGENT`. It is read from the environment and never written to the repository. Without
it, any command that needs sec.gov exits with code 3 and prints the setup line above.

## Commands (run from this directory)

```bash
python -m personal_vc_research discover --config config.yaml   # DERA zips -> frame; refuses if frozen hash changes
python -m personal_vc_research sample   --config config.yaml   # seed-42 stratified 13/13/14 sample; refuses to overwrite
python -m personal_vc_research ocr      --config config.yaml [--batch N]   # planned OCR batches (<=10 pages)
python -m personal_vc_research collect  --config config.yaml --only pilot  # or --only all / comma-separated ids
python -m personal_vc_research audit    --config config.yaml --only pilot  # second-pass audit (or --only audit)
python -m personal_vc_research screen   --config config.yaml   # native-text quality screen of all 40 Form Cs
python -m personal_vc_research import   --config config.yaml   # validate user-provided browser evidence (data/user_imports/)
python -m personal_vc_research report   --config config.yaml   # pilot_feasibility.md, outcome_recovery.md, manual_review_queue.csv
pytest -q
```

All downloads are cached under `data/cache/` (gitignored) and logged in `data/manifests/retrieval_manifest.jsonl`
with URL, retrieval time, SHA-256 and status. Re-runs reuse the cache: the final pilot `collect` made 0 network
requests. To rebuild the cache, run the commands above; the manifest lists every URL.

## Frozen study configuration (`config.yaml`)

* Cohort: initial Form C filed 2018–2020, naming a Republic intermediary. Intermediary CIKs are `0001672732`
  (OpenDeal Inc., SEC file 007-00046) and `0001751525` (OpenDeal Portal LLC, SEC file 007-00167).
* Securities: equity, SAFE, convertible note. Excluded: crypto token/DPA, revenue share, pure debt, real estate,
  fund/SPV. Each exclusion is listed with its reason in `data/frame/excluded_candidates.csv`.
* Decision date: initial Form C filing date + 30 days. The date is never shifted.
* Outcome cutoff: 2026-10-10, the run's UTC start date.
* Seed 42; sample 40 (13/13/14); pilot 5; audit set 5.
* Budgets:
  * 10 relevant documents per offering (index records excluded) and 3 web searches per offering.
  * OCR: 30 pages per offering, 60 minutes in total, 10 pages per batch.
  * HTTP: 4 requests/s to SEC; 1,500 requests per command.

## Data layout

| Path | Content |
|---|---|
| `data/frame/` | DERA download log, intermediary evidence, all candidates, eligible frame, exclusions, linked filings, FTS cross-check, `frame_freeze.json` |
| `data/sample/` | `frozen_sample.csv` (40, with pilot and audit flags) and `sample_freeze.json` |
| `data/manual/` | Analyst inputs with provenance: `pilot_manual_facts.csv` (page locators, method, verification status, excerpts), `ocr_page_plan.csv`, `outcome_evidence_manual.csv`, `web_search_log.csv`, `document_probes.csv` |
| `data/tables/*_pilot.csv` | offerings, facts, sources, outcome_events, payout_evidence, cash_flows (empty: none documented), issuer_filings |
| `data/tables/ocr_log.csv` | per-page OCR status, batch, rationale and seconds |
| `data/tables/form_c_text_screening.csv` | native-text quality of all 40 sampled Form C documents |
| `reports/` | `pilot_feasibility.md`, `pilot_second_pass_audit.csv`, `manual_review_queue.csv`, `handoff.md` |
| `data/manual/` (phase 2) | `phase2_time_log.csv`, `phase2_source_yield.csv`, `janover_security_trace.csv`, Republic holdings marks in `outcome_evidence_manual.csv` |
| `data/user_imports/` | optional user-captured evidence: public register (committed), raw files and investor-only items (gitignored) |
| `reports/outcome_recovery.md` | phase-2 before/after outcome report, field coverage by offering, recommendations A/B |
| `reports/phase2_targeted_high_impact_checks.csv` | targeted checks (separate from the random audit) |
| `tests/` | invariant tests on **synthetic** fixtures only (they verify logic, not real-data accuracy) |

Facts record their economic period, public-availability date and retrieval date separately, together with
`eligible_at_decision`, `source_id` and a page or field locator. Missing values are rows with a `missing_reason`,
never 0.

## Limitations (read before using any number)

* **Sources.**
  * SEC EDGAR and DERA data were the only fully accessible primary sources.
  * Unreachable from this environment: `republic.com` (Cloudflare challenge), the Wayback Machine (connection
    reset by the egress proxy), Kingscrowd (HTTP 403), and Springer full text (login wall).
  * The run therefore under-observes platform-side company updates and investor distributions. Phase 1 used SEC filings plus 2 press articles (Hemster). Phase 2 added Republic's own SEC-filed holdings marks and company websites (`reports/outcome_recovery.md`).
* **Frame completeness.** DERA and EDGAR full-text search agree (244/245, with one explained mismatch). That is
  reconciliation within EDGAR, not proof that every Republic-hosted offering is included. See
  `docs/frame_notes.md`.
* **Availability at decision** is inferred from filings, not verified against an archived campaign page.
* **PDF text.** 22/40 sampled Form C documents have garbled text layers and need OCR. Only the 5 pilot offerings
  were extracted. Pages never OCR'd are "not extracted within budget", not "not disclosed".
* **Returns.** No real return was calculated. No investor cash flow was documented for any pilot offering.
  `returns.py` is exercised only on labelled synthetic fixtures.
* **Second pass.** The audit was run by the same agent that extracted the facts, so it is not independent
  validation. Real-data accuracy evidence = `reports/pilot_second_pass_audit.csv` (random/pilot audit) +
  `reports/phase2_targeted_high_impact_checks.csv` (targeted). Synthetic tests (`pytest`) verify logic only.
  For any full-40 expansion, audit the frozen random set in `data/sample/sample_freeze.json` without replacement.
* **Evidence preservation.** Raw cached sources are not in git. The exported evidence archive (see
  `exports/` from the phase-2 handoff) keeps the documents behind every manually verified fact; do not assume a
  re-download reproduces the same bytes (web pages and platform tables change).
* **Process disclosure.** In the first session, a command to fetch all 40 sampled Form C PDFs for text screening
  was rejected by the user. The retrieval manifest nevertheless shows 31 distinct PDF URLs were downloaded
  (00:36–00:43 UTC) before the process stopped. They were kept in the cache, and later reused only after the user
  explicitly authorized that screening.
