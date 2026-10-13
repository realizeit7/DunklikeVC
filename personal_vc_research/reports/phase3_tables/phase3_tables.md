### t1_coverage_before_after

| field | pilot n=5 (phase 2 sources, phase-3 rules) | non-pilot n=35 before phase 3 | non-pilot n=35 after | all n=40 after |
|---|---|---|---|---|
| Completion status parsed (C-U text or C-W) | 5 | 0 (not collected) | 35 | 40 |
| ≥1 post-offering SEC issuer filing recorded | 5 | 0 (not collected) | 28 | 33 |
| Last SEC-issuer observation on/after 2023-10-10 | 1 | 0 (not collected) | 2 | 3 |
| Republic holding linked at offering level (manually reviewed) | 5 | 0 (not collected) | 29 | 34 |
| Republic status mark or numbered note on the offering-level holding | 3 | 0 (not collected) | 9 | 12 |
| Dated operating evidence, any tier | 5 | 0 (not collected) | 23 | 28 |
| Dated operating evidence on/after 2024-10-10 | 3 | 0 (not collected) | 2 | 5 |
| External dated evidence item (excl. website reachability) | 3 | 0 (not collected) | 5 | 8 |
| Any observation on/after 2023-10-10 (SEC issuer, Republic mark/note, external) | 4 | 0 (not collected) | 13 | 17 |
| Legal status from a state registry | 0 | 0 (not collected) | 0 | 0 |
| Strict definitive label (listed/acquired/dissolved/closure); denominator excludes withdrawn | 1/5 | 0 (not collected) | 1/31 | 2/36 |
| Investor cash flows recovered from accessible sources | 0 | 0 (not collected) | 0 | 0 |

### t2_issuers_vs_offerings

| quantity | count |
|---|---|
| Sampled offerings | 40 |
| Unique issuer CIKs | 40 |
| Issuers with >1 Republic offering inside the 2018–2020 frame | 0 |
| Issuers with a later Form C (any platform) after the sampled offering | 12 |
| Issuers with ≥1 other Republic holding series kept at issuer level (other round) | 7 |
| Offerings whose Republic holding has >1 yearly row (repeated observations of one series) | 33 |

### t3_claims_vs_adjudicated

| platform_claim | offering | strict_label | strict_reason |
|---|---|---|---|
| * insolvent/dormant/dissolved (composite) | Boring Life Inc | unresolved | platform adverse claim only |
| * insolvent/dormant/dissolved (composite) | Genius Juice, LLC | unresolved | platform adverse claim only |
| * insolvent/dormant/dissolved (composite) | GrapeStars International, Inc. | unresolved | platform adverse claim only |
| * insolvent/dormant/dissolved (composite) | Grove Biomedical LLC | unresolved | platform adverse claim only |
| * insolvent/dormant/dissolved (composite) | Janover Ventures LLC | listed_public | 424B4 + 8-A12B |
| * insolvent/dormant/dissolved (composite) | Layali LLC | unresolved | platform adverse claim only |
| * insolvent/dormant/dissolved (composite) | Lieu Ltd | unresolved | platform adverse claim only |
| * insolvent/dormant/dissolved (composite) | Parlay App, Inc. | unresolved | platform adverse claim only |
| * insolvent/dormant/dissolved (composite) | Pigeonly, Inc. | unresolved | insolvency proceeding reported (not dissolution) |
| * insolvent/dormant/dissolved (composite) | SkyHi Travel, Inc. | unresolved | platform adverse claim only |
| * on another round only (issuer level) | Genius Juice, LLC | unresolved | platform adverse claim only |
| * on another round only (issuer level) | Linen Mobile, Inc. | operational_closure_documented | company announcement + independent report (legal dissolution not established) |
| + converted, no cash to Republic | Hemster, Inc. | unresolved | conflicting sources |
| numbered note: Republic holding liquidated/tendered | YOURVIRTUALSIM INC | unresolved | reporting terminated; no later dated evidence |

### t4a_strict_by_cohort

| strict label — reason | 2018 | 2019 | 2020 | all |
|---|---|---|---|---|
| listed_public — 424B4 + 8-A12B | 0 | 0 | 1 | 1 |
| offering_withdrawn — Form C-W; no completion report | 3 | 0 | 1 | 4 |
| operational_closure_documented — company announcement + independent report (legal dissolution not established) | 0 | 1 | 0 | 1 |
| unresolved — conflicting sources | 1 | 1 | 0 | 2 |
| unresolved — insolvency proceeding reported (not dissolution) | 1 | 0 | 0 | 1 |
| unresolved — no terminal evidence | 2 | 2 | 3 | 7 |
| unresolved — platform adverse claim only | 1 | 3 | 4 | 8 |
| unresolved — recent operating evidence only (not a terminal outcome) | 0 | 1 | 2 | 3 |
| unresolved — reporting terminated; no later dated evidence | 5 | 5 | 3 | 13 |
| all | 13 | 13 | 14 | 40 |

### t4b_sensitivity_by_cohort

| sensitivity label (not exclusive) | 2018 | 2019 | 2020 | all |
|---|---|---|---|---|
| closure_claim_weak | 0 | 0 | 1 | 1 |
| conflicted | 1 | 1 | 1 | 3 |
| insolvency_proceeding_reported | 1 | 0 | 0 | 1 |
| operating_claim_recent | 1 | 1 | 3 | 5 |
| platform_claim_adverse_issuer_level_only | 0 | 1 | 0 | 1 |
| platform_claim_converted_no_cash | 1 | 0 | 0 | 1 |
| platform_claim_holding_disposed | 1 | 0 | 0 | 1 |
| platform_claim_insolvent_dormant_or_dissolved | 2 | 3 | 4 | 9 |
| unobserved_gt_3y | 9 | 7 | 7 | 23 |
| all | 16 | 13 | 16 | 45 |

### t4c_source_presence_by_cohort

| cohort_year | sec_issuer | sec_platform_mark_or_note | external | offerings |
|---|---|---|---|---|
| 2018 | 13 | 4 | 2 | 13 |
| 2019 | 13 | 4 | 3 | 13 |
| 2020 | 14 | 5 | 2 | 14 |

### t5a_followup_by_cohort

| cohort_year | offerings | followup_min | followup_max | last_any_ge_2023_10_10 | last_sec_issuer_ge_2023_10_10 |
|---|---|---|---|---|---|
| 2018 | 13 | 7.8 | 8.6 | 4 | 0 |
| 2019 | 13 | 6.8 | 7.6 | 6 | 0 |
| 2020 | 14 | 5.7 | 6.6 | 7 | 3 |

### t5b_last_observation_year

| year of last observation (any tier) | 2018 | 2019 | 2020 | all |
|---|---|---|---|---|
| 2018 | 2 | 0 | 0 | 2 |
| 2019 | 2 | 0 | 0 | 2 |
| 2020 | 2 | 3 | 1 | 6 |
| 2021 | 2 | 1 | 2 | 5 |
| 2022 | 0 | 2 | 2 | 4 |
| 2023 | 1 | 1 | 2 | 4 |
| 2024 | 1 | 1 | 0 | 2 |
| 2025 | 0 | 0 | 1 | 1 |
| 2026 | 3 | 5 | 6 | 14 |
| all | 13 | 13 | 14 | 40 |

### t6_missingness

| field | missing | denominator | cause |
|---|---|---|---|
| legal_status | 40 | 40 | state registries blocked from this environment (DE CAPTCHA, CA bot protection, NY/FL refused); no user import |
| last_operating_evidence_date | 12 | 40 | no C-AR with revenue, no 10-K, no dated company/independent item found |
| Republic holding at offering level | 6 | 40 | 4 withdrawn offerings (no issuance), 1 issuer-level only (Linen), 1 ambiguous (Gesture) |
| investor_distributions | 38 | 40 | no issuer filing or investor document; platform notes describe Republic's holding |
| acquisition_or_listing | 39 | 40 | absence of a filing/report is not evidence of no event |
| archived campaign pages / platform updates | 40 | 40 | republic.com behind Cloudflare challenge; Wayback blocked by proxy |

### t7_conflicts

| legal_name | conflicts | strict_label | strict_reason |
|---|---|---|---|
| Hemster, Inc. | platform mark disappears in later filing (instability; not a reversal) | unresolved | conflicting sources |
| Janover Ventures LLC | platform '*' vs SEC listing/reporting evidence | listed_public | 424B4 + 8-A12B |
| DIGITAL DREAM LABS, LLC | external report names a differently-suffixed entity (identity uncertain) | unresolved | conflicting sources |

### t8a_match_class_offering_level

| best match class (rejected = candidate rejected on review) | association used | offerings |
|---|---|---|
| ambiguous | ambiguous | 1 |
| corroborated_alias | issuer_level_only | 1 |
| corroborated_alias | offering_level | 6 |
| exact | offering_level | 28 |
| rejected | unmatched | 1 |
| unmatched | unmatched | 3 |

### t8b_linkage_uncertainty

| linkage issue | count |
|---|---|
| Offering-level series via corroborated alias (brand ≠ legal name) | 6 |
| Offering-level series whose issuance month differs across filings | 12 |
| Ambiguous candidate series (never used in labels) | 2 |
| Ambiguous aliases used in any label | 0 |
| External items with identity uncertain (suffix mismatch) | 1 |

### t9_source_yield

| source | attempted (offerings or searches) | yielding usable dated evidence | note |
|---|---|---|---|
| EDGAR submissions/index (issuer filings) | 40 | 33 | automated; 0 network requests on re-run (cached) |
| Republic holdings tables (4 SEC filings, 2,184 rows) | 40 | 12 | status marks/notes on offering-level holdings |
| Company websites (35 non-pilot) | 35 | 2 | live_undated=16; unreachable_or_blocked=16; live_dated_content=2; parked_or_for_sale=1 |
| Selective web searches (phase 3) | 11 | 3 | searches -> items used |
| State registries | 4 | 0 | all blocked |
