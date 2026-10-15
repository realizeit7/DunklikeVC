# v2.1 — Republic access, four-dimension assessment, deterministic calculations, Korean brief redesign

v2.1 changes no data from v1 or v2. Earlier analyses, forecasts, packs and briefs stay as they were. v2.1 adds the
following (migration 3, with an automatic pre-migration backup).

## 1. Republic access (Workstream A)

- **Report:** `reports/republic_access_assessment.md`.
- **Log:** `reports/republic_access_attempts.csv` and table `access_attempts`.
- **Result:**
  - Plain HTTP and an ordinary headless browser both receive a Cloudflare block page (403) from this environment.
  - There is no integration with the user's own browser.
  - The supported route is **user-assisted import**: save the page in your browser, then run
    `python -m prospective import-evidence <csv>`. Template: `templates/republic_manual_import/`.
  - The importer refuses block, challenge, login and error pages, as well as cookie, HAR and token files, before
    storing anything.
  - Captures made while logged in are stored privately and excluded from exports.
- **`access-probe <url> [--method http|browser]`:** one logged attempt. It is refused while a block recorded in the
  last `block_cooldown_days` (7) is in force. There are no retries, no stealth and no CAPTCHA handling.

## 2. Analyst v2 pipeline

```
python -m prospective analyst-register-v2 <version> --description "..." [--dev-offering <id> ...] [--repair-rounds 2]
python -m prospective analyze-v2 <offering> --version <version> --pack <pack_id>
python -m prospective brief-v2 <analysis_id>
```

### Stages

| Stage | What it does |
|---|---|
| A | Claims, critical items, `valuation_inputs`, `financial_statements` |
| — | **Code** computes K1… implied-equity figures (`calc.py`) |
| B | Analysis |
| C | Critical review |
| D | Eight criterion results (BT1–BT5, PC1–PC3) and FORECAST_V2 forecasts |
| E | Structured support check of the claims behind fail/pass criteria (**model judgment**) |
| — | **Code** computes the four-dimension assessment (`assess.py`) |
| F | Korean top summary, written against the fixed assessment |

### Validation and repair

- Each stage is validated as soon as it returns.
- A failing stage gets at most `repair_rounds` repair requests. Each request carries only the explicit errors.
- Original and repaired outputs are both saved (`<stage>.json`, `<stage>_repairN.json`).
- If a stage still fails after the cap, the run stops as `analysis_failed`.
- Usage per stage and attempt goes to `stage_usage`. Cost is a CLI-estimated list-price equivalent, not a billed
  amount.

## 3. Assessment dimensions

| Dimension | Values |
|---|---|
| Assessment | `fails_current_screen`, `passes_current_screen`, `indeterminate`, `analysis_failed` |
| Evidence completeness | `sufficient_for_current_conclusion`, `material_gaps`, `extraction_incomplete` |
| Operational readiness | `available_verified`, `availability_unknown`, `unavailable_or_closed`, `not_checked` |
| Budget status | `eligible`, `ineligible`, `incomplete_cost_information` |

### Support rules (code, `assess.criterion_final`)

A model "fail" stays a failure only when all three conditions hold:

1. It has a decisive ground: a documented adverse fact, a documented contract term, a computed calculation, or an
   internal inconsistency in the documents.
2. It cites a valid claim or a computed K-id.
3. The support check marks at least one cited claim `supported`, without material overstatement.

Otherwise the criterion is `unresolved`.

### Aggregation

| Condition | Assessment |
|---|---|
| Any supported failure | `fails_current_screen` (unknowns elsewhere do not erase it) |
| All eight criteria pass and no extraction gap | `passes_current_screen` |
| Otherwise | `indeterminate` |

This aggregation is the **proposed** `screening_policy_v1_1`, which is **not acknowledged**; see
`policies/screening_policy_v1_1_PROPOSED.md`. The policy-v1 status is still written to `analysis_runs.status`, and
approvals still use it.

## 4. Calculations

`calc.implied_equity` uses issued/outstanding shares only (authorized shares are listed as excluded). It computes:

- pre-money value;
- post-money value at the offering minimum and maximum;
- fully diluted value, but only when every convertible's terms are disclosed. Otherwise it is `withheld` and the
  instruments are named.

Conflicting share counts make a result `illustrative`, with the conflict stated. Every input carries its value, unit,
as-of date, claim id and citation.

## 5. Freshness

The brief appendix shows:

- the analysis age;
- the evidence cutoff;
- the last *successful* EDGAR check (`source_checks`);
- whether new filings appeared after the cutoff. This is stated only for an interval covered by a successful check;
  otherwise it reads "not established";
- the financial-statement period end, assurance level and age;
- when the contract documents were observed;
- the latest availability observation and known outages.

## 6. Forecasts

- FORECAST_V2 covers a single event; "or" between distinct events is rejected, while threshold phrases such as "at
  or above" are allowed.
- Each forecast has a target type:
  - the event occurs;
  - the issuer announces it;
  - it is independently corroborated.
- Each forecast also has an explicit deadline, a reporting lag, allowed evidence, a rationale, assumptions, unknown
  treatment and cancellation treatment.
- A true event may resolve early. Silence is never false (enforced by a CHECK constraint).
- `forecast-flag <id> --relation flagged_compound --reason ...` records a note about an old forecast. The original is
  never changed.

## 7. Large or image-only PDFs

`target-ocr <document_id> --offering <id> --cutoff <utc> [--cap 60]` works in three steps:

1. A 100-dpi OCR page map of every page.
2. Page selection with priority contract > financials > offering terms, up to the cap.
3. 200-dpi OCR of the selected pages.

The result is a **new** pack (`pack_v1_targeted_ocr`). Unprocessed pages are listed as a pack gap, so that pack's
evidence completeness is `extraction_incomplete` unless the result is a supported failure. Both OCR passes are cached
by document hash.

## 8. Manual spot checks

`support-check-manual <analysis_id> <claim_id> --verdict ... --note ...` records a human comparison against the
source page. Briefs show it separately from the model's support check.
