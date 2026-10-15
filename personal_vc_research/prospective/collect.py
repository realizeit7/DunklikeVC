"""Capture (full snapshot at first discovery) and scheduled change/follow-up checks.

Collection only: documents and structured facts are stored; nothing here adjudicates outcomes beyond
recording what a filing says (e.g. a C-U's own progress text).
"""
from __future__ import annotations

import datetime as dt
import json
import re

from personal_vc_research.outcomes import classify_filing

from .core import Ctx, iso, next_check_due, norm_utc, parse_utc
from .discover import primary_xml_url, submissions_url
from .extract import form_c_facts, parse_xml, pdf_pages, text_terms

COMPLETION = re.compile(r"closed|conclusion|successful(ly)?\b|completed|ended|total amount sold|raised approximately", re.I)
TRACKED = ("inception", "initial_watchlist")


def _add_facts(ctx: Ctx, oid: str, doc_id: int, facts: list[dict], observed: str) -> int:
    for f in facts:
        ctx.con.execute(
            """INSERT INTO facts(offering_id, document_id, fact_kind, field, value, unit, currency, financial_period, locator,
               extraction_method, verification_status, missing_reason, observed_utc, run_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (oid, doc_id, f["fact_kind"], f["field"], f["value"], f.get("unit", ""), f.get("currency", ""),
             f.get("financial_period", ""), f["locator"], f["extraction_method"], f["verification_status"],
             f.get("missing_reason", ""), observed, ctx.run_id))
    return len(facts)


def snapshot_filing(ctx: Ctx, o, accession: str, filing_date: str, acceptance_utc: str) -> dict:
    """Snapshot one filing: index.json, primary_doc.xml (+ facts) and attachments (+ term candidates)."""
    cik, oid = o["issuer_id"], o["offering_id"]
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
    kw = dict(offering_id=oid, issuer_cik=cik, accession=accession, claimed_publication_date=filing_date,
              verified_public_date=acceptance_utc)
    out = {"documents": 0, "facts": 0, "contract_marker": False, "text_unusable": 0}
    idx_id, r = ctx.snapshot_url(base + "index.json", "sec_filing_index", description="EDGAR filing index", **kw)
    out["documents"] += 1
    if not r.ok:
        return out
    items = [i["name"] for i in json.loads(r.text())["directory"]["item"]]
    items = [n for n in items if not n.endswith((".txt", "-index.html", "-index-headers.html")) and n != "index.json"]
    items = sorted(items, key=lambda n: (n != "primary_doc.xml", n))[: int(ctx.cfg["capture"]["max_documents_per_filing"])]
    for name in items:
        stype = "sec_primary_xml" if name == "primary_doc.xml" else "sec_attachment"
        doc_id, dr = ctx.snapshot_url(base + name, stype, description=name, **kw)
        out["documents"] += 1
        if not dr.ok:
            continue
        observed = norm_utc(dr.retrieved_at_utc)
        if name == "primary_doc.xml":
            try:
                out["facts"] += _add_facts(ctx, oid, doc_id, form_c_facts(parse_xml(dr.bytes())), observed)
            except Exception as exc:  # noqa: BLE001
                ctx.gap("parse_failure", dr.url, repr(exc), oid)
        elif name.lower().endswith(".pdf"):
            if dr.path.stat().st_size > int(ctx.cfg["capture"]["max_bytes_per_document"]):
                ctx.gap("parse_failure", dr.url, "document above size limit; stored, not parsed", oid)
                continue
            try:
                pages = pdf_pages(dr.path)
            except Exception as exc:  # noqa: BLE001
                ctx.gap("parse_failure", dr.url, repr(exc), oid)
                continue
            facts, summ = text_terms(pages)
            out["facts"] += _add_facts(ctx, oid, doc_id, facts, observed)
            status = ("contract_text_marker_found pages " + ",".join(map(str, summ["contract_marker_pages"]))
                      if summ["contract_marker_pages"] else "no_contract_marker_in_text")
            if summ["text_quality"] < 0.85:
                status = f"text_layer_unusable (quality {summ['text_quality']}); OCR not run"
                out["text_unusable"] += 1
                ctx.gap("parse_failure", dr.url, status, oid)
            out["contract_marker"] |= bool(summ["contract_marker_pages"]) and summ["text_quality"] >= 0.85
            out["facts"] += _add_facts(ctx, oid, doc_id, [{
                "field": "document_text_status", "value": f"{name}: {summ['pages']} pages; {status}", "fact_kind": "extracted_fact",
                "locator": name, "extraction_method": "pdfplumber", "verification_status": "text_regex_unreviewed"}], observed)
    return out


def cmd_capture(ctx: Ctx, limit: int | None = None, offering_ids: list[str] | None = None) -> dict:
    lim = int(limit or ctx.cfg["capture"]["initial_batch_size"])
    sql = ("SELECT * FROM offerings WHERE eligibility='eligible' AND cohort IN ('inception','initial_watchlist') "
           "AND captured_utc IS NULL ORDER BY (cohort='inception') DESC, first_observed_utc, offering_id")
    rows = ctx.con.execute(sql).fetchall()
    if offering_ids:
        rows = [r for r in rows if r["offering_id"] in offering_ids]
    stats = {"captured": 0, "documents": 0, "facts": 0, "pending_after_batch": max(0, len(rows) - lim)}
    for o in rows[:lim]:
        led = ctx.con.execute("SELECT filing_date, acceptance_utc FROM discovery_ledger WHERE accession=?",
                              (o["initial_accession"],)).fetchone()
        s = snapshot_filing(ctx, o, o["initial_accession"], led["filing_date"], led["acceptance_utc"])
        stats["documents"] += s["documents"]
        stats["facts"] += s["facts"]
        oid = o["offering_id"]
        ctx.con.execute("INSERT INTO facts(offering_id, document_id, fact_kind, field, value, financial_period, locator, "
                        "extraction_method, verification_status, observed_utc, run_id) VALUES (?,?,?,?,?,'',?,?,?,?,?)",
                        (oid, None, "extracted_fact", "contract_coverage",
                         "contract_text_in_capture_unreviewed" if s["contract_marker"] else "summary_or_unreadable_only",
                         "capture summary", "rule", "text_regex_unreviewed", ctx.now(), ctx.run_id))
        ctx.set_offering(oid, captured_utc=ctx.now())
        stats["captured"] += 1
        ctx.con.commit()
    return stats


def _cu_completion(ctx: Ctx, cik: str, accession: str) -> tuple[bool, str]:
    r = ctx.fetch(primary_xml_url(cik, accession), "sec_primary_xml")
    if not r.ok:
        return False, f"C-U XML not retrievable (HTTP {r.status})"
    try:
        txt = " ".join(parse_xml(r.bytes()).get("progressUpdate", []))
    except Exception as exc:  # noqa: BLE001
        return False, f"C-U XML parse failure {exc!r}"
    return bool(COMPLETION.search(txt)), txt[:400]


def _source_check(ctx: Ctx, oid: str, success: int, covers_from, covers_to, detail: str) -> None:
    """Freshness record (v2.1). 'No new filings' may be stated only for an interval covered by a SUCCESSFUL check."""
    if ctx.con.execute("SELECT 1 FROM sqlite_master WHERE name='source_checks'").fetchone():
        ctx.con.execute("INSERT INTO source_checks(offering_id, source, checked_utc, success, covers_from_utc, covers_to_utc, detail) "
                        "VALUES (?,?,?,?,?,?,?)", (oid, "sec_edgar_submissions", ctx.now(), success,
                                                   norm_utc(covers_from) if covers_from else None, covers_to, detail))


def check_offering(ctx: Ctx, o) -> dict:
    cik, oid, fno = o["issuer_id"], o["offering_id"], o["offering_file_number"]
    out = {"new_events": 0, "ok": True}
    doc_id, r = ctx.snapshot_url(submissions_url(cik), "sec_submissions_json", use_cache=False,
                                 offering_id=oid, issuer_cik=cik, description="EDGAR submissions JSON (change check)")
    now = ctx.now()
    if not r.ok:
        out["ok"] = False
        # outage stays visible; the offering is re-tried on the next run (due date unchanged)
        ctx.set_offering(oid, last_check_utc=now, last_check_ok=0)
        _source_check(ctx, oid, 0, None, now, f"submissions JSON not retrieved (status {getattr(r, 'status', '?')})")
        return out
    rec = json.loads(r.text())["filings"]["recent"]
    observed = norm_utc(r.retrieved_at_utc)
    _source_check(ctx, oid, 1, o["initial_filing_date"], observed,
                  f"EDGAR submissions JSON listing {len(rec['form'])} recent filings for CIK {cik}")
    avail, closing = o["availability_status"], o["closing_status"]
    for form, fdate, fnum, acc, acc_dt in zip(rec["form"], rec["filingDate"], rec["fileNumber"], rec["accessionNumber"],
                                             rec["acceptanceDateTime"]):
        if fdate < (o["initial_filing_date"] or "") or acc == o["initial_accession"]:
            continue
        if ctx.con.execute("SELECT 1 FROM events WHERE offering_id=? AND accession=?", (oid, acc)).fetchone():
            continue
        claim, interp, etype = f"{form} filed {fdate} (file {fnum})", "", ""
        if fnum == fno and form == "C/A":
            etype, interp = "offering_amendment_filed", "amendment of the same offering (not a new offering)"
            snapshot_filing(ctx, o, acc, fdate, norm_utc(acc_dt) if acc_dt else "")
            ctx.set_offering(oid, amendment_accessions=";".join(filter(None, [o["amendment_accessions"], acc])))
        elif fnum == fno and form == "C-U":
            done, txt = _cu_completion(ctx, cik, acc)
            etype, claim = "progress_update_filed", f"C-U {fdate}: {txt}"
            interp = "issuer-reported close (completion language in C-U)" if done else "progress update; no completion language"
            if done:
                closing, avail = "close_reported_c_u", "closed_reported"
        elif fnum == fno and form == "C-W":
            etype, interp = "offering_withdrawn_c_w", "Form C-W filed; whether commitments were received is not stated"
            closing, avail = "withdrawn_c_w", "withdrawn"
        else:
            etype, _, note = classify_filing(form, fnum, fno)
            if not etype:
                continue
            interp = note
        ctx.con.execute("""INSERT OR IGNORE INTO events(offering_id, issuer_cik, event_type, event_date, publication_date,
                           observed_utc, source_document_id, accession, source_claim, interpretation, uncertainty, run_id)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (oid, cik, etype, fdate, fdate, observed, doc_id, acc, claim, interp,
                         "event date = filing date (the underlying business event may differ)", ctx.run_id))
        out["new_events"] += 1
    fields = dict(last_check_utc=now, last_check_ok=1, closing_status=closing, availability_status=avail,
                  next_check_due_utc=next_check_due(avail, closing, now, ctx.cfg))
    if avail != o["availability_status"]:
        fields["availability_evidence"] = "EDGAR filing (C-U completion language or C-W)"
    ctx.set_offering(oid, evidence=f"submissions JSON document {doc_id}", **fields)
    return out


def probe_platform(ctx: Ctx) -> str:
    """At most one probe per run; a recent block is not retried within the cooldown."""
    url = ctx.cfg["platform"]["public_page_probe_url"]
    cool = int(ctx.cfg["platform"]["block_cooldown_days"])
    last = ctx.con.execute("SELECT MAX(utc) FROM gaps WHERE url=? AND kind='access_blocked'", (url,)).fetchone()[0]
    if last and parse_utc(ctx.now()) - parse_utc(last) < dt.timedelta(days=cool):
        return f"skipped (blocked {last[:10]}; cooldown {cool} days)"
    r = ctx.fetch(url, "platform_page", use_cache=False, log_gap=False)
    body = r.bytes()[:4000].decode("utf-8", "replace") if r.ok else ""
    if not r.ok or "challenge" in body.lower() or "cf-chl" in body:
        ctx.gap("access_blocked", url, f"HTTP {r.status}; platform pages treated as inaccessible (no bypass attempted)")
        return f"blocked (HTTP {r.status})"
    ctx.record_document(url=url, source_type="platform_page", data=r.bytes(), retrieved_utc=norm_utc(r.retrieved_at_utc),
                        description="platform probe page")
    return "accessible"


def cmd_followup(ctx: Ctx) -> dict:
    now = ctx.now()
    due = ctx.con.execute("SELECT * FROM offerings WHERE eligibility='eligible' AND cohort IN ('inception','initial_watchlist') "
                          "AND (next_check_due_utc IS NULL OR next_check_due_utc <= ?) ORDER BY next_check_due_utc", (now,)).fetchall()
    stats = {"due": len(due), "checked_ok": 0, "failed": 0, "new_events": 0, "platform_probe": probe_platform(ctx)}
    for o in due:
        s = check_offering(ctx, o)
        stats["checked_ok" if s["ok"] else "failed"] += 1
        stats["new_events"] += s["new_events"]
        ctx.con.commit()
    return stats
