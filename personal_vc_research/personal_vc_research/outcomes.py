"""Outcome-event classification rules and per-offering outcome summaries.

Rules encode the study's interpretation limits:
* C-U closing amounts = completion evidence, not investor profit.
* Form D = a securities-offering notice; it does not prove the amount was raised or closed.
* C-TR = reporting termination; never business failure by itself.
* IPO/listing or acquisition evidence is not a positive investor return.
* Absence of evidence is "not found within budget", never "confirmed absent".
"""
from __future__ import annotations

import datetime as dt

# form -> (event_type, evidence_strength, note)
FORM_RULES = {
    "C-AR": ("annual_report_filed", "filing_evidence", "Annual report filed (issuer-level reporting activity)."),
    "C-AR/A": ("annual_report_filed", "filing_evidence", "Amended annual report filed."),
    "C-TR": ("reporting_termination", "filing_evidence",
             "Reg CF reporting termination; NOT evidence of business closure or failure."),
    "D": ("securities_offering_notice_form_d", "filing_evidence",
          "Form D notice of exempt offering; does not prove amount raised or round closed."),
    "D/A": ("securities_offering_notice_form_d_amendment", "filing_evidence", "Form D amendment."),
    "C": ("follow_on_reg_cf_offering_filed", "filing_evidence", "New Reg CF offering (Form C) filed."),
    "1-A": ("reg_a_offering_filed", "filing_evidence", "Reg A offering statement filed (not proof of sale)."),
    "1-A-W": ("reg_a_offering_withdrawn", "filing_evidence", "Reg A offering statement withdrawn."),
    "S-1": ("registration_statement_filed", "filing_evidence", "S-1 registration statement filed (not proof of IPO)."),
    "424B4": ("ipo_prospectus_final", "filing_evidence",
              "Final prospectus (424B4); with 8-A12B indicates exchange listing. Not an investor return."),
    "8-A12B": ("exchange_registration_8a12b", "filing_evidence", "Exchange-listing registration of a class."),
    "10-K": ("periodic_report_10k", "filing_evidence", "Exchange Act annual report (public reporting company)."),
    "15-12G": ("exchange_act_deregistration", "filing_evidence", "Deregistration under Exchange Act."),
    "C-W": ("offering_withdrawn", "filing_evidence", "Offering withdrawn (Form C-W)."),
}


def classify_filing(form: str, file_number: str, offering_file_number: str) -> tuple[str, str, str]:
    """Map an issuer filing to an outcome event type. Returns ('', '', '') for ignored forms."""
    if form == "C" and file_number == offering_file_number:
        return "", "", ""  # the offering itself
    if form == "C-U" and file_number != offering_file_number:
        # phase-3 audit correction: another Reg CF round's progress/completion report is a dated issuer observation
        return ("other_reg_cf_offering_progress_reported", "filing_evidence",
                "Form C-U for another Reg CF offering of the issuer (progress/completion of that round; not proof of funds received).")
    if form == "C/A" and file_number != offering_file_number:
        return "", "", ""  # belongs to another offering; its own C is the event
    if form == "C-U":
        return "", "", ""  # handled from DERA progress text
    return FORM_RULES.get(form, ("", "", ""))


SEC_ISSUER = {"filing_evidence", "issuer_reported_financials", "sec_index"}
SEC_PLATFORM = {"platform_claim_in_sec_filing"}
OPERATING_TYPES = {"operating_activity_reported", "operating_activity_independent_report", "periodic_report_10k",
                   "operating_activity_company_claim"}


def source_tier(strength: str) -> str:
    """sec_issuer | sec_platform | external — kept separate in every summary."""
    if strength in SEC_ISSUER:
        return "sec_issuer"
    if strength in SEC_PLATFORM:
        return "sec_platform"
    return "external"


TERMINAL_PRIORITY = [
    ("dissolution_confirmed", "confirmed_dissolution"),
    ("acquisition_reported", "acquisition_reported_payout_unknown"),
    ("ipo_prospectus_final", "listed_via_ipo_payout_unknown"),
    ("platform_reports_insolvent_dormant_or_dissolved", "platform_claims_insolvent_dormant_or_dissolved"),
]


def _d(x: str) -> str:
    """Normalize partial dates conservatively: YYYY -> YYYY-01-01, YYYY-MM -> YYYY-MM-01."""
    x = str(x or "").strip()
    if len(x) == 4:
        return x + "-01-01"
    if len(x) == 7:
        return x + "-01"
    return x[:10]


def summarize_outcomes(events: list[dict], cutoff: str) -> dict:
    """Summarize an event history without collapsing it into success/failure."""
    events = [{**e, "publication_date": _d(e.get("publication_date", "")), "event_date": _d(e.get("event_date", ""))}
              for e in events]
    types = {e["event_type"] for e in events}
    dated = [e for e in events if e.get("publication_date")]
    last_obs = max((e["publication_date"] for e in dated if e["publication_date"] <= cutoff), default="")
    ops = [e for e in events if e["event_type"] in OPERATING_TYPES]
    last_ops = max((e["publication_date"] for e in ops if e["publication_date"]), default="")
    status = "no_post_offering_evidence_found_within_budget"
    for et, label in TERMINAL_PRIORITY:
        if et in types:
            status = label
            break
    else:
        if "reporting_termination" in types:
            later_ops = [e for e in ops if e["publication_date"] > max(
                x["publication_date"] for x in events if x["event_type"] == "reporting_termination")]
            status = ("reporting_terminated_later_activity_reported" if later_ops
                      else "reporting_terminated_status_unknown")
        elif last_ops:
            status = "operating_activity_last_evidenced"
        elif "annual_report_filed" in types:
            status = "reporting_only"
    gap_years = ""
    if last_obs:
        gap_years = round((dt.date.fromisoformat(cutoff) - dt.date.fromisoformat(last_obs)).days / 365.25, 2)
    lost = bool(gap_years != "" and gap_years > 3 and status not in ("confirmed_dissolution",))
    def last(evs, tier):
        ds = [e["publication_date"] for e in evs if e.get("publication_date") and e["publication_date"] <= cutoff
              and source_tier(e.get("evidence_strength", "")) == tier]
        return max(ds, default="")
    plat = [e for e in events if e["event_type"].startswith("platform_reports")]
    conflict = bool(plat and any(e["event_type"] == "platform_reports_insolvent_dormant_or_dissolved" for e in plat)
                    and any(e["event_type"] in ("periodic_report_10k", "ipo_prospectus_final") and
                            e["publication_date"] >= "2025-01-01" for e in events))
    return {
        "outcome_status_summary": status,
        "last_observation_sec_issuer": last(events, "sec_issuer"),
        "last_observation_sec_platform": last(events, "sec_platform"),
        "last_observation_external": last(events, "external"),
        "last_operating_evidence_sec_issuer": last(ops, "sec_issuer"),
        "last_operating_evidence_external": last(ops, "external"),
        "platform_status_marks": "; ".join(f"{e['event_date'][:4]}:{e['event_type'].replace('platform_reports_', '').replace('platform_lists_holding_', '')}"
                                           for e in sorted(plat + [x for x in events if x["event_type"] == "platform_lists_holding_no_status_mark"],
                                                           key=lambda x: x["event_date"])),
        "platform_mark_conflicts_with_sec_evidence": conflict,
        "n_events_total": len(events),
        "n_annual_reports_filed": sum(e["event_type"] == "annual_report_filed" for e in events),
        "n_follow_on_financing_filings": sum(e["event_type"] in (
            "securities_offering_notice_form_d", "follow_on_reg_cf_offering_filed", "reg_a_offering_filed",
            "financing_independent_report") for e in events),
        "has_reporting_termination": "reporting_termination" in types,
        "has_ipo_or_listing_evidence": bool(types & {"ipo_prospectus_final", "exchange_registration_8a12b"}),
        "has_acquisition_evidence": "acquisition_reported" in types,
        "has_confirmed_dissolution": "dissolution_confirmed" in types,
        "last_observation_date": last_obs,
        "last_operating_activity_evidence_date": last_ops,
        "years_since_last_observation": gap_years,
        "visibility_lost_gt_3y": lost,
    }
