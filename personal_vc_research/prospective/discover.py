"""SEC-led discovery of Republic Reg CF offerings.

Source of record: the EDGAR daily form index (all filings of a day) -> every initial Form C ('C') -> its XML
intermediary block (commissionCik / commissionFileNumber). Offering identity = issuer CIK + offering file number
(020-xxxxx), so amendments never create a second offering and separate rounds stay distinct.
"""
from __future__ import annotations

import datetime as dt
import re

from personal_vc_research.frame import classify_security

from .core import Ctx, get_clock, iso, next_check_due, norm_utc, parse_utc, start_clock
from .extract import parse_xml

WEEKEND = {5, 6}


def offering_id(issuer_cik: str, file_number: str) -> str:
    return f"RCF-{int(issuer_cik)}-{file_number}"


def index_url(day: dt.date) -> str:
    return f"https://www.sec.gov/Archives/edgar/daily-index/{day.year}/QTR{(day.month - 1) // 3 + 1}/form.{day:%Y%m%d}.idx"


def parse_form_index(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not re.match(r"^(C|C/A|C-U|C-W)\s", line):
            continue
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 5:
            continue
        form, company, cik, date, fname = parts[0], parts[1], parts[2], parts[3], parts[4]
        acc = fname.rsplit("/", 1)[-1].removesuffix(".txt")
        rows.append({"form": form, "company": company, "cik": cik.zfill(10), "date": f"{date[:4]}-{date[4:6]}-{date[6:]}",
                     "accession": acc})
    return rows


def primary_xml_url(cik: str, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/primary_doc.xml"


def submissions_url(cik: str) -> str:
    return f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"


def eligibility(x: dict, cfg) -> tuple[str, str, str, str]:
    name = (x.get("nameOfIssuer") or [""])[0]
    inter = (x.get("companyName") or [""])[0].lower()
    if any(p in inter for p in cfg["platform"]["exclude_name_patterns"]):
        return "excluded", "excluded intermediary name", "", ""
    cls, ev = classify_security((x.get("securityOfferedType") or [""])[0], (x.get("securityOfferedOtherDesc") or [""])[0],
                                name, (x.get("issuerWebsite") or [""])[0])
    if cls in cfg["security_filter"]["include_classes"]:
        return "eligible", "security class included", cls, ev
    return "excluded", f"security class {cls}", cls, ev


def _is_republic(x: dict, cfg) -> bool:
    cik = (x.get("commissionCik") or [""])[0].zfill(10)
    fno = (x.get("commissionFileNumber") or [""])[0]
    return cik in cfg["platform"]["intermediary_ciks"] or fno in cfg["platform"]["intermediary_file_numbers"]


def _filing_meta(sub: dict, accession: str) -> dict:
    r = sub["filings"]["recent"]
    for i, a in enumerate(r["accessionNumber"]):
        if a == accession:
            return {"form": r["form"][i], "filing_date": r["filingDate"][i], "file_number": r["fileNumber"][i],
                    "acceptance_utc": norm_utc(r["acceptanceDateTime"][i]) if r["acceptanceDateTime"][i] else ""}
    return {}


def register_initial_form_c(ctx: Ctx, cik: str, accession: str, source: str, clock: dict, startup: bool) -> str | None:
    """Fetch an initial Form C's XML; if Republic, add it to the ledger and offerings. Returns offering_id or None."""
    if ctx.con.execute("SELECT 1 FROM discovery_ledger WHERE accession=?", (accession,)).fetchone():
        return None
    xr = ctx.fetch(primary_xml_url(cik, accession), "sec_primary_xml")
    if not xr.ok:
        return None
    try:
        x = parse_xml(xr.bytes())
    except Exception as exc:  # noqa: BLE001 - record and continue
        ctx.gap("parse_failure", xr.url, repr(exc))
        return None
    if not _is_republic(x, ctx.cfg):
        return None
    sr = ctx.fetch(submissions_url(cik), "sec_submissions_json", use_cache=False)
    meta = _filing_meta(__import__("json").loads(sr.text()), accession) if sr.ok else {}
    fno = meta.get("file_number") or ""
    if not fno:
        ctx.gap("parse_failure", sr.url, f"offering file number not found for {accession}")
        return None
    oid = offering_id(cik, fno)
    now = ctx.now()
    ctx.con.execute("""INSERT OR IGNORE INTO discovery_ledger(accession, form, issuer_cik, offering_file_number, filing_date,
                       acceptance_utc, intermediary_cik, intermediary_file_number, first_observed_utc, run_id, source, offering_id)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (accession, "C", cik, fno, meta.get("filing_date"), meta.get("acceptance_utc"),
                     (x.get("commissionCik") or [""])[0], (x.get("commissionFileNumber") or [""])[0], now, ctx.run_id, source, oid))
    if ctx.con.execute("SELECT 1 FROM offerings WHERE offering_id=?", (oid,)).fetchone():
        return oid
    elig, reason, cls, ev = eligibility(x, ctx.cfg)
    acc_utc = meta.get("acceptance_utc") or ""
    start = clock.get("pilot_start_utc")
    deadline = (x.get("deadlineDate") or [""])[0]
    deadline_iso = f"{deadline[6:]}-{deadline[:2]}-{deadline[3:5]}" if re.match(r"\d\d-\d\d-\d{4}", deadline) else ""
    if start and acc_utc and acc_utc >= start:
        cohort = "inception"
    elif startup and ctx.cfg["discovery"]["watchlist_enabled"] and deadline_iso and deadline_iso >= now[:10]:
        cohort = "initial_watchlist"   # left-truncated; never mixed into inception statistics
    else:
        cohort = "pre_start_other"
    forms_later = _later_offering_forms(__import__("json").loads(sr.text()), fno) if sr.ok else set()
    closing = "withdrawn_c_w" if "C-W" in forms_later else "none_reported"
    if cohort == "initial_watchlist" and closing == "withdrawn_c_w":
        cohort = "pre_start_other"
    avail = "withdrawn" if closing == "withdrawn_c_w" else "unknown"
    ctx.con.execute(
        """INSERT INTO offerings(offering_id, issuer_id, offering_file_number, legal_name, intermediary_cik,
           intermediary_file_number, initial_accession, initial_filing_date, initial_acceptance_utc, cohort, eligibility,
           eligibility_reason, security_class, security_evidence, deadline_date, first_observed_utc, first_observed_run,
           discovery_source, availability_status, availability_evidence, closing_status, last_check_utc, last_check_ok,
           next_check_due_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (oid, cik, fno, (x.get("nameOfIssuer") or [""])[0], (x.get("commissionCik") or [""])[0],
         (x.get("commissionFileNumber") or [""])[0], accession, meta.get("filing_date"), acc_utc, cohort, elig, reason, cls, ev,
         deadline_iso, now, ctx.run_id, source, avail,
         "platform page not verified (Republic public pages not accessible); a future deadline is not proof of availability"
         if avail == "unknown" else "Form C-W on EDGAR", closing, now, 1, next_check_due(avail, closing, now, ctx.cfg)))
    return oid


def _later_offering_forms(sub: dict, file_number: str) -> set[str]:
    r = sub["filings"]["recent"]
    return {f for f, fn in zip(r["form"], r["fileNumber"]) if fn == file_number}


def scan_days(ctx: Ctx, days: list[dt.date], clock: dict, startup: bool) -> dict:
    stats = {"days_complete": 0, "days_pending": 0, "form_c_seen": 0, "republic_new": 0}
    today = dt.date.fromisoformat(ctx.now()[:10])
    for day in days:
        if ctx.con.execute("SELECT 1 FROM index_days WHERE day=? AND status='complete'", (day.isoformat(),)).fetchone():
            continue
        url = index_url(day)
        r = ctx.fetch(url, "sec_daily_index", log_gap=False)
        if not r.ok and r.from_cache:
            r = ctx.fetch(url, "sec_daily_index", use_cache=False, log_gap=False)
        if not r.ok:
            if day.weekday() in WEEKEND:
                status = "no_index_weekend"
            elif (today - day).days <= 3:
                status = "not_yet_available"
                stats["days_pending"] += 1
            else:
                status = "missing"
                ctx.gap("index_unavailable", url, f"HTTP {r.status} for a past business day (holiday or outage)")
            if status != "not_yet_available":
                ctx.con.execute("INSERT OR REPLACE INTO index_days VALUES (?,?,?,?,?,?)",
                                (day.isoformat(), ctx.now(), ctx.run_id, 0, 0, status))
            continue
        rows = [x for x in parse_form_index(r.text()) if x["form"] == "C"]
        n_rep = 0
        for x in rows:
            stats["form_c_seen"] += 1
            if register_initial_form_c(ctx, x["cik"], x["accession"], "edgar_daily_index", clock, startup):
                n_rep += 1
        stats["republic_new"] += n_rep
        stats["days_complete"] += 1
        ctx.con.execute("INSERT OR REPLACE INTO index_days VALUES (?,?,?,?,?,?)",
                        (day.isoformat(), ctx.now(), ctx.run_id, len(rows), n_rep, "complete"))
        ctx.con.commit()
    return stats


def watchlist_from_fts(ctx: Ctx, clock: dict) -> int:
    """Optional startup watchlist: Republic Form Cs found by EDGAR full-text search (completeness unverified)."""
    end = dt.date.fromisoformat(ctx.now()[:10])
    start = end - dt.timedelta(days=int(ctx.cfg["discovery"]["watchlist_fts_lookback_days"]))
    n = 0
    for fno in ctx.cfg["platform"]["intermediary_file_numbers"]:
        frm = 0
        while True:
            url = (f"https://efts.sec.gov/LATEST/search-index?q=%22{fno}%22&forms=C&dateRange=custom"
                   f"&startdt={start}&enddt={end}&from={frm}")
            r = ctx.fetch(url, "sec_fts", use_cache=False)
            if not r.ok:
                break
            hits = __import__("json").loads(r.text())["hits"]["hits"]
            for h in hits:
                acc = h["_id"].split(":")[0]
                cik = h["_source"]["ciks"][0].zfill(10)
                if h["_source"].get("form") == "C" and register_initial_form_c(ctx, cik, acc, "edgar_full_text_search", clock, True):
                    n += 1
            ctx.con.commit()
            if len(hits) < 100:
                break
            frm += 100
    return n


def cmd_discover(ctx: Ctx) -> dict:
    clock = get_clock(ctx)
    startup = not clock
    today = dt.date.fromisoformat(ctx.now()[:10])
    if startup:
        lookback = int(ctx.cfg["discovery"]["first_run_lookback_days"])
        days = [today - dt.timedelta(days=i) for i in range(lookback, -1, -1)]
        # the clock is the start of the first discovery run; set only if the run succeeds (below)
        provisional = {"pilot_start_utc": ctx.con.execute("SELECT started_utc FROM runs WHERE run_id=?",
                                                         (ctx.run_id,)).fetchone()[0]}
    else:
        done = ctx.con.execute("SELECT MAX(day) FROM index_days").fetchone()[0]
        # with no scan history (e.g. a fresh database on a new machine) resume from the pilot start, never skip days
        first = dt.date.fromisoformat(done) + dt.timedelta(days=1) if done else dt.date.fromisoformat(clock["pilot_start_utc"][:10])
        first = min(first, today - dt.timedelta(days=3))   # days whose index was pending are re-checked
        days = [first + dt.timedelta(days=i) for i in range((today - first).days + 1)]
        provisional = clock
    stats = scan_days(ctx, days, provisional, startup)
    if startup:
        if stats["days_complete"] == 0:
            raise RuntimeError("no daily index could be retrieved: pilot clock NOT started")
        clock = start_clock(ctx, provisional["pilot_start_utc"])
        if ctx.cfg["discovery"]["watchlist_enabled"]:
            stats["watchlist_fts_new"] = watchlist_from_fts(ctx, clock)
    ctx.con.commit()
    return stats
