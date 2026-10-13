"""Conservative matching of sampled offerings to Republic holdings rows.

Classes (per offering x holdings issuance series):
  exact              normalized listed label == a documented issuer name (legal, DERA alias, EDGAR current/former)
                     AND issuance month within the offering window
  corroborated_alias label matches the issuer's own website domain stem (documented in its Form C) AND
                     issuance month in window AND amount consistent with the C-U closing amount
  ambiguous          some name evidence but window/amount inconsistent, several candidate series, or brand-only
  unmatched          no candidate
Offering-level association requires the issuance month to fall inside the offering window; otherwise a match
is kept at issuer level only. Repeated yearly rows of the same issuance are one series (repeated observations).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import pandas as pd

STOP = {"inc", "llc", "pbc", "corp", "corporation", "co", "ltd", "the", "company", "holdings", "group", "technologies",
        "technology", "labs", "international", "systems", "app", "inc."}


def norm(s: str) -> str:
    s = re.sub(r"\(formerly[^)]*\)", "", str(s), flags=re.I)
    toks = [t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOP]
    return "".join(toks)


def domain_stem(url: str) -> str:
    u = str(url).strip()
    if not u:
        return ""
    if "//" not in u:
        u = "http://" + u
    host = urlparse(u).netloc.lower().removeprefix("www.")
    stem = host.split(".")[0] if host else ""
    return re.sub(r"[^a-z0-9]", "", stem)


def month_add(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) + k
    while m > 12:
        y, m = y + 1, m - 12
    while m < 1:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def match(offerings: pd.DataFrame, frame: pd.DataFrame, holdings: pd.DataFrame) -> pd.DataFrame:
    h = holdings.copy()
    h["label_norm"] = h["listed_entity_label"].map(norm)
    h["series_key"] = h["label_norm"] + "|" + h["issuance_month"]
    out = []
    for _, o in offerings.iterrows():
        fr = frame[frame["offering_id"] == o["offering_id"]].iloc[0]
        names = {norm(o["issuer_legal_name_at_offering"]), norm(o.get("issuer_current_edgar_name", ""))}
        names |= {norm(x) for x in str(fr.get("issuer_aliases", "")).split("|") if x.strip()}
        names |= {norm(x) for x in str(o.get("issuer_former_names", "")).split("|") if x.strip()}
        names.discard("")
        stem = domain_stem(fr.get("issuer_website", ""))
        start = o["initial_filing_date"][:7]
        close = (o.get("completion_report_date") or o.get("deadline_in_effect_at_decision") or "")[:7] or month_add(start, 6)
        win = (start, month_add(close, 3))
        amt = float(o["amount_reported_at_close_usd"]) if str(o.get("amount_reported_at_close_usd", "")) not in ("", "nan") else None
        name_hit = h[h["label_norm"].isin(names)]
        dom_hit = h[(h["label_norm"] == stem) | (h["label_norm"].str.startswith(stem) & (len(stem) >= 5))] if stem else h.iloc[0:0]
        first = norm(o["issuer_legal_name_at_offering"])[:5]
        weak = h[h["label_norm"].str.startswith(first)] if len(first) >= 4 else h.iloc[0:0]
        cands = pd.concat([name_hit.assign(name_ev="exact_name"), dom_hit.assign(name_ev="website_domain_stem"),
                           weak.assign(name_ev="prefix_only")]).drop_duplicates(subset=["accession", "page", "raw_line"])
        if cands.empty:
            out.append({"offering_id": o["offering_id"], "legal_name": o["issuer_legal_name_at_offering"],
                        "match_class": "unmatched", "series_key": "", "listed_label": "", "issuance_month": "",
                        "window": f"{win[0]}..{win[1]}", "name_evidence": "", "date_in_window": "", "amount_ratio": "",
                        "years_listed": "", "association_level": "none", "website_stem": stem})
            continue
        for key, g in cands.groupby("series_key"):
            ev = sorted(set(g["name_ev"]), key=["exact_name", "website_domain_stem", "prefix_only"].index)[0]
            im = g["issuance_month"].iloc[0]
            in_win = win[0] <= im <= win[1]
            cap = float(g["capital_raised_usd"].iloc[0])
            ratio = round(cap / amt, 3) if amt else ""
            amt_ok = (ratio != "" and 0.6 <= ratio <= 1.25)
            if ev == "exact_name" and in_win:
                cls = "exact"
            elif ev == "website_domain_stem" and in_win and (amt_ok or amt is None):
                cls = "corroborated_alias"
            else:
                cls = "ambiguous"
            out.append({"offering_id": o["offering_id"], "legal_name": o["issuer_legal_name_at_offering"],
                        "match_class": cls, "series_key": key, "listed_label": g["listed_entity_label"].iloc[0],
                        "issuance_month": im, "window": f"{win[0]}..{win[1]}", "name_evidence": ev,
                        "date_in_window": in_win, "amount_ratio": ratio,
                        "years_listed": ";".join(sorted(g["holdings_as_of"].str[:4].unique())),
                        "marks_by_year": ";".join(f"{a[:4]}:{m or '-'}{('(' + f + ')') if f else ''}" for a, m, f in
                                                  sorted(zip(g["holdings_as_of"], g["marks"], g["footnote_no"]))),
                        "association_level": "offering" if cls in ("exact", "corroborated_alias") else "issuer_or_none",
                        "website_stem": stem})
    return pd.DataFrame(out)
