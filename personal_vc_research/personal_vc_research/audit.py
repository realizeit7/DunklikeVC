"""Second-pass source audit (same agent => "second pass", not independent validation).

Checks per audited offering:
  A. Form C primary_doc.xml (independent parse) vs DERA structured row for the initial Form C.
  B. Identifier consistency: issuer CIK, offering file number, intermediary CIK / SEC file number.
  C. Manual (PDF/OCR) facts vs structured fields where both exist (employees, revenue, net income,
     deadline, minimum investment).
  D. Verification-status tallies of manual facts.
Writes reports/<scope>_second_pass_audit.csv and prints discrepancies.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import pandas as pd

from .collect import parse_form_c_xml
from .config import Config
from .http import Fetcher

XML_VS_DERA = [  # (xml tag, DERA column, kind)
    ("offeringAmount", "OFFERINGAMOUNT", "num"), ("maximumOfferingAmount", "MAXIMUMOFFERINGAMOUNT", "num"),
    ("deadlineDate", "DEADLINEDATE", "date"), ("currentEmployees", "CURRENTEMPLOYEES", "num"),
    ("revenueMostRecentFiscalYear", "REVENUEMOSTRECENTFISCALYEAR", "num"),
    ("netIncomeMostRecentFiscalYear", "NETINCOMEMOSTRECENTFISCALYEAR", "num"),
    ("totalAssetMostRecentFiscalYear", "TOTALASSETMOSTRECENTFISCALYEAR", "num"),
    ("cashEquiMostRecentFiscalYear", "CASHEQUIMOSTRECENTFISCALYEAR", "num"),
    ("securityOfferedType", "SECURITYOFFEREDTYPE", "text"), ("commissionCik", "COMMISSIONCIK", "text"),
    ("commissionFileNumber", "COMMISSIONFILENUMBER", "text"),
]


def _norm(v, kind):
    v = (v or "").strip()
    if kind == "num":
        try:
            return round(float(v.replace(",", "")), 2)
        except ValueError:
            return v
    if kind == "date" and len(v) == 10 and v[2] == "-":  # MM-DD-YYYY -> ISO
        return f"{v[6:]}-{v[:2]}-{v[3:5]}"
    return v


def cmd_audit(cfg: Config, args) -> int:
    from . import dera
    f = Fetcher(cfg)
    sample = pd.read_csv(cfg.path("sample_dir") / "frozen_sample.csv", dtype=str, keep_default_na=False)
    if args.only == "pilot":
        sel, scope = sample[sample["is_pilot"] == "True"], "pilot"
    elif args.only == "audit":
        sel, scope = sample[sample["is_audit"] == "True"], "audit_set"
    else:
        sel, scope = sample[sample["offering_id"].isin(args.only.split(","))], "custom"
    tabs = dera.load_tables(cfg, f)
    m = tabs["FORM_C_SUBMISSION"].merge(tabs["FORM_C_ISSUER_INFORMATION"], on="ACCESSION_NUMBER", suffixes=("", "_i")) \
        .merge(tabs["FORM_C_DISCLOSURE"], on="ACCESSION_NUMBER", suffixes=("", "_d"))
    td = cfg.path("tables_dir")
    facts_p = td / ("facts_pilot.csv" if scope == "pilot" else "facts.csv")
    facts = pd.read_csv(facts_p, dtype=str, keep_default_na=False) if facts_p.exists() else pd.DataFrame()
    rows = []
    for _, off in sel.iterrows():
        oid, cik_i, acc = off["offering_id"], str(int(off["issuer_cik"])), off["initial_accession"]
        res = f.get(f"https://www.sec.gov/Archives/edgar/data/{cik_i}/{acc.replace('-', '')}/primary_doc.xml",
                    "form_c_xml")
        xml = parse_form_c_xml(res.text()) if res.ok else {}
        d = m[m["ACCESSION_NUMBER"] == acc]
        d = d.iloc[0] if len(d) else None
        # A. XML vs DERA
        for tag, col, kind in XML_VS_DERA:
            xv = _norm(xml.get(tag, ""), kind)
            dv = _norm(d[col], kind) if d is not None else "MISSING_ROW"
            rows.append({"offering_id": oid, "check": f"xml_vs_dera:{tag}", "value_a": xv, "value_b": dv,
                         "source_a": res.url, "source_b": "DERA FORM_C row", "match": xv == dv})
        # B. identifiers
        rows.append({"offering_id": oid, "check": "issuer_cik_xml_vs_frame",
                     "value_a": xml.get("filerCik", ""), "value_b": off["issuer_cik"], "source_a": res.url,
                     "source_b": "frozen_sample", "match": xml.get("filerCik", "") == off["issuer_cik"]})
        rows.append({"offering_id": oid, "check": "intermediary_sec_file_number_xml_vs_frame",
                     "value_a": xml.get("commissionFileNumber", ""), "value_b": off["intermediary_file_number"],
                     "source_a": res.url, "source_b": "frozen_sample",
                     "match": xml.get("commissionFileNumber", "") == off["intermediary_file_number"]})
        # C. manual vs structured
        if len(facts):
            fo = facts[facts["offering_id"] == oid]

            def get(name, method_not="structured_field", method="structured_field", accession_tag="initial_form_c"):
                if method == "structured_field":
                    x = fo[(fo["fact_name"] == name) & (fo["extraction_method"] == "structured_field")
                           & fo["locator"].str.contains(accession_tag)]
                else:
                    x = fo[(fo["fact_name"] == name) & (fo["extraction_method"] != "structured_field")]
                return x["value_text"].iloc[0] if len(x) else ""
            pairs = [("employees_stated_in_memorandum", "employees"), ("revenue_fs", "revenue"),
                     ("net_income_fs", "net_income")]
            for man_name, st_name in pairs:
                a, b = get(man_name, method="manual"), get(st_name)
                if a == "":
                    continue
                rows.append({"offering_id": oid, "check": f"manual_vs_structured:{man_name}~{st_name}",
                             "value_a": a, "value_b": b, "source_a": "Form C PDF (manual)",
                             "source_b": "DERA initial Form C", "match": _norm(a, "num") == _norm(b, "num")})
            mi = fo[fo["fact_name"] == "minimum_investment"]
            amend = fo[fo["fact_name"] == "amendment_nature"]
            for _, a in amend.iterrows():
                if "minimum" in a["value_text"].lower():
                    rows.append({"offering_id": oid, "check": "minimum_investment_changed_by_amendment",
                                 "value_a": mi["value_text"].iloc[0] if len(mi) else "",
                                 "value_b": a["value_text"][:200], "source_a": "Form C PDF (manual)",
                                 "source_b": f"C/A published {a['public_available_date']}", "match": False})
            # C2. amendment text naming a deadline vs the structured DEADLINEDATE of the same C/A
            dl = fo[(fo["fact_name"] == "offering_deadline") & fo["locator"].str.contains("form_c_amendment")]
            for _, a in amend.iterrows():
                txt = a["value_text"]
                if not re.search(r"deadline|extended|extend", txt, re.I):
                    continue
                mdates = list(re.finditer(r"(January|February|March|April|May|June|July|August|September|October|"
                                  r"November|December)\s+(\d{1,2}),?\s+(\d{4})", txt))
                if not mdates:
                    continue
                mdate = mdates[-1]  # the new deadline is the last date named in the amendment text
                stated = dt.datetime.strptime(" ".join(mdate.groups()), "%B %d %Y").date().isoformat()
                same = dl[dl["public_available_date"] == a["public_available_date"]]
                structured = same["value_text"].iloc[0] if len(same) else ""
                rows.append({"offering_id": oid, "check": "amendment_text_deadline_vs_structured_deadline",
                             "value_a": stated, "value_b": structured,
                             "source_a": f"C/A NATUREOFAMENDMENT {a['public_available_date']}",
                             "source_b": "DERA DEADLINEDATE same C/A", "match": stated == structured})
            # D. verification tallies
            man = fo[fo["extraction_method"] != "structured_field"]
            for status, n in man["verification_status"].value_counts().items():
                rows.append({"offering_id": oid, "check": f"manual_fact_verification_status:{status}",
                             "value_a": int(n), "value_b": "", "source_a": "", "source_b": "", "match": ""})
    out = pd.DataFrame(rows)
    p = cfg.path("reports_dir") / f"{scope}_second_pass_audit.csv"
    out.to_csv(p, index=False)
    disc = out[out["match"] == False]  # noqa: E712
    print(f"checks={len(out[out['match'] != ''])} discrepancies={len(disc)} -> {p}")
    if len(disc):
        print(disc[["offering_id", "check", "value_a", "value_b"]].to_string())
    return 0
