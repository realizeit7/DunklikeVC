# v2 initial execution report — LLM analyst and personal investment ledger

**Run.** 2026-10-14/15 UTC on branch `llm-analyst-v2`, created from `prospective-pilot-v1`. Local commits only:
nothing was pushed, deployed, scheduled, purchased or sent, and no investment was made.

**Preserved.** The pilot clock (2026-10-14T15:16:34Z → 2027-01-12T15:16:34Z) is unchanged. So are all v1 offerings,
snapshots, facts, events and runs, and the closed historical study.

## 1. Implemented and reused

**Reused:**
* the v1 collection pipeline (no collection code was rebuilt) and the content-addressed snapshots;
* `Fetcher`/`Config`, and the append-only trigger pattern;
* `journal.add_forecast`, `forecast_status` and `brier` (forecast rules: no false before deadline + lag; Brier only
  on adjudicated forecasts);
* `text_quality`, and the contract-marker regex.

**New** (see `V2_GUIDE.md`):
* Versioned migrations (`migrations.py`).
* The budget policy, written as an explicit, versioned file (`policies/budget_policy_v1.yaml`).
* The ledger, approvals and reservations (`ledger.py`).
* The screening policy, marked UNVALIDATED (`policies/screening_policy_v1.md`).
* The prompt and schema files: `llm/prompts/analyst_prompt_v1.md`, `analyst_prompt_v1_1.md` and
  `llm/schemas_v1.py` (now `analysis_schema_v1_0_2`).
* Frozen evidence packs (`packs.py`).
* The 4-stage analysis with mechanical validation, a deterministic status and an optional repair round
  (`analysis.py`).
* Korean briefs (`brief.py`).
* Evaluation tracks and version comparison (`evaluation.py`), and spot checks (`spot_check.py`).
* The monthly v2 report (`portfolio_report.py`).
* The synthetic demo (`demo_ledger.py`).

**Migration of the live database:**
* A manual backup (`data/backups/pilot_pre_v2_*.sqlite`) and the automatic pre-migration backup were both taken.
* The migration was tested on a copy first: every v1 row was identical afterwards, the backup equalled the
  pre-migration state, and a second connect was a no-op.
* On the live database, after migration, the v1 tables equal the backup row for row.

## 2. What ran with real data and a real LLM

**Adapter.** The user's authenticated Claude Code CLI (2.1.299), called with only documented flags: `-p --tools ""
--strict-mcp-config --no-session-persistence --output-format json --system-prompt … --json-schema …
--max-budget-usd 5`. It ran in an empty temporary directory, with the pack sent on stdin.
* Model as reported by the CLI: `claude-sonnet-5-5` (with `claude-haiku-5-5` for small internal calls).
* Provider: `firstParty`.
* Total LLM cost: **$15.99** across 6 live runs.

**Frozen packs** (committed under `data/packs/`):

| Pack | Offering | Content | Gaps |
|---|---|---|---|
| `PACK-RCF-2147043-020-37424-7e1d749b1f6d` | Mightylicious | 151 pages | — |
| `PACK-RCF-2114933-020-37299-893511c4af2b` | Hope-Neuron Therapeutx | 67 pages | — |
| `PACK-RCF-2128340-020-37393-cc5d6fad73e3` | TradeFunded | XML only | the 61.7 MB PDF is not parsed (visible gap) |

**Analyst versions.** Each was registered before it ran:
* `analyst_v1_baseline`: prompt v1, no repair.
* `analyst_v1_1` (challenger): prompt v1.1 adds a rule that absences belong in `missing_information`, plus one
  mechanical repair round. TradeFunded is its **development case**, excluded from its evaluation.

| # | Offering | Version | Schema | Adapter | AI status | Validation |
|---|---|---|---|---|---|---|
| 1 | TradeFunded | baseline | v1 | claude_cli | analysis_failed | 1 error: claim A15 (an absence statement) had no citation |
| 2 | Hope-Neuron | baseline | v1 | claude_cli | **needs_information** | 0 errors. Price/cap/conversion not confirmed. Gates: evidence unknown, business unknown, price & contract **fail** |
| 3 | Hope-Neuron | v1.1 | v1 | claude_cli (+repair of A) | **needs_information** | 0 errors. Minimum investment/fees not confirmed. Gates as in #2 |
| 4 | Mightylicious | baseline | v1 | claude_cli | analysis_failed | 10 schema errors, caused by **our** input-name pattern bug (see §7) |
| 5 | Mightylicious | v1.1 | v1 | claude_cli (+3 repairs) | analysis_failed | same bug |
| 6 | TradeFunded | v1.1 | v1_0_1 | claude_cli | **needs_information** | 0 errors. Contract, terms, minimum, dated financials not confirmed. Gate 1 fail |
| 7–9 | Mightylicious | both | v1_0_1 / v1_0_2 | revalidation of stored outputs (no LLM call, $0) | analysis_failed | **Genuine model errors** once the bug was fixed. Baseline: claim A32 cites p.129, but the quote is on p.130. v1.1: one calculation formula is not valid arithmetic |

* **Forecasts recorded.** Five, all labelled `model_judgment_uncalibrated` and linked to pack, version and model.
  Four are evaluation forecasts (Hope-Neuron); one belongs to the TradeFunded development case and is excluded from
  evaluation. None is resolved; all are pending until their deadlines plus reporting lag.
* **Version comparison.** Two shared frozen packs; status agreement 2/2; 0 outcomes resolved since registration.
  Verdict: **insufficient evidence**. Nothing is promoted.
* **Same model, different misses.** The two valid Hope-Neuron runs missed different critical items: the baseline
  did not confirm price/cap, v1.1 did not confirm the minimum investment. This run-to-run variability is itself a
  finding for evaluation track 1.

## 3. Companies analysed and evidence sufficiency

None of these offerings is shown to be currently available to invest in. Availability is `unknown` because Republic
pages are not accessible, and Form C deadlines are not proof of availability.

* **Hope-Neuron Therapeutx (equity, pre-revenue).** **Needs information.**
  * Both valid runs cite the contract text, and the AI "price & contract" gate fails on documented terms:
    * an arbitrary $1.00 price, about $75M implied pre-money value;
    * a 10-year irrevocable voting proxy to the founder;
    * custodian holding, no information or anti-dilution rights;
    * $210k of convertible notes with an unknown conversion price.
  * The business evidence is issuer-only: a mouse proof-of-concept and a going-concern doubt.
* **TradeFunded (LLC units).** **Needs information.** The only substantive document (61.7 MB) is unparsed, so the
  contract, terms, minimum investment and dated financials are missing. The analysis also flags an inconsistency: the
  entity was incorporated on 2026-02-10 but reports prior-year figures.
* **Mightylicious (Crowd SAFE, revenue $459k).** **analysis_failed** under both versions; its briefs show only the
  errors. The corrective step is a fresh registered run, not repeated re-runs until something passes.

**Briefs** (`reports/briefs/`):
* Hope-Neuron: analyses 2 and 3.
* TradeFunded: analysis 6 (and the failed analysis 1).
* Mightylicious: analyses 8 and 9 (failed).

Brief bodies run about 6–7k Korean characters, with the evidence appendix and source links after them.

## 4. Live approvals or investments

**None.** The live database has 0 approvals, 0 ledger events, 0 policy acknowledgments and 0 user decisions. AI
assessments created no approval, reservation, investment or fill. Every approval and transaction example ran only in
the isolated synthetic demo database (`data/demo/`, gitignored), with step logs in `reports/demo/`.

## 5. Budget semantics and tested edge cases

Semantics: see `V2_GUIDE.md`, "Budget semantics", and `policies/budget_policy_v1.yaml`.

`tests/prospective/test_v2_ledger.py` (18 tests, synthetic) covers:
* the $1,200 issuer limit with fees and simultaneous reservations (an exact $1,200 is allowed; $0.01 over is
  blocked);
* the $12,000 annual limit across issuers, in the pre-start bucket;
* no double count when a reservation settles;
* anniversary periods, with Feb 29 → Feb 28;
* a reservation pending across a rollover, counted in P2 and settled once, with P1 unchanged;
* a refund restoring only the refunded cost, attributed to the original period, with the non-refunded fee still
  counted;
* distributions, sale proceeds, sale fees and write-offs not restoring the issuer limit;
* a round and an SPV of the same issuer sharing one limit;
* a duplicate confirmation import being idempotent;
* an expired approval releasing its reservation, with late execution flagged `APPROVAL_EXPIRED`;
* changed terms or new filings since the analysis blocking the approval (the original is preserved);
* an unknown fee making an approval `incomplete` with no reservation;
* an out-of-policy actual transaction recorded and flagged (`OUT_OF_POLICY:issuer_limit`, `NO_APPROVAL`);
* AI being unable to create approvals or ledger rows, and the policy acknowledgment being required;
* an override of a failed screen requiring a rationale, with the failed conditions stored;
* append-only rows with void corrections;
* no realized multiple for a converted position;
* migration and backup preserving v1 records.

**Synthetic demo** (`python -m prospective.demo_ledger`). It reproduces:
* a blocked pre-acknowledgment approval;
* pre-start reservations;
* a blocked same-issuer SPV;
* a settled investment with no double count (annual $1,408.50 = $500 + $8.50 fee + the $900 still reserved);
* a released reservation;
* a flagged out-of-policy transaction;
* the P2 rollover, and a distribution with no budget effect.

## 6. Tests

`pytest`: **106 passed**:
* 52 historical tests;
* 16 v1 pilot tests;
* 18 v2 ledger tests;
* 20 v2 analysis tests. These cover invalid citations, wrong pages and missing documents; unsupported statuses;
  calculation recomputation; inference basis; unverified support; statistics in forecasts; brief references;
  critique coverage; prompt injection (extra fields rejected, tools disabled, no document text on the command line);
  late and private evidence excluded from packs; tamper-evident packs; AI analyses not creating approvals; the repair
  round; and the version-comparison rules.

Synthetic tests verify logic only; they say nothing about investment performance.

**Real-source spot checks** (stored in `citation_checks`):
* **Independent extractor.** Cited quotes were re-found in the **original snapshot bytes** with poppler `pdftotext`
  rather than the pack text, for analyses 2, 3 and 6: 121 citations checked.
  * 114 matched exactly.
  * 7 matched only when spacing was ignored, because the pdfplumber text layer merges words (e.g. "TotalAssets").
  * 0 were missing.
  * (The first pass on analysis 2, before the whitespace-insensitive rule, recorded 3 of them as not found; those
    rows are kept.)
* **Semantic review** of 7 claims in analysis 2, by this agent (same model family; not independent human review):
  * 2 fully supported;
  * 5 supported, but each claim carries details from elsewhere on the page that the quote does not show (e.g. the
    10-year proxy term is on p.10, not in the quoted span).
* **Live validation** caught a real wrong-page citation (Mightylicious A32) and a real invalid formula.

## 7. Defects found during the run (fixed and recorded; failed rows kept)

1. **Prompt gap.** The model recorded "the PDF was not parsed" as a sourced claim. Prompt v1.1 adds rule 12.
   Registered as a challenger, with TradeFunded as its development case.
2. **Schema bug (ours).** The strict local pattern for calculation input names (`^[a-z_]+$`) was never sent to the
   model, because the CLI schema strips patterns. Fixed in `analysis_schema_v1_0_1`: digits are allowed after the
   first character.
3. **Validator false positive (ours).** "about 32%" was rejected although a cited calculation gives 32.1%. Fixed in
   `v1_0_2`: a percentage within 0.5 points of a number or calculation in a cited basis claim is accepted.
4. **Evaluation filter.** The forecasting track included a development-case forecast; it is now restricted to
   evaluation-split analyses.
5. **Operations.** A wait loop (`pgrep -f`) matched its own command line; it was replaced.

The original runs (1, 4 and 5) stay in the database as `analysis_failed`. Re-validations are new, labelled runs with
no LLM call.

## 8. Outstanding limitations

* **Republic is unreachable** (HTTP 403). Availability, minimum investment and investor fees must be confirmed by the
  user on the platform at approval.
* **TradeFunded's** 61.7 MB PDF is unparsed (a size limit, not a policy choice), so it stays needs_information
  unless the limit is raised or the user imports the document.
* **Inference is non-deterministic.** The same model produced different gaps on the same pack. One registered run
  per version is a single sample.
* **Cost.** About $0.6–6 per offering per run. Mightylicious (151 pages, plus repairs) was the most expensive.
* **Forecasts** cannot be scored for 6–12 months. Every comparison is "insufficient evidence" until then.
* **Semantic support** (whether a claim says more than its quote) is checked only by spot review, not mechanically.
* **Calibration.** No probability is calibrated, the screening policy is unvalidated, and a pass never means
  investment quality.
