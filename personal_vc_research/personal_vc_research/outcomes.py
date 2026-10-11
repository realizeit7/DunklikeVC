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
    if form in ("C/A", "C-U") and file_number != offering_file_number:
        return "", "", ""  # belongs to another offering; its own C is the event
    if form == "C-U":
        return "", "", ""  # handled from DERA progress text
    return FORM_RULES.get(form, ("", "", ""))


TERMINAL_PRIORITY = [
    ("dissolution_confirmed", "confirmed_dissolution"),
    ("acquisition_reported", "acquisition_reported_payout_unknown"),
    ("ipo_prospectus_final", "listed_via_ipo_payout_unknown"),
]


def summarize_outcomes(events: list[dict], cutoff: str) -> dict:
    """Summarize an event history without collapsing it into success/failure."""
    types = {e["event_type"] for e in events}
    dated = [e for e in events if e.get("publication_date")]
    last_obs = max((e["publication_date"] for e in dated if e["publication_date"] <= cutoff), default="")
    ops = [e for e in events if e["event_type"] in ("operating_activity_reported", "operating_activity_independent_report")]
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
    return {
        "outcome_status_summary": status,
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
