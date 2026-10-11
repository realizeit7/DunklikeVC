"""SEC DERA Crowdfunding Offerings data sets (structured extracts of Form C XML filings).

Each quarterly zip contains FORM_C_SUBMISSION, FORM_C_ISSUER_INFORMATION, FORM_C_DISCLOSURE, ...
keyed by ACCESSION_NUMBER and covering Form C, C/A, C-U, C-AR, C-AR/A, C-TR, C-W filings.
"""
from __future__ import annotations

import datetime as dt
import io
import zipfile

import pandas as pd

from .config import Config
from .http import Fetcher

TABLES = ["FORM_C_SUBMISSION", "FORM_C_ISSUER_INFORMATION", "FORM_C_DISCLOSURE"]


def quarters(first: str, last: str, cutoff: dt.date) -> list[str]:
    y, q = int(first[:4]), int(first[-1])
    ly, lq = int(last[:4]), int(last[-1])
    out = []
    while (y, q) <= (ly, lq):
        q_end = dt.date(y, 3 * q, 1) + dt.timedelta(days=31)
        q_end = q_end.replace(day=1) - dt.timedelta(days=1)
        if q_end <= cutoff:
            out.append(f"{y}q{q}")
        q += 1
        if q == 5:
            y, q = y + 1, 1
    return out


def zip_url(cfg: Config, quarter: str) -> str:
    return f"{cfg['sources']['dera_base_url']}{quarter}_cf.zip"


def download_all(cfg: Config, fetcher: Fetcher) -> list[dict]:
    s = cfg["sources"]
    log = []
    for qtr in quarters(s["dera_first_quarter"], s["dera_last_quarter"], cfg.cutoff):
        res = fetcher.get(zip_url(cfg, qtr), source_kind="dera_zip")
        log.append({"quarter": qtr, "status": res.status, "sha256": res.sha256, "from_cache": res.from_cache})
    return log


def load_tables(cfg: Config, fetcher: Fetcher) -> dict[str, pd.DataFrame]:
    """Load and concatenate DERA tables from cached zips (adds SOURCE_QUARTER, SOURCE_URL)."""
    s = cfg["sources"]
    frames: dict[str, list[pd.DataFrame]] = {t: [] for t in TABLES}
    for qtr in quarters(s["dera_first_quarter"], s["dera_last_quarter"], cfg.cutoff):
        res = fetcher.get(zip_url(cfg, qtr), source_kind="dera_zip")
        if not res.ok:
            continue
        z = zipfile.ZipFile(io.BytesIO(res.bytes()))
        for name in z.namelist():
            base = name.rsplit("/", 1)[-1].replace(".tsv", "")
            if base in frames:
                df = pd.read_csv(z.open(name), sep="\t", dtype=str, keep_default_na=False,
                                 quoting=3, encoding="utf-8", encoding_errors="replace")
                df["SOURCE_QUARTER"] = qtr
                df["SOURCE_URL"] = res.url
                frames[base].append(df)
    out = {}
    for t, lst in frames.items():
        df = pd.concat(lst, ignore_index=True)
        out[t] = df.drop_duplicates(subset=[c for c in df.columns if c not in ("SOURCE_QUARTER", "SOURCE_URL")])
    sub = out["FORM_C_SUBMISSION"]
    sub["FILING_DATE"] = pd.to_datetime(sub["FILING_DATE"], format="%Y%m%d", errors="coerce").dt.date
    # Never treat filings after the outcome cutoff as observable.
    out["FORM_C_SUBMISSION"] = sub[sub["FILING_DATE"] <= cfg.cutoff].copy()
    return out
