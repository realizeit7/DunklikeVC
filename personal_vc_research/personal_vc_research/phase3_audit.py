"""Phase-3 random-audit second pass (frozen audit set, without replacement).

Re-derives, for each audit offering, (a) the issuer's SEC filing history directly from the cached EDGAR submissions
JSON and (b) the Republic holdings rows with a different PDF text extractor (poppler `pdftotext -layout`), then
compares both with the pipeline tables. Same agent as the extraction -> a SECOND PASS, not independent validation.
"""
from __future__ import annotations

import json
import re
import subprocess

import pandas as pd

from .config import Config
from .republic_holdings import FILINGS

FORMS = {"C-AR": "annual_report_filed", "C-TR": "reporting_termination", "C-W": "offering_withdrawn"}


def _sec_rederive(sub: dict, file_no: str, start: str, cutoff: str) -> dict:
    """Issuer filings strictly after the offering's initial Form C and on/before the cutoff (outcome window)."""
    r = sub["filings"]["recent"]
    rows = [(f, d, fn) for f, d, fn in zip(r["form"], r["filingDate"], r.get("fileNumber", [""] * len(r["form"])))
            if start < d <= cutoff]
    out = {f"n_{k}": sum(1 for f, _, _ in rows if f == k) for k in FORMS}
    out["n_form_d"] = sum(1 for f, _, _ in rows if f in ("D", "D/A"))
    out["n_later_form_c"] = sum(1 for f, _, fn in rows if f == "C" and fn != file_no)
    out["n_other_round_c_u"] = sum(1 for f, _, fn in rows if f == "C-U" and fn != file_no)
    out["last_sec_filing"] = max((d for _, d, _ in rows), default="")
    out["older_files_pages"] = len(sub["filings"].get("files", []))
    return out


def cmd_audit_p3(cfg: Config, args) -> int:
    td, cutoff = cfg.path("tables_dir"), cfg["study"]["outcome_cutoff_utc"]
    freeze = json.load(open(cfg.path("sample_dir") / "sample_freeze.json"))
    audit_ids = freeze["audit"]
    man = {}
    for line in open(cfg.path("manifest")):
        rec = json.loads(line)
        man[rec["url"]] = rec
    off = pd.read_csv(td / "offerings_outcomes40.csv", dtype=str, keep_default_na=False)
    ev = pd.read_csv(td / "outcome_events_outcomes40.csv", dtype=str, keep_default_na=False)
    fields = pd.read_csv(td / "outcome_fields_40.csv", dtype=str, keep_default_na=False)
    claims = pd.read_csv(td / "republic_holdings_claims_40.csv", dtype=str, keep_default_na=False)
    texts = {}
    for acc, url, _, as_of, _ in FILINGS:
        texts[as_of] = subprocess.run(["pdftotext", "-layout", str(cfg.root / man[url]["cache_path"]), "-"],
                                      capture_output=True, text=True, check=True).stdout
    out = []
    for oid in audit_ids:
        o = off[off["offering_id"] == oid].iloc[0]
        cik = o["issuer_cik"].zfill(10)
        sub = json.load(open(cfg.root / man[f"https://data.sec.gov/submissions/CIK{cik}.json"]["cache_path"]))
        re_ = _sec_rederive(sub, o["offering_file_number"], o["initial_filing_date"], cutoff)
        e = ev[ev["offering_id"] == oid]
        pipe = {f"n_{k}": int((e["event_type"] == v).sum()) for k, v in FORMS.items()}
        pipe["n_form_d"] = int(e["event_type"].isin(["securities_offering_notice_form_d",
                                                     "securities_offering_notice_form_d_amendment"]).sum())
        pipe["n_later_form_c"] = int((e["event_type"] == "follow_on_reg_cf_offering_filed").sum())
        pipe["n_other_round_c_u"] = int((e["event_type"] == "other_reg_cf_offering_progress_reported").sum())
        f = fields[fields["offering_id"] == oid].iloc[0]
        pipe["last_sec_filing"] = f["last_observation_sec_issuer"]
        for k in ["n_C-AR", "n_C-TR", "n_C-W", "n_form_d", "n_later_form_c", "n_other_round_c_u", "last_sec_filing"]:
            out.append({"offering_id": oid, "legal_name": o["issuer_legal_name_at_offering"], "check": f"sec:{k}",
                        "second_pass_value": re_[k], "pipeline_value": pipe[k],
                        "agree": str(re_[k]) == str(pipe[k]), "method": "EDGAR submissions JSON (filings.recent) <= cutoff"})
        c = claims[(claims["offering_id"] == oid) & (claims["association_level"] == "offering")]
        for label in sorted(set(c["listed_entity"])):
            cap = c[c["listed_entity"] == label]["capital_raised_usd"].iloc[0]
            cap_s = f"{float(cap):,.0f}"
            for as_of, t in texts.items():
                hits = [ln for ln in t.splitlines() if re.search(rf"^\s*{re.escape(label)}\b", ln) and cap_s in ln]
                marks = "|".join(sorted({("*" if re.search(rf"{re.escape(label)}\s*\*", h) else "") +
                                         ("+" if re.search(rf"{re.escape(label)}\s*\+", h) else "") +
                                         (("(" + m.group(1) + ")") if (m := re.search(r"\((\d+)\)", h)) else "")
                                         for h in hits})) if hits else "not listed"
                pc = c[(c["listed_entity"] == label) & (c["holdings_as_of"] == as_of)]
                pm = (pc["mark"].iloc[0] + (f"({pc['footnote_no'].iloc[0]})" if pc["footnote_no"].iloc[0] and
                      as_of != "2022-12-31" else "")) if len(pc) else "not listed"
                if as_of == "2022-12-31" and hits:  # 2022 notes are superscripts; pdftotext renders them as digits
                    marks = marks.replace("()", "")
                out.append({"offering_id": oid, "legal_name": o["issuer_legal_name_at_offering"],
                            "check": f"republic:{label}:{as_of}", "second_pass_value": marks or "no mark",
                            "pipeline_value": pm or "no mark", "agree": (marks or "no mark") == (pm or "no mark"),
                            "method": "pdftotext -layout (poppler) line search by label + capital"})
    df = pd.DataFrame(out)
    df.to_csv(cfg.root / "reports" / "phase3_random_audit_second_pass.csv", index=False)
    print(df.groupby("offering_id")["agree"].agg(["sum", "count"]))
    print(df[~df["agree"]].to_string())
    return 0
