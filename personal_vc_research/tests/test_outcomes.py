"""Outcome classification invariants (SYNTHETIC events)."""
from personal_vc_research.outcomes import classify_filing, summarize_outcomes


def ev(t, d):
    return {"event_type": t, "publication_date": d, "event_date": d}


def test_reporting_termination_is_not_failure():
    etype, _, note = classify_filing("C-TR", "020-1", "020-1")
    assert etype == "reporting_termination" and "NOT evidence of business closure" in note
    s = summarize_outcomes([ev("reporting_termination", "2021-05-01")], "2026-10-10")
    assert s["outcome_status_summary"] == "reporting_terminated_status_unknown"
    assert s["has_confirmed_dissolution"] is False


def test_acquisition_without_payout_is_not_positive_return():
    s = summarize_outcomes([ev("acquisition_reported", "2022-01-01")], "2026-10-10")
    assert s["outcome_status_summary"] == "acquisition_reported_payout_unknown"


def test_form_d_is_notice_not_proof_of_raise():
    etype, _, note = classify_filing("D", "021-1", "020-1")
    assert etype == "securities_offering_notice_form_d" and "does not prove" in note


def test_other_offering_amendments_ignored_but_new_form_c_is_follow_on():
    assert classify_filing("C/A", "020-9", "020-1")[0] == ""
    assert classify_filing("C", "020-9", "020-1")[0] == "follow_on_reg_cf_offering_filed"
    assert classify_filing("C-U", "020-9", "020-1")[0] == "other_reg_cf_offering_progress_reported"
    assert classify_filing("C-U", "020-1", "020-1")[0] == ""
    assert classify_filing("C", "020-1", "020-1")[0] == ""


def test_no_evidence_is_not_confirmed_absent():
    s = summarize_outcomes([], "2026-10-10")
    assert s["outcome_status_summary"] == "no_post_offering_evidence_found_within_budget"
    assert s["last_observation_date"] == ""


def test_lost_visibility_flag():
    s = summarize_outcomes([ev("annual_report_filed", "2020-04-30")], "2026-10-10")
    assert s["visibility_lost_gt_3y"] is True


def test_events_after_cutoff_not_observable():
    s = summarize_outcomes([ev("annual_report_filed", "2027-01-01")], "2026-10-10")
    assert s["last_observation_date"] == ""
