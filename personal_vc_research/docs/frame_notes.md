# Sampling frame: identifiers, linkage rules and reconciliation (first run)

Frozen frame: `data/frame/sampling_frame_all_candidates.csv` (sha256 `702cf561…`, frozen 2026-10-11T00:21Z).
Frozen sample: `data/sample/frozen_sample.csv` (sha256 `cd1a66c7…`). Neither was modified in the pilot phase.

## 1. Identifier schema (corrected terminology)

An earlier progress note said "Republic appears under two intermediary CIKs: OpenDeal Inc. (007-00046) …",
which put an SEC file number where a CIK was meant. The stored fields were already separate; the correct terms are:

| Concept | Example | Where stored |
|---|---|---|
| **Intermediary CIK** (EDGAR filer id of the funding portal) | `0001672732` OpenDeal Inc.; `0001751525` OpenDeal Portal LLC | frame `intermediary_cik`; offerings `intermediary_cik`; config `platform.intermediary_ciks` |
| **Intermediary SEC file number** (funding-portal registration, `007-`) | `007-00046` (OpenDeal Inc.); `007-00167` (OpenDeal Portal LLC) | frame `intermediary_file_number` (= offerings `intermediary_sec_file_number`) |
| Intermediary FINRA CRD | `283874` for both entities (filings also contain typo variants 284874, 28374, 000283874) | `data/frame/intermediary_evidence.csv` (not used for matching) |
| **Issuer CIK** | `0001805526` (Janover Ventures LLC → Janover Inc. → DeFi Development Corp.) | `issuer_cik` |
| **Offering file number** (one per Form C offering, `020-`) | `020-26437` | frame `file_number`; offerings `offering_file_number` |
| **Filing accession number** | `0001805526-20-000001` | `initial_accession`, `accession` in filings/events/sources |

Matching uses the intermediary CIK (not names). Name variants found for the two CIKs are listed with
filing counts in `data/frame/intermediary_evidence.csv` (7 name variants; 2 CIKs; 2 SEC file numbers).
The pilot audit confirmed, for 5/5 pilot offerings, that the intermediary CIK and SEC file number in the
original Form C XML equal the frame values (`reports/pilot_second_pass_audit.csv`).

## 2. Linkage rules

* **Offering-level** (same issuer CIK + same `020-` file number): C/A, C-U, C-W.
  *Guard:* a C/A or C-U under the same file number that names a non-Republic intermediary is **not**
  treated as an amendment; it is listed in `foreign_intermediary_accessions` and flagged for review.
* **Issuer-level** (same issuer CIK, any file number): C-AR, C-AR/A, C-TR, Form D, later Form C,
  Reg A, S-1/424B4/8-A12B/10-K. Annual reports and terminations are issuer obligations; issuers file them
  under whichever file number they choose (see CricClubs below).
* Issuer-level events are attributed to an offering with `attribution_level = issuer`. Security-specific
  payout or contract events are never copied to other offerings of the same issuer; when a disclosure
  pools several security classes (Janover's SAFE conversions), it is recorded once with its pooled scope.

## 3. Same-day initial filings and withdrawals (2 cases in candidates; neither sampled)

| Issuer | Filings | Evidence | Treatment |
|---|---|---|---|
| Alpha'a, Inc. (CIK 1794484) | Form C 020-25938 and Form C 020-25939, both 2019-12-13; C-W for 020-25939 the same day | Identical structured terms (Crowd SAFE, target $25,000, max $1,070,000, deadline 2020-03-13, price $1.00, same revenue); all later C/A, C-U, C-AR, C-TR on 020-25938 | **Replacement/duplicate filing** — 020-25939 excluded as duplicate of 020-25938; not a distinct round |
| CricClubs Inc (CIK 1807742) | Form C 020-26272 and 020-26273, both 2020-03-30; C-W for 020-26273 same day | Identical structured terms (target $100,000, max $1,000,000, deadline 2020-07-31); C-U on 020-26272; but C-AR ×3 (2025) and C-TR (2025-08-29) were filed under the *withdrawn* 020-26273 | **Duplicate filing**, 020-26273 excluded. The later C-AR/C-TR are issuer-level filings attached to the wrong file number — the reason annual reports/terminations are linked by CIK |

Rule (implemented in `frame.build_frame`, tested): same CIK + same filing date + one filing withdrawn on that
date while a sibling is not withdrawn ⇒ the withdrawn one is a duplicate. Other withdrawn offerings remain
in the frame (withdrawn ≠ excluded).

## 4. Cross-platform cases

| Case | What the filings show | Frame treatment |
|---|---|---|
| R3 Printing, Inc. 020-24160 (in frame, not sampled) | Initial Form C 2018-04-11 via OpenDeal Inc.; C-U 2018; then 12 C/As 2020-2024 naming StartEngine Capital under the **same** file number | Republic offering kept; StartEngine C/As not linked as amendments; flagged `needs_manual_review` |
| SmartSoda Holdings 020-25814 (not in frame) | Initial Form C 2019-10-31 via StartEngine; two C/As in Sept 2020 name OpenDeal Portal LLC | Excluded: intermediary at initial filing (and at day 30) was StartEngine. The issuer's own Republic offering (020-26810, initial Form C 2020-08-24, accession 0001445866-20-001267) is in the frame; the Sept-2020 OpenDeal-named C/As sit under the old StartEngine file number 020-25814 and are therefore not linked to 020-26810 (likely filer-agent error; unresolved) |
| Banaia, Inc. (in frame) | C/As filed by filer agents under OpenDeal Portal LLC while the original named OpenDeal Inc. | Same platform (both Republic CIKs) — linked normally after the first-run fix |

Platform at decision time for the five pilot offerings: all initial Form Cs and all C/As dated on or before
the decision date name a Republic intermediary CIK (audit check `xml_vs_dera:commissionCik`, 5/5).

## 5. What the completeness cross-check did and did not establish

**Sources and queries**
1. SEC DERA *Crowdfunding Offerings Data Sets*, quarterly zips 2017Q1–2026Q3 (39 zips; download log with sha256 in
   `data/frame/dera_download_log.csv`). Frame query: `SUBMISSION_TYPE == 'C'` AND filing date 2018-01-01…2020-12-31
   AND intermediary CIK ∈ {0001672732, 0001751525}.
2. SEC EDGAR full-text search (`efts.sec.gov/LATEST/search-index`), query `"OpenDeal"`, `forms=C`, one query per
   calendar year 2018, 2019, 2020, all result pages; kept hits whose `form == 'C'` (distinct accessions).

**Counts**
* DERA frame candidates: **244** initial Form Cs (2018: 48, 2019: 69, 2020: 127).
* Full-text search: **245** distinct Form C accessions mentioning "OpenDeal".
* Matched: **244**. Unmatched in FTS but not in frame: **1** — Desert Farms Inc. (0001676476-19-000002, 2019-09-03);
  its Form C names **SI Securities, LLC** (CIK 0001603038) as intermediary, so the text mention of OpenDeal is
  incidental (e.g., a prior offering). Correctly excluded. Unmatched in frame but not in FTS: **0**.
* Results: `data/frame/fts_crosscheck.csv`.

**What this supports.** The two SEC-derived routes agree on the set of initial Form Cs that name a Republic
intermediary in 2018–2020. That is reconciliation of two derivatives of the same EDGAR corpus, not proof of
completeness.

**Remaining limitations**
* Both routes depend on EDGAR; an offering hosted on Republic whose Form C named another intermediary, or a
  paper/misfiled Form C, would be missed by both.
* FTS relies on the literal text "OpenDeal"; DERA relies on the structured intermediary block. A Form C with a
  blank/garbled intermediary block and no "OpenDeal" text would be missed by both.
* Offerings that moved *to* Republic after the initial filing (SmartSoda pattern) are excluded by design.
* Republic's own historical listings could not be compared: `republic.com` is behind a Cloudflare challenge and
  the Wayback Machine is unreachable from this environment.
* The universe is therefore "initial Form Cs naming a Republic intermediary CIK", not "everything Republic hosted".
