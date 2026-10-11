"""Sampling-frame construction from SEC DERA Form C data.

Unit of analysis = one *offering* = one initial Form C (SUBMISSION_TYPE == 'C') and its own
EDGAR file number (020-xxxxx). Amendments (C/A), progress updates (C-U) and withdrawals (C-W)
are linked by file number. Annual reports (C-AR) and terminations (C-TR) are *issuer-level*
obligations and are linked by CIK, because issuers sometimes file them under another offering's
file number.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re

import pandas as pd

from .config import Config

OFFERING_LEVEL_FORMS = {"C", "C/A", "C-U", "C-W", "C/A-W", "C-U-W"}
ISSUER_LEVEL_FORMS = {"C-AR", "C-AR/A", "C-TR", "C-AR-W", "C-TR-W"}

FRAME_COLUMNS = [
    "offering_id", "issuer_cik", "file_number", "initial_accession", "initial_filing_date", "cohort_year",
    "legal_name", "issuer_aliases", "issuer_website", "legal_status", "jurisdiction", "date_incorporation",
    "intermediary_name", "intermediary_cik", "intermediary_file_number",
    "security_type_raw", "security_desc_raw", "security_class", "eligible", "exclusion_reason",
    "needs_manual_review", "review_note",
    "round_index_for_issuer", "n_republic_offerings_for_issuer",
    "amendment_accessions", "n_amendments", "progress_update_accessions", "withdrawal_accessions",
]

# Keyword rules, applied in order. Recorded per row as the classification evidence.
CRYPTO_DESC = re.compile(r"\btoken\b|\bDPAs?\b|debt payable by assets|\bCTRA|\bTPA\b|\bSAFT\b|\bcoin\b", re.I)
CRYPTO_NAME = re.compile(r"token|coin|crypto|blockchain", re.I)
REVSHARE = re.compile(r"revenue[- ]?shar|revenue participation|profit[- ]?shar", re.I)
REAL_ESTATE_NAME = re.compile(r"propert|real estate|realty|\breit\b|compound projects|^\d+\s+\w+.*\b(ave|avenue|st|street|blvd|road|rd)\b", re.I)
FUND_NAME = re.compile(r"\bfund(?:\s+(?:I|II|III|LP|L\.P\.))?,?\s*(llc|lp|l\.p\.)$|\bSPV\b|\bventure fund\b", re.I)
SAFE = re.compile(r"\bsafes?\b|crowd\s*safe|simple agreement for future equity", re.I)
CONV = re.compile(r"convertible", re.I)
LLC_UNITS = re.compile(r"membership|units?\b|class \w+ units", re.I)


def classify_security(sec_type: str, desc: str, name: str, website: str) -> tuple[str, str]:
    """Return (security_class, evidence). Classes: equity, safe, convertible_note, crypto_token,
    revenue_share, pure_debt, real_estate, fund_or_spv, other_unclassified."""
    sec_type = (sec_type or "").strip()
    desc = (desc or "").strip()
    if CRYPTO_DESC.search(desc):
        return "crypto_token", f"security description matches token/DPA pattern: {desc!r}"
    if CRYPTO_NAME.search(name) or CRYPTO_NAME.search(website or ""):
        if not SAFE.search(desc) and sec_type not in ("Common Stock", "Preferred Stock"):
            return "crypto_token", f"issuer name/website crypto keyword with non-equity security ({sec_type} {desc!r})"
    if REVSHARE.search(desc):
        return "revenue_share", f"description: {desc!r}"
    llc_interest = bool(re.search(r"membership|units?\b", desc, re.I))
    if (REAL_ESTATE_NAME.search(name) and llc_interest) or (re.search(r"series\b", desc, re.I) and "membership" in desc.lower()):
        return "real_estate", f"real-estate pattern in issuer name/series membership interest: {name!r} / {desc!r}"
    if FUND_NAME.search(name.strip()) and not SAFE.search(desc):
        return "fund_or_spv", f"fund/SPV pattern in issuer name: {name!r}"
    if sec_type in ("Common Stock", "Preferred Stock"):
        return "equity", f"SECURITYOFFEREDTYPE={sec_type}"
    if sec_type == "Debt":
        if CONV.search(desc):
            return "convertible_note", f"Debt with description {desc!r}"
        return "pure_debt", "SECURITYOFFEREDTYPE=Debt with no conversion feature in structured data"
    if SAFE.search(desc):
        return "safe", f"description: {desc!r}"
    if CONV.search(desc):
        return "convertible_note", f"description: {desc!r}"
    if LLC_UNITS.search(desc):
        return "equity", f"LLC membership units: {desc!r}"
    return "other_unclassified", f"type={sec_type!r} desc={desc!r}"


def is_republic(intermediary_name: str, intermediary_cik: str, cfg: Config, republic_ciks: set[str]) -> bool:
    nm = (intermediary_name or "").lower()
    if any(p in nm for p in cfg["platform"]["exclude_name_patterns"]):
        return False
    return intermediary_cik in republic_ciks


def discover_intermediary_ciks(iss: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Evidence table: intermediary name variants matching platform patterns, by CIK / file number."""
    pats = "|".join(cfg["platform"]["intermediary_name_patterns"])
    m = iss[iss["COMPANYNAME"].str.contains(pats, case=False, regex=True)]
    ev = (m.groupby(["COMMISSIONCIK", "COMMISSIONFILENUMBER", "COMPANYNAME"]).size()
          .reset_index(name="n_filings").sort_values("n_filings", ascending=False))
    return ev


def build_frame(tables: dict[str, pd.DataFrame], cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (frame_all_candidates, intermediary_evidence, linked_filings)."""
    sub = tables["FORM_C_SUBMISSION"]
    iss = tables["FORM_C_ISSUER_INFORMATION"]
    dis = tables["FORM_C_DISCLOSURE"]
    ev = discover_intermediary_ciks(iss, cfg)
    configured = set(cfg["platform"].get("intermediary_ciks") or [])
    republic_ciks = configured or set(ev["COMMISSIONCIK"].unique())

    m = sub.merge(iss, on="ACCESSION_NUMBER", how="left", suffixes=("", "_iss")) \
           .merge(dis, on="ACCESSION_NUMBER", how="left", suffixes=("", "_dis"))
    years = set(cfg["study"]["cohort_years"])
    init = m[(m["SUBMISSION_TYPE"] == "C")
             & m["FILING_DATE"].map(lambda d: d.year in years)
             & m["COMMISSIONCIK"].isin(republic_ciks)].copy()
    init = init[init.apply(lambda r: is_republic(r["COMPANYNAME"], r["COMMISSIONCIK"], cfg, republic_ciks), axis=1)]

    # Offering-level linked filings (same CIK + same file number).
    off_forms = m[m["SUBMISSION_TYPE"].isin(OFFERING_LEVEL_FORMS)]
    by_fn = {k: g.sort_values("FILING_DATE") for k, g in off_forms.groupby(["CIK", "FILE_NUMBER"])}
    # All initial Cs by CIK on any platform (to detect duplicates / count rounds).
    all_init = m[m["SUBMISSION_TYPE"] == "C"]

    overrides = {o["accession"]: o for o in (cfg["security_filter"].get("overrides") or [])}
    rows = []
    for _, r in init.iterrows():
        key = (r["CIK"], r["FILE_NUMBER"])
        g_all = by_fn.get(key, pd.DataFrame(columns=m.columns))
        # Guard: filings under the same file number that name a *different* intermediary are not
        # treated as amendments of this offering (observed: issuer re-using an old file number for a
        # later offering on another platform). They are recorded for review instead.
        same_im = g_all["COMMISSIONCIK"].isin(list(republic_ciks) + [""]) | g_all["SUBMISSION_TYPE"].eq("C-W")
        g = g_all[same_im]
        foreign = g_all[~same_im]
        amend = g[g["SUBMISSION_TYPE"] == "C/A"]
        cu = g[g["SUBMISSION_TYPE"] == "C-U"]
        cw = g[g["SUBMISSION_TYPE"] == "C-W"]
        names = sorted(set(g["NAMEOFISSUER"].dropna().str.strip()) - {""})
        sec_class, sec_ev = classify_security(r["SECURITYOFFEREDTYPE"], r["SECURITYOFFEREDOTHERDESC"],
                                              r["NAMEOFISSUER"], r["ISSUERWEBSITE"])
        ov = overrides.get(r["ACCESSION_NUMBER"])
        if ov:
            sec_class, sec_ev = ov["security_class"], f"MANUAL OVERRIDE: {ov['evidence']} (rule said: {sec_class})"
        rows.append({
            "offering_id": f"RCF-{r['CIK'].lstrip('0')}-{r['FILE_NUMBER']}",
            "issuer_cik": r["CIK"], "file_number": r["FILE_NUMBER"],
            "initial_accession": r["ACCESSION_NUMBER"], "initial_filing_date": r["FILING_DATE"].isoformat(),
            "cohort_year": r["FILING_DATE"].year,
            "legal_name": r["NAMEOFISSUER"].strip(), "issuer_aliases": " | ".join(names),
            "issuer_website": r["ISSUERWEBSITE"], "legal_status": r["LEGALSTATUSFORM"],
            "jurisdiction": r["JURISDICTIONORGANIZATION"], "date_incorporation": r["DATEINCORPORATION"],
            "intermediary_name": r["COMPANYNAME"], "intermediary_cik": r["COMMISSIONCIK"],
            "intermediary_file_number": r["COMMISSIONFILENUMBER"],
            "security_type_raw": r["SECURITYOFFEREDTYPE"], "security_desc_raw": r["SECURITYOFFEREDOTHERDESC"],
            "security_class": sec_class, "security_class_evidence": sec_ev,
            "amendment_accessions": " ".join(amend["ACCESSION_NUMBER"]), "n_amendments": len(amend),
            "progress_update_accessions": " ".join(cu["ACCESSION_NUMBER"]),
            "withdrawal_accessions": " ".join(cw["ACCESSION_NUMBER"]),
            "first_withdrawal_date": cw["FILING_DATE"].min().isoformat() if len(cw) else "",
            "foreign_intermediary_accessions": " ".join(
                f"{a}({t},{c})" for a, t, c in zip(foreign["ACCESSION_NUMBER"], foreign["SUBMISSION_TYPE"], foreign["COMPANYNAME"])),
        })
    fr = pd.DataFrame(rows)
    if fr.empty:
        return pd.DataFrame(columns=FRAME_COLUMNS), ev, m.iloc[0:0]

    # Same-day duplicate filings: same CIK, same filing date, one withdrawn the same day while
    # a sibling is not withdrawn -> filing error, not a distinct round.
    fr["duplicate_of"] = ""
    for cik, g in fr.groupby("issuer_cik"):
        for d, gd in g.groupby("initial_filing_date"):
            if len(gd) < 2:
                continue
            withdrawn_same_day = gd[gd["first_withdrawal_date"] == d]
            alive = gd[gd["first_withdrawal_date"] != d]
            if len(alive) >= 1 and len(withdrawn_same_day) >= 1:
                for idx in withdrawn_same_day.index:
                    fr.loc[idx, "duplicate_of"] = alive.iloc[0]["offering_id"]

    include = set(cfg["security_filter"]["include_classes"])
    elig, reason, review, note = [], [], [], []
    for _, r in fr.iterrows():
        rv, nt = False, ""
        if r["duplicate_of"]:
            e, why = False, f"duplicate Form C filed and withdrawn same day; duplicate of {r['duplicate_of']}"
        elif r["security_class"] not in include:
            e, why = False, f"security class {r['security_class']}: {r['security_class_evidence']}"
            rv = r["security_class"] in ("pure_debt", "other_unclassified")
            nt = "confirm security terms from offering document" if rv else ""
        else:
            e, why = True, ""
            if r["security_class"] == "equity" and str(r["legal_status"]).startswith("Limited Liability"):
                rv, nt = True, "LLC units: confirm operating business (not single-asset/project vehicle)"
            if re.search(r"fund|movie|film|spv|token|coin|crypto", r["legal_name"], re.I):
                rv, nt = True, "issuer name suggests fund/project/crypto vehicle; confirm operating business and non-token security"
        if e and r["foreign_intermediary_accessions"]:
            rv = True
            nt = (nt + "; " if nt else "") + "filings under same file number name another intermediary: " + r["foreign_intermediary_accessions"][:200]
        elig.append(e); reason.append(why); review.append(rv); note.append(nt)
    fr["eligible"], fr["exclusion_reason"], fr["needs_manual_review"], fr["review_note"] = elig, reason, review, note

    # Rounds per issuer among eligible Republic offerings (any year in frame).
    fr = fr.sort_values(["issuer_cik", "initial_filing_date", "file_number"]).reset_index(drop=True)
    fr["round_index_for_issuer"] = fr[fr["eligible"]].groupby("issuer_cik").cumcount() + 1
    fr["n_republic_offerings_for_issuer"] = fr[fr["eligible"]].groupby("issuer_cik")["offering_id"].transform("count")
    # Any initial C by same CIK on any platform / any year (context only).
    n_all = all_init.groupby("CIK")["ACCESSION_NUMBER"].nunique()
    fr["n_initial_form_c_any_platform"] = fr["issuer_cik"].map(n_all).fillna(0).astype(int)

    # Linked filings table for transparency (offering-level by file number; issuer-level by CIK).
    ciks = set(fr["issuer_cik"])
    linked = m[m["CIK"].isin(ciks)][["ACCESSION_NUMBER", "SUBMISSION_TYPE", "FILING_DATE", "CIK", "FILE_NUMBER",
                                    "NATUREOFAMENDMENT", "PROGRESSUPDATE", "SOURCE_URL"]].copy()
    linked["link_level"] = linked["SUBMISSION_TYPE"].map(
        lambda t: "issuer" if t in ISSUER_LEVEL_FORMS else "offering")
    linked = linked.sort_values(["CIK", "FILING_DATE", "ACCESSION_NUMBER"])
    return fr, ev, linked


def frame_hash(frame: pd.DataFrame) -> str:
    cols = ["offering_id", "issuer_cik", "file_number", "initial_accession", "initial_filing_date",
            "cohort_year", "security_class", "eligible"]
    canon = frame[cols].sort_values("offering_id").to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(canon.encode()).hexdigest()


def decision_date(initial_filing_date: str, days: int) -> str:
    return (dt.date.fromisoformat(initial_filing_date) + dt.timedelta(days=days)).isoformat()
