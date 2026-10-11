"""Offering/issuer linkage invariants on SYNTHETIC DERA-like tables."""
import datetime as dt

import pandas as pd

from personal_vc_research.config import Config
from personal_vc_research.frame import build_frame, classify_security, frame_hash

REP = "0000000001"   # synthetic intermediary CIK
OTHER = "0000000002"


def _cfg(tmp_path):
    raw = {"study": {"cohort_years": [2019]},
           "platform": {"intermediary_name_patterns": ["synthportal"], "intermediary_ciks": [REP],
                        "exclude_name_patterns": []},
           "security_filter": {"include_classes": ["equity", "safe", "convertible_note"], "overrides": []},
           "paths": {}}
    return Config(raw=raw, root=tmp_path)


def _tables(rows):
    sub, iss, dis = [], [], []
    for r in rows:
        acc, typ, date, cik, fn, im = r[:6]
        desc = r[6] if len(r) > 6 else "Crowd SAFE"
        sub.append({"ACCESSION_NUMBER": acc, "SUBMISSION_TYPE": typ, "FILING_DATE": dt.date.fromisoformat(date),
                    "CIK": cik, "FILE_NUMBER": fn, "PERIOD": "", "SOURCE_QUARTER": "q", "SOURCE_URL": "u"})
        iss.append({"ACCESSION_NUMBER": acc, "NAMEOFISSUER": f"Synth {cik}", "COMPANYNAME": "SynthPortal" if im == REP else "Other",
                    "COMMISSIONCIK": im, "COMMISSIONFILENUMBER": "007-0", "LEGALSTATUSFORM": "Corporation",
                    "JURISDICTIONORGANIZATION": "DE", "DATEINCORPORATION": "2017-01-01", "ISSUERWEBSITE": "x",
                    "NATUREOFAMENDMENT": "", "PROGRESSUPDATE": ""})
        dis.append({"ACCESSION_NUMBER": acc, "SECURITYOFFEREDTYPE": "Other", "SECURITYOFFEREDOTHERDESC": desc})
    return {"FORM_C_SUBMISSION": pd.DataFrame(sub), "FORM_C_ISSUER_INFORMATION": pd.DataFrame(iss),
            "FORM_C_DISCLOSURE": pd.DataFrame(dis)}


def test_amendments_do_not_create_duplicate_offerings(tmp_path):
    t = _tables([("a1", "C", "2019-03-01", "C1", "020-1", REP),
                 ("a2", "C/A", "2019-03-05", "C1", "020-1", REP),
                 ("a3", "C/A", "2019-04-05", "C1", "020-1", REP),
                 ("a4", "C-U", "2019-06-05", "C1", "020-1", REP)])
    fr, _, _ = build_frame(t, _cfg(tmp_path))
    assert len(fr) == 1
    assert fr.iloc[0]["n_amendments"] == 2


def test_distinct_rounds_stay_distinct_and_share_issuer(tmp_path):
    t = _tables([("b1", "C", "2019-02-01", "C2", "020-2", REP),
                 ("b2", "C", "2019-09-01", "C2", "020-3", REP)])
    fr, _, _ = build_frame(t, _cfg(tmp_path))
    assert len(fr) == 2 and fr["issuer_cik"].nunique() == 1
    assert sorted(fr["round_index_for_issuer"].tolist()) == [1, 2]


def test_same_day_withdrawn_duplicate_is_not_a_round(tmp_path):
    t = _tables([("c1", "C", "2019-05-01", "C3", "020-4", REP),
                 ("c2", "C", "2019-05-01", "C3", "020-5", REP),
                 ("c3", "C-W", "2019-05-01", "C3", "020-5", "")])
    fr, _, _ = build_frame(t, _cfg(tmp_path))
    dup = fr[fr["file_number"] == "020-5"].iloc[0]
    assert not dup["eligible"] and dup["duplicate_of"].endswith("020-4")
    assert fr[fr["file_number"] == "020-4"].iloc[0]["eligible"]


def test_cross_intermediary_filings_under_same_file_number_not_amendments(tmp_path):
    t = _tables([("d1", "C", "2019-01-10", "C4", "020-6", REP),
                 ("d2", "C/A", "2020-05-01", "C4", "020-6", OTHER)])
    fr, _, _ = build_frame(t, _cfg(tmp_path))
    r = fr.iloc[0]
    assert r["n_amendments"] == 0
    assert "d2" in r["foreign_intermediary_accessions"] and r["needs_manual_review"]


def test_other_platform_offerings_excluded(tmp_path):
    t = _tables([("e1", "C", "2019-01-10", "C5", "020-7", OTHER)])
    fr, _, _ = build_frame(t, _cfg(tmp_path))
    assert len(fr) == 0


def test_security_classification_rules():
    assert classify_security("Other", "Token DPA", "X Inc", "")[0] == "crypto_token"
    assert classify_security("Other", "CrowdSAFE", "X Inc", "")[0] == "safe"
    assert classify_security("Debt", "", "X Inc", "")[0] == "pure_debt"
    assert classify_security("Other", "Membership Interest of Series Y", "Proj LLC", "")[0] == "real_estate"
    assert classify_security("Other", "Crowd SAFE", "Realtyna Inc.", "")[0] == "safe"


def test_frame_hash_ignores_row_order(tmp_path):
    t = _tables([("f1", "C", "2019-01-10", "C6", "020-8", REP), ("f2", "C", "2019-02-10", "C7", "020-9", REP)])
    fr, _, _ = build_frame(t, _cfg(tmp_path))
    assert frame_hash(fr) == frame_hash(fr.iloc[::-1])
