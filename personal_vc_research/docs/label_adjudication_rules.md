# Outcome evidence fields and label-adjudication rules (phase 3)

These rules were written **before** they were applied to the 40-offering pass, and are implemented in
`personal_vc_research/adjudicate.py`. They separate *evidence* from *research labels*, and a strict label set
from a sensitivity set that keeps weaker claims.

## A. Evidence fields (one row per offering; all dated and sourced)

| Field | Admissible sources | Notes |
|---|---|---|
| `legal_status` | State registry records only, imported by the user via `data/user_imports` (entity number, jurisdiction, verbatim status, URL, capture date) | Otherwise `not_accessed`. "Active" ≠ operating; administrative dissolution ≠ investor loss |
| `last_operating_evidence` (+ date, tier) | C-AR with revenue > 0 or Exchange Act 10-K (SEC-issuer); independent report naming the entity (external); company-published dated content (external, weak) | A live, undated website is **not** operating evidence; a failed website is not closure |
| `financing_events` | Form D (notice only), later Form C, Reg A filings; independent reports | Counts and dates; a filing ≠ money raised |
| `acquisition_or_listing` | 424B4 + 8-A12B (listing); acquirer/issuer filing or ≥2 independent reports naming the legal entity (acquisition) | Payout to investors unknown unless documented |
| `security_conversion_or_disposal` | Issuer filings (strong); Republic `+` mark (platform claim: Republic's commission holding converted, no cash); Republic numbered notes (platform claim: Republic's holding liquidated/repurchased at N¢/$) | Applies to the offering only if the holding row is associated at offering level |
| `investor_distributions` | Issuer filing or user-provided investor document showing a distribution/repurchase **to retail holders** | A Republic note that the "issuer elected to repurchase outstanding Crowd SAFEs" is a **platform claim** (sensitivity only); Republic's recovery ≠ retail recovery |
| `platform_reported_status` | Republic `*` mark, verbatim: "To Republic Crowd-Invest's knowledge the issuer is insolvent, dormant, or has dissolved and Republic Crowd-Invest does not expect to receive any cash proceeds as a result of its securities holdings." | **Composite** claim: no component (insolvent vs dormant vs dissolved) is chosen. The event time is an **interval**: (last as-of date without the mark, first as-of date with it]; if first listed already marked: (unknown, first as-of] |
| `conflicts_uncertainty` | Any pair of sources that disagree; mark instability; alias ambiguity; inconsistent table dates | Conflicting claims are both retained |

Republic holdings rows are filer claims in SEC-hosted documents (internally prepared, unaudited); they are
**not** independent SEC verification. Repeated yearly rows of one issuance are one series (repeated
observations, not independent events). A disappearing mark does not establish recovery, reversal or a new event.
A missing mark does not establish a healthy company. An unlisted holding is not evidence of anything.

## B. Entity association (prerequisite for using a holdings claim)

* `exact`: listed label = documented issuer name (legal, DERA alias, EDGAR current/former), issuance month in the
  offering window (initial Form C … C-U close + 3 months).
* `corroborated_alias`: label matches the issuer's own documented website/brand (Form C website field or the
  Form C's self-reference), month in window, capital raised within 0.6–1.25× the C-U closing amount.
* `ambiguous`: anything weaker (prefix/brand only, amount or date inconsistent, several candidate series).
* `unmatched`.
Offering-level use requires `exact` or `corroborated_alias` **and** the date in window. Rows for other rounds of the
same issuer are kept at **issuer level**. Ambiguous matches are never used in labels.

## C. Strict outcome set (definitive labels only)

| Label | Requirement |
|---|---|
| `listed_public` | Issuer 424B4 and 8-A12B (SEC-issuer) |
| `acquired` | Acquirer/issuer filing, or ≥2 independent sources naming the legal entity |
| `dissolved_or_liquidated_documented` | Registry record (verbatim dissolved/cancelled/forfeited) **or** issuer C-TR citing 17 CFR 227.202(b)(5) |
| `operational_closure_documented` | Company announcement of shutdown/wind-down **and** ≥1 independent report of it, with the brand linked to the legal issuer through a documented identifier (e.g. the Form C website) — legal dissolution NOT implied *(rule added 2026-10-13 before application; the original spec lists "confirmed operational closure" as an outcome event)* |
| `offering_withdrawn` | Form C-W and no completion report; excluded from business-outcome denominators |
| `unresolved` | Everything else, with a reason code |

A definitive adverse label may **never** rest on a Republic mark, a dead website, a C-TR, or missing filings.
An offering with a conflicting source pair is excluded from strict labels that depend on the conflicting claims.

## D. Sensitivity set (weak claims, reported separately)

| Label | Requirement |
|---|---|
| `platform_claim_insolvent_dormant_or_dissolved` | Republic `*` on an offering-level holding, no conflicting SEC/registry evidence |
| `platform_claim_adverse_issuer_level_only` | `*` only on another round of the same issuer |
| `platform_claim_converted_no_cash` | Republic `+` on the offering-level holding |
| `platform_claim_holding_disposed` | Republic numbered liquidation/repurchase note on the offering-level holding (cents on the dollar recorded) |
| `operating_claim_recent` | Company-published or independent dated activity within 24 months before the cutoff |
| `unobserved_gt_3y` | No observation from any tier within 3 years before the cutoff |
| `conflicted` | Any conflicting pair (kept, never resolved by force) |

## E. Implementation notes recorded after application (no rule changed)

* A Republic holding listed **without** a mark or numbered note is not counted as an observation of the issuer
  (it follows from section A: a listing is not evidence about the issuer). The first implementation counted it;
  corrected as C5 in `reports/phase3_audit_corrections.csv`.
* Yearly rows of one holding are joined on (normalized label, capital compared numerically); see correction C3.
