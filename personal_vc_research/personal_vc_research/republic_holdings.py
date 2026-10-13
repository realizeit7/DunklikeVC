"""Parse Republic Crowd-Invest "Securities Holdings" tables from Republic Note / Republic Core filings.

Scope (from the filer's own narrative, Republic Core C-AR 2026 p.48-49): the table lists "the securities
Republic Crowd-Invest has acquired as partial compensation for the crowdfunding issuances that have taken
place on its portal", in "the same form and manner as the securities sold" to investors; it is "prepared
internally" and "unaudited". Each row is therefore a HOLDING (one issuance's commission securities), not an
issuer record and not investor-level data. Marks are the filer's claims; an SEC-hosted filing is still a claim
by its filer, not SEC verification.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pdfplumber

from .config import Config

FILINGS = [
    # accession, url, filing date, as-of date
    ("0001794805-23-000001", "https://www.sec.gov/Archives/edgar/data/1794805/000179480523000001/rnotecf.pdf",
     "2023-02-07", "2022-12-31", "Form C (Republic Note offering)"),
    ("0001213900-24-037386", "https://www.sec.gov/Archives/edgar/data/1794805/000121390024037386/formcar.pdf",
     "2024-04-30", "2023-12-31", "Form C-AR (Republic Core)"),
    ("0001213900-25-037004", "https://www.sec.gov/Archives/edgar/data/1794805/000121390025037004/formcar.pdf",
     "2025-04-30", "2024-12-31", "Form C-AR (Republic Core)"),
    ("0001213900-26-050398", "https://www.sec.gov/Archives/edgar/data/1794805/000121390026050398/formcar.pdf",
     "2026-04-30", "2025-12-31", "Form C-AR (Republic Core)"),
]

ROW = re.compile(r"^(?P<name>.*?)\s*(?P<date>\d{4}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4})\s+\$\s?(?P<cap>[\d,]+(?:\.\d+)?)\s+"
                 r"(?P<pct>[\d.]+)%\s+\$\s?(?P<usd>[\d,]+(?:\.\d+)?)\s*$")
SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
SUP_TAIL = re.compile(r"(?P<sup>[⁰¹²³⁴⁵⁶⁷⁸⁹]+)\s*$")
MARK = re.compile(r"^(?P<base>.*?)(?P<marks>[\*\+&\^#]+)?\s*(?:\((?P<fn>\d+)\))?\s*(?P<marks2>[\*\+&\^#]+)?$")


def _norm_date(d: str) -> str:
    if "/" in d:
        m, dd, y = d.split("/")
        return f"{y}-{int(m):02d}"
    y, m = d.split("-")
    return f"{y}-{int(m):02d}"


def parse_filing(pdf_path: Path, accession: str, url: str, filed: str, as_of: str, form: str):
    rows, legend_text, table_pages = [], [], []
    with pdfplumber.open(pdf_path) as pdf:
        texts = [(i + 1, p.extract_text() or "") for i, p in enumerate(pdf.pages)]
    start = next((i for i, t in texts if re.search(r"Crowd-?Invest\s*\n?\s*Securities\s+Holdings", t)
                  or ("Securities Holdings" in t and "As of" in t and "Issuer" in t)), None)
    if start is None:
        return pd.DataFrame(), ""
    for pno, t in texts[start - 1:]:
        lines = t.splitlines()
        hit = False
        for k, line in enumerate(lines):
            m = ROW.match(line.strip())
            if not m:
                continue
            hit = True
            name = m.group("name").strip()
            wrapped = False
            if not name:  # name wrapped around the data line
                prev = lines[k - 1].strip() if k else ""
                nxt = lines[k + 1].strip() if k + 1 < len(lines) else ""
                parts = [p for p in (prev, nxt) if p and not ROW.match(p) and not re.match(r"^\d+$", p)]
                name, wrapped = " ".join(parts), True
            # 2022 (Republic Note Form C) attaches its numbered notes ("1." ... "10.") as Unicode superscripts
            sup = SUP_TAIL.search(name)
            fn_sup = sup.group("sup").translate(SUP) if sup else ""
            if sup:
                name = name[:sup.start()].rstrip()
            mm = MARK.match(name)
            base = (mm.group("base") or name).strip()
            marks = (mm.group("marks") or "") + (mm.group("marks2") or "")
            rows.append({"accession": accession, "filing_url": url, "form": form, "filing_date": filed,
                         "holdings_as_of": as_of, "page": pno, "raw_line": line.strip(),
                         "listed_entity_label": base, "marks": marks, "footnote_no": mm.group("fn") or fn_sup,
                         "footnote_style": ("superscript" if fn_sup else ("parenthesized" if mm.group("fn") else "")),
                         "issuance_month": _norm_date(m.group("date")), "capital_raised_usd": m.group("cap").replace(",", ""),
                         "commission_pct": m.group("pct"), "commission_usd": m.group("usd").replace(",", ""),
                         "name_reconstructed_from_wrapped_lines": wrapped})
        if hit:
            table_pages.append(pno)
        if re.search(r"insolvent, dormant|has converted due to|were liquidated, resulting", t):
            legend_text.append(f"[page {pno}]\n{t}")
        if table_pages and not hit and pno > table_pages[-1] + 1:
            break
    return pd.DataFrame(rows), "\n".join(legend_text)


def cmd_holdings(cfg: Config, args) -> int:
    man = {}
    for line in open(cfg.path("manifest")):
        r = json.loads(line)
        man[r["url"]] = r
    out, legends = [], []
    for acc, url, filed, as_of, form in FILINGS:
        rec = man.get(url)
        if not rec or not rec.get("cache_path"):
            print(f"missing cached filing {url}; fetch it first")
            continue
        df, leg = parse_filing(cfg.root / rec["cache_path"], acc, url, filed, as_of, form)
        df["filing_sha256"] = rec["sha256"]
        out.append(df)
        legends.append({"accession": acc, "holdings_as_of": as_of, "filing_date": filed, "legend_text_verbatim": leg})
        print(f"{acc} as-of {as_of}: {len(df)} rows, pages {df['page'].min() if len(df) else '-'}-{df['page'].max() if len(df) else '-'}")
    allr = pd.concat(out, ignore_index=True)
    td = cfg.path("tables_dir")
    allr.to_csv(td / "republic_holdings_rows.csv", index=False)
    pd.DataFrame(legends).to_csv(td / "republic_holdings_legends.csv", index=False)
    print(allr.groupby("holdings_as_of")["marks"].value_counts().unstack(fill_value=0))
    return 0
