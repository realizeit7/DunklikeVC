"""User-import eligibility and outcome source tiers (SYNTHETIC rows)."""
from personal_vc_research.imports import validate_row
from personal_vc_research.outcomes import source_tier, summarize_outcomes

DD = {"O1": "2020-06-25"}


def _row(**kw):
    base = {"item_id": "i1", "offering_id": "O1", "url_or_document_identity": "https://example.invalid/update",
            "file": "", "capture_date_utc": "2026-10-11", "displayed_publication_or_update_date": "2020-06-01",
            "visibility": "public", "security_class": "Crowd SAFE", "evidence_locator": "update #1",
            "publication_timing_independently_verified": "false", "evidence_type": "campaign_update",
            "summary": "synthetic"}
    base.update(kw)
    return base


def test_page_captured_today_is_outcome_only_without_verified_timing(tmp_path):
    v = validate_row(_row(), DD, tmp_path)
    assert v["historical_feature_eligible"] is False and v["permitted_use"] == "outcome_only"
    assert "not independently verified" in v["ineligibility_reason"]


def test_verified_public_pre_decision_item_can_be_historical(tmp_path):
    v = validate_row(_row(publication_timing_independently_verified="true"), DD, tmp_path)
    assert v["historical_feature_eligible"] is True


def test_post_decision_or_investor_only_never_historical(tmp_path):
    assert validate_row(_row(publication_timing_independently_verified="true",
                             displayed_publication_or_update_date="2020-07-01"), DD, tmp_path)["historical_feature_eligible"] is False
    assert validate_row(_row(publication_timing_independently_verified="true", visibility="investor_only"),
                        DD, tmp_path)["historical_feature_eligible"] is False


def test_missing_fields_and_unknown_offering_flagged(tmp_path):
    v = validate_row(_row(offering_id="NOPE", evidence_locator=""), DD, tmp_path)
    assert "offering_id not in frozen sample" in v["validation_errors"] and "missing evidence_locator" in v["validation_errors"]


def test_source_tiers_kept_separate():
    ev = [{"event_type": "annual_report_filed", "publication_date": "2022-05-01", "event_date": "2022-05-01",
           "evidence_strength": "filing_evidence"},
          {"event_type": "operating_activity_company_claim", "publication_date": "2026-10-12", "event_date": "2026-10-12",
           "evidence_strength": "company_claim_current_webpage"},
          {"event_type": "platform_lists_holding_no_status_mark", "publication_date": "2026-04-30",
           "event_date": "2025-12-31", "evidence_strength": "platform_claim_in_sec_filing"}]
    s = summarize_outcomes(ev, "2026-10-10")
    assert s["last_observation_sec_issuer"] == "2022-05-01"
    assert s["last_observation_sec_platform"] == "2026-04-30"
    assert s["last_observation_external"] == ""          # 2026-10-12 is after the cutoff
    assert source_tier("independent_reporting") == "external"


def test_platform_insolvency_mark_conflicting_with_listing_is_flagged():
    ev = [{"event_type": "ipo_prospectus_final", "publication_date": "2023-07-26", "event_date": "2023-07-26",
           "evidence_strength": "filing_evidence"},
          {"event_type": "periodic_report_10k", "publication_date": "2026-03-30", "event_date": "2026-03-30",
           "evidence_strength": "filing_evidence"},
          {"event_type": "platform_reports_insolvent_dormant_or_dissolved", "publication_date": "2026-04-30",
           "event_date": "2025-12-31", "evidence_strength": "platform_claim_in_sec_filing"}]
    s = summarize_outcomes(ev, "2026-10-10")
    assert s["platform_mark_conflicts_with_sec_evidence"] is True
    assert s["outcome_status_summary"] == "listed_via_ipo_payout_unknown"
