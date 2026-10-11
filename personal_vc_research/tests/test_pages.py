"""OCR plan guards (SYNTHETIC)."""
import pytest

from personal_vc_research.pages import parse_pages, run_plan
from personal_vc_research.pdftext import text_quality


def test_parse_pages():
    assert parse_pages("5-7,10") == [5, 6, 7, 10]


def test_batch_larger_than_limit_rejected(tmp_path):
    row = {"offering_id": "O", "doc_url": "u", "batch": "1", "pages": "1-11", "rationale": "r"}
    with pytest.raises(ValueError):
        run_plan([row], {"u": {"path": "x", "sha256": "h"}}, tmp_path, tmp_path / "log.csv", 30, 3600, 10)


def test_page_cap_skips_and_logs(tmp_path):
    row = {"offering_id": "O", "doc_url": "u", "batch": "1", "pages": "1-3", "rationale": "r"}
    out = run_plan([row], {"u": {"path": "x", "sha256": "h"}}, tmp_path, tmp_path / "log.csv", 0, 3600, 10)
    assert [r["status"] for r in out] == ["skipped_offering_page_cap"] * 3


def test_cid_glyphs_count_as_unreadable():
    assert text_quality("(cid:68)(cid:72)(cid:70)") < 0.5 and text_quality("Valuation Cap $6,000,000") > 0.9
