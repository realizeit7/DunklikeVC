"""Historical eligibility and missing-value invariants (SYNTHETIC)."""
from personal_vc_research.collect import Ctx, fact
from personal_vc_research.config import Config


def _ctx(tmp_path):
    return Ctx(Config(raw={"collection": {"max_documents_per_offering": 10}, "paths": {}}, root=tmp_path), fetcher=None)


def test_fact_published_after_decision_is_ineligible(tmp_path):
    c = _ctx(tmp_path)
    fact(c, "O1", "1", "financial", "revenue", "1000", "USD", source_id="s", locator="l",
         public_date="2020-07-01", decision="2020-06-25", method="structured_field",
         economic_date="2019-12-31")  # economic period earlier, publication later
    assert c.facts[0]["eligible_at_decision"] is False


def test_fact_published_on_or_before_decision_is_eligible(tmp_path):
    c = _ctx(tmp_path)
    fact(c, "O1", "1", "financial", "revenue", "1000", "USD", source_id="s", locator="l",
         public_date="2020-06-25", decision="2020-06-25", method="structured_field")
    assert c.facts[0]["eligible_at_decision"] is True


def test_fact_without_publication_date_is_ineligible(tmp_path):
    c = _ctx(tmp_path)
    fact(c, "O1", "1", "founder", "bio", "x", "text", source_id="s", locator="l",
         public_date="", decision="2020-06-25", method="current_webpage")
    assert c.facts[0]["eligible_at_decision"] is False


def test_missing_value_is_not_zero(tmp_path):
    c = _ctx(tmp_path)
    fact(c, "O1", "1", "financial", "revenue", None, "USD", source_id="s", locator="l",
         public_date="2020-01-01", decision="2020-02-01", method="structured_field",
         missing_reason="field blank in filing")
    f = c.facts[0]
    assert f["missing"] is True and f["value_num"] is None and f["value_text"] == ""
    assert f["missing_reason"] == "field blank in filing"


def test_reported_zero_is_kept_as_zero_not_missing(tmp_path):
    c = _ctx(tmp_path)
    fact(c, "O1", "1", "financial", "revenue", "0", "USD", source_id="s", locator="l",
         public_date="2020-01-01", decision="2020-02-01", method="structured_field")
    assert c.facts[0]["missing"] is False and c.facts[0]["value_num"] == 0.0
