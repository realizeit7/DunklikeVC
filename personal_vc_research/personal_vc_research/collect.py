"""Collection: offering, historical-fact, source, outcome-event and payout-evidence tables.

Automated (SEC): issuer filing index, original Form C XML + offering PDF, DERA structured
fields for C, C/A, C-U, C-AR, C-TR, Form D XML, C-TR documents, and document probes.
Manual, provenance-backed imports (data/manual/):
  pilot_manual_facts.csv        analyst extraction from rendered / OCR'd Form C pages
  outcome_evidence_manual.csv   bounded public-web outcome evidence (<= 3 searches/offering)
  document_probes.csv           extra SEC documents to fetch and pattern-search (e.g. 10-K)
Every fact/event carries a source_id; missing values are rows with a missing_reason, never 0.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

from . import dera
from .config import Config
from .frame import decision_date
from .http import BudgetExhausted, Fetcher, utcnow_iso
from .outcomes import classify_filing, summarize_outcomes

SEC = "https://www.sec.gov/Archives/edgar/data"
OFFERING_FORMS = {"C", "C/A", "C-U", "C-W"}

# DERA disclosure fields -> (fact_name, unit, period_label)
FIN_FIELDS = [
    ("TOTALASSETMOSTRECENTFISCALYEAR", "total_assets", "most_recent_fy"),
    ("TOTALASSETPRIORFISCALYEAR", "total_assets", "prior_fy"),
    ("CASHEQUIMOSTRECENTFISCALYEAR", "cash_and_equivalents", "most_recent_fy"),
    ("CASHEQUIPRIORFISCALYEAR", "cash_and_equivalents", "prior_fy"),
    ("ACTRECEIVEDRECENTFISCALYEAR", "accounts_receivable", "most_recent_fy"),
    ("SHORTTERMDEBTMRECENTFISCALYEAR", "short_term_debt", "most_recent_fy"),
    ("LONGTERMDEBTRECENTFISCALYEAR", "long_term_debt", "most_recent_fy"),
    ("REVENUEMOSTRECENTFISCALYEAR", "revenue", "most_recent_fy"),
    ("REVENUEPRIORFISCALYEAR", "revenue", "prior_fy"),
    ("COSTGOODSSOLDRECENTFISCALYEAR", "cost_of_goods_sold", "most_recent_fy"),
    ("NETINCOMEMOSTRECENTFISCALYEAR", "net_income", "most_recent_fy"),
    ("NETINCOMEPRIORFISCALYEAR", "net_income", "prior_fy"),
]
TERM_FIELDS = [
    ("OFFERINGAMOUNT", "target_offering_amount", "USD"),
    ("MAXIMUMOFFERINGAMOUNT", "maximum_offering_amount", "USD"),
    ("PRICE", "price_per_security", "USD"),
    ("DEADLINEDATE", "offering_deadline", "date"),
    ("OVERSUBSCRIPTIONACCEPTED", "oversubscription_accepted", "flag"),
    ("COMPENSATIONAMOUNT", "intermediary_compensation", "text"),
    ("FINANCIALINTEREST", "intermediary_financial_interest", "text"),
    ("CURRENTEMPLOYEES", "employees", "count"),
]
MONEY = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


class Ctx:
    """Per-run accumulators."""

    def __init__(self, cfg: Config, fetcher: Fetcher):
        self.cfg, self.f = cfg, fetcher
        self.sources: dict[str, dict] = {}
        self.facts: list[dict] = []
        self.events: list[dict] = []
        self.payout: list[dict] = []
        self.filings: list[dict] = []
        self.doc_count: dict[str, int] = {}
        self.budget_notes: dict[str, list] = {}

    def source(self, url: str, source_type: str, form: str = "", accession: str = "", pub: str = "",
               res=None, issuer_cik: str = "", note: str = "") -> str:
        sid = _sid(url)
        if sid not in self.sources:
            self.sources[sid] = {
                "source_id": sid, "url": url, "accession": accession, "form_type": form,
                "source_type": source_type, "publication_date": pub, "issuer_cik": issuer_cik,
                "retrieved_at_utc": getattr(res, "retrieved_at_utc", "") if res else "",
                "cache_path": str(res.path.relative_to(self.cfg.root)) if res is not None and res.path else "",
                "sha256": getattr(res, "sha256", "") if res else "", "note": note}
        return sid

    def fetch_doc(self, oid: str, url: str, kind: str):
        """Fetch a *relevant document* counted against the per-offering budget."""
        limit = int(self.cfg["collection"]["max_documents_per_offering"])
        used = self.doc_count.get(oid, 0)
        if used >= limit:
            self.budget_notes.setdefault(oid, []).append(f"document budget exhausted; skipped {url}")
            return None
        res = self.f.get(url, kind)
        self.doc_count[oid] = used + 1
        return res


def _sid(url: str) -> str:
    import hashlib
    return "SRC-" + hashlib.sha256(url.encode()).hexdigest()[:12]


def fact(ctx: Ctx, oid: str, cik: str, group: str, name: str, value, unit: str, *, source_id: str,
         locator: str, public_date: str, decision: str, method: str, period_label: str = "",
         period_end: str = "", excerpt: str = "", availability: str = "verified", verification: str = "",
         derivation: str = "", missing_reason: str = "", economic_date: str = "", claim_type: str = "") -> None:
    is_missing = value is None or (isinstance(value, str) and value.strip() == "")
    num = None if is_missing else (_num(value) if unit not in ("text", "date", "flag") else None)
    ctx.facts.append({
        "fact_id": f"F{len(ctx.facts) + 1:05d}", "offering_id": oid, "issuer_cik": cik, "fact_group": group,
        "fact_name": name, "value_text": "" if is_missing else str(value), "value_num": num, "unit": unit,
        "period_label": period_label, "period_end": period_end, "economic_date": economic_date,
        "public_available_date": public_date, "decision_date": decision,
        "eligible_at_decision": bool(public_date) and public_date <= decision,
        "availability_status": availability, "source_id": source_id, "locator": locator,
        "evidence_excerpt": excerpt[:400], "extraction_method": method, "verification_status": verification,
        "claim_type": claim_type, "derivation": derivation,
        "missing": is_missing, "missing_reason": missing_reason if is_missing else ""})


def event(ctx: Ctx, oid: str, cik: str, etype: str, *, event_date: str, publication_date: str, strength: str,
          source_id: str, locator: str, details: str, attribution: str, date_basis: str = "") -> None:
    ctx.events.append({
        "event_id": f"E{len(ctx.events) + 1:05d}", "offering_id": oid, "issuer_cik": cik, "event_type": etype,
        "event_date": event_date, "event_date_basis": date_basis, "publication_date": publication_date,
        "evidence_strength": strength, "attribution_level": attribution, "source_id": source_id,
        "locator": locator, "details": details[:600]})


def load_manual(cfg: Config, name: str) -> pd.DataFrame:
    p = cfg.path("manual_dir") / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p, dtype=str, keep_default_na=False)


def submissions(ctx: Ctx, cik: str) -> dict:
    res = ctx.f.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", "submissions_index")
    d = json.loads(res.text())
    rows = []
    blocks = [d["filings"]["recent"]]
    for extra in d["filings"].get("files", []):
        r2 = ctx.f.get(f"https://data.sec.gov/submissions/{extra['name']}", "submissions_index")
        blocks.append(json.loads(r2.text()))
    for b in blocks:
        for i in range(len(b["form"])):
            rows.append({"form": b["form"][i], "filing_date": b["filingDate"][i],
                         "accession": b["accessionNumber"][i], "file_number": b["fileNumber"][i],
                         "primary_document": b["primaryDocument"][i],
                         "acceptance": b.get("acceptanceDateTime", [""] * len(b["form"]))[i]})
    d["_rows"] = rows
    d["_res"] = res
    return d


def parse_form_c_xml(text: str) -> dict:
    """Flatten Form C primary_doc.xml leaf elements (namespace-stripped tag -> text, first wins)."""
    out: dict[str, str] = {}
    root = ET.fromstring(text.encode())
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if el.text and el.text.strip() and tag not in out:
            out[tag] = el.text.strip()
    return out


def parse_form_d(text: str) -> dict:
    g = lambda tag: (re.findall(rf"<{tag}>(.*?)</{tag}>", text, re.S) or [""])[0].strip()
    first_sale = re.search(r"<dateOfFirstSale>\s*<value>(.*?)</value>", text, re.S)
    return {"date_of_first_sale": first_sale.group(1) if first_sale else "",
            "first_sale_yet_to_occur": "yetToOccur" in text,
            "total_offering_amount": g("totalOfferingAmount"), "total_amount_sold": g("totalAmountSold"),
            "total_remaining": g("totalRemaining"), "industry": g("industryGroupType"),
            "exemptions": ";".join(re.findall(r"<item>(.*?)</item>", text)),
            "is_amendment": g("isAmendment"), "investors": g("totalNumberAlreadyInvested")}


def collect_offering(ctx: Ctx, off: pd.Series, dtabs: dict, manual: dict) -> dict:
    cfg = ctx.cfg
    oid, cik, fnum = off["offering_id"], off["issuer_cik"], off["file_number"]
    cik_i = str(int(cik))
    acc0 = off["initial_accession"]
    t0 = time.monotonic()
    dec = decision_date(off["initial_filing_date"], cfg.decision_days)
    cutoff = cfg.cutoff.isoformat()

    # -- issuer filing index (lightweight, not counted) --------------------------------------
    sub = submissions(ctx, cik)
    sid_sub = ctx.source(sub["_res"].url, "sec_index", "submissions", pub="", res=sub["_res"], issuer_cik=cik,
                         note="EDGAR issuer filing index (current snapshot; lists historical filings with dates)")
    rows = [r for r in sub["_rows"] if r["filing_date"] <= cutoff]
    for r in rows:
        ctx.filings.append({"offering_id": oid, "issuer_cik": cik, **r,
                            "same_offering_file_number": r["file_number"] == fnum,
                            "after_decision_date": r["filing_date"] > dec})
    former = [x.get("name", "") for x in sub.get("formerNames", [])]

    # -- original Form C documents ---------------------------------------------------------------
    acc_path = acc0.replace("-", "")
    idx = ctx.f.get(f"{SEC}/{cik_i}/{acc_path}/index.json", "edgar_index")
    items = json.loads(idx.text())["directory"]["item"]
    xml_res = ctx.fetch_doc(oid, f"{SEC}/{cik_i}/{acc_path}/primary_doc.xml", "form_c_xml")
    sid_xml = ctx.source(xml_res.url, "sec_filing_structured", "C", acc0, off["initial_filing_date"], xml_res, cik)
    xml = parse_form_c_xml(xml_res.text()) if xml_res and xml_res.ok else {}
    pdfs = sorted([i for i in items if i["name"].lower().endswith(".pdf")], key=lambda i: -int(i["size"] or 0))
    pdf_url = f"{SEC}/{cik_i}/{acc_path}/{pdfs[0]['name']}" if pdfs else ""
    pdf_res = ctx.fetch_doc(oid, pdf_url, "form_c_attachment") if pdf_url else None
    sid_pdf = ctx.source(pdf_url, "sec_filing_document", "C", acc0, off["initial_filing_date"], pdf_res, cik,
                         note="Form C offering memorandum PDF (issuer statements + reviewed financials)") if pdf_url else ""

    # -- DERA structured rows for this offering / issuer ---------------------------------------------
    m = dtabs["m"]
    issuer_rows = m[m["CIK"] == cik].sort_values("FILING_DATE")
    rep_ciks = set(cfg["platform"]["intermediary_ciks"])
    off_rows = issuer_rows[(issuer_rows["FILE_NUMBER"] == fnum) & issuer_rows["SUBMISSION_TYPE"].isin(OFFERING_FORMS)]
    off_rows = off_rows[off_rows["COMMISSIONCIK"].isin(rep_ciks | {""}) | (off_rows["SUBMISSION_TYPE"] == "C-W")]
    dera_url = lambda r: r["SOURCE_URL"]

    def dera_source(r):
        return ctx.source(f"{dera_url(r)}#{r['ACCESSION_NUMBER']}", "sec_bulk_dataset", r["SUBMISSION_TYPE"],
                          r["ACCESSION_NUMBER"], r["FILING_DATE"].isoformat(), None, cik,
                          note="SEC DERA crowdfunding data set row (structured extract of the filing XML)")

    # Historical facts from the initial Form C and C/As (eligibility by filing date)
    for _, r in off_rows[off_rows["SUBMISSION_TYPE"].isin(["C", "C/A"])].iterrows():
        sid = dera_source(r)
        pub = r["FILING_DATE"].isoformat()
        tag = "initial_form_c" if r["ACCESSION_NUMBER"] == acc0 else "form_c_amendment"
        for col, name, label in FIN_FIELDS:
            v = r[col]
            fact(ctx, oid, cik, "financial", name, v if v != "" else None, "USD", source_id=sid,
                 locator=f"DERA FORM_C_DISCLOSURE.{col} ({tag})", public_date=pub, decision=dec,
                 method="structured_field", period_label=label, verification="structured_filing_field",
                 claim_type="issuer_reported_financials", missing_reason="field blank in filing",
                 derivation="as filed; fiscal-year end date not in structured data (see manual facts)")
        for col, name, unit in TERM_FIELDS:
            v = r[col]
            fact(ctx, oid, cik, "offering_terms", name, v if v != "" else None, unit, source_id=sid,
                 locator=f"DERA FORM_C_DISCLOSURE.{col} ({tag})", public_date=pub, decision=dec,
                 method="structured_field", verification="structured_filing_field",
                 claim_type="issuer_statement_in_filing", missing_reason="field blank in filing")
        if tag == "form_c_amendment":
            fact(ctx, oid, cik, "offering_terms", "amendment_nature", r["NATUREOFAMENDMENT"] or None, "text",
                 source_id=sid, locator="DERA NATUREOFAMENDMENT", public_date=pub, decision=dec,
                 method="structured_field", missing_reason="nature of amendment blank")
    # Company facts from the initial Form C
    r0 = off_rows[off_rows["ACCESSION_NUMBER"] == acc0]
    if len(r0):
        r0 = r0.iloc[0]
        sid = dera_source(r0)
        for col, name in [("DATEINCORPORATION", "date_incorporation"), ("LEGALSTATUSFORM", "legal_status"),
                          ("JURISDICTIONORGANIZATION", "jurisdiction"), ("ISSUERWEBSITE", "website")]:
            fact(ctx, oid, cik, "company", name, r0[col] or None, "text", source_id=sid,
                 locator=f"DERA FORM_C_ISSUER_INFORMATION.{col}", public_date=off["initial_filing_date"],
                 decision=dec, method="structured_field", missing_reason="field blank in filing")

    # Prior Form D filings available before the decision date (historical financing context)
    for r in rows:
        if r["form"] in ("D", "D/A") and r["filing_date"] <= dec:
            url = f"{SEC}/{cik_i}/{r['accession'].replace('-', '')}/primary_doc.xml"
            res = ctx.fetch_doc(oid, url, "form_d")
            if res is None or not res.ok:
                continue
            d = parse_form_d(res.text())
            sid = ctx.source(url, "sec_filing_structured", r["form"], r["accession"], r["filing_date"], res, cik)
            fact(ctx, oid, cik, "company", "prior_form_d_total_amount_sold", d["total_amount_sold"] or None, "USD",
                 source_id=sid, locator="Form D totalAmountSold", public_date=r["filing_date"], decision=dec,
                 method="structured_field", excerpt=json.dumps(d), claim_type="issuer_statement_in_filing",
                 missing_reason="not stated")

    # -- manual facts (provenance-backed analyst extraction) ------------------------------------------
    mf = manual["facts"]
    if len(mf):
        for _, r in mf[mf["offering_id"] == oid].iterrows():
            url = r["doc_url"]
            res = ctx.f.cached(url)
            sid = ctx.source(url, r.get("source_type") or "sec_filing_document", r.get("form_type", "C"),
                             pub=r["public_available_date"], res=res, issuer_cik=cik)
            fact(ctx, oid, cik, r["fact_group"], r["fact_name"], r["value_text"] or None, r["unit"],
                 source_id=sid, locator=f"page {r['page']}" if r["page"] else r.get("locator", ""),
                 public_date=r["public_available_date"], decision=dec, method=r["extraction_method"],
                 period_label=r.get("period_label", ""), period_end=r.get("period_end", ""),
                 excerpt=r["evidence_excerpt"], verification=r["verification_status"],
                 claim_type=r.get("claim_type", ""), derivation=r.get("notes", ""),
                 availability=r.get("availability_status") or "verified",
                 missing_reason=r.get("missing_reason", ""))

    # -- availability at decision date ------------------------------------------------------------------
    pre = off_rows[off_rows["FILING_DATE"].map(lambda d: d.isoformat()) <= dec]
    deadline = ""
    for _, r in pre[pre["SUBMISSION_TYPE"].isin(["C", "C/A"])].iterrows():
        if r["DEADLINEDATE"]:
            deadline = r["DEADLINEDATE"]
    withdrawn_pre = (pre["SUBMISSION_TYPE"] == "C-W").any()
    cu_pre = pre[pre["SUBMISSION_TYPE"] == "C-U"]
    closed_pre = cu_pre["PROGRESSUPDATE"].str.contains(r"closed|conclusion of the offering|ended", case=False).any() if len(cu_pre) else False
    if withdrawn_pre:
        avail = "withdrawn_before_decision"
    elif not deadline:
        avail = "unknown_no_deadline_in_filings"
    elif deadline < dec:
        avail = "closed_before_decision_deadline_passed"
    elif closed_pre:
        avail = "closed_before_decision_per_progress_update"
    else:
        avail = "inferred_open_per_filings"

    # -- completion evidence (offering level) -------------------------------------------------------------
    cu = off_rows[off_rows["SUBMISSION_TYPE"] == "C-U"]
    amount_reported, completion_note, completion_date = None, "", ""
    for _, r in cu.iterrows():
        sid = dera_source(r)
        txt = r["PROGRESSUPDATE"]
        amts = [_num(a) for a in MONEY.findall(txt)]
        final = bool(re.search(r"closed|conclusion|successfully (raised|completed|received)|ended", txt, re.I))
        if final and amts:
            amount_reported, completion_note, completion_date = amts[0], txt, r["FILING_DATE"].isoformat()
        event(ctx, oid, cik, "offering_completion_reported" if final else "progress_update",
              event_date=r["FILING_DATE"].isoformat(), date_basis="C-U filing date",
              publication_date=r["FILING_DATE"].isoformat(), strength="filing_evidence",
              source_id=sid, locator="DERA FORM_C_ISSUER_INFORMATION.PROGRESSUPDATE", attribution="offering",
              details=f"{txt} [completion evidence only; not investor profit]")
    withdrawn = (off_rows["SUBMISSION_TYPE"] == "C-W").any()
    issuer_car = issuer_rows[issuer_rows["SUBMISSION_TYPE"].isin(["C-AR", "C-AR/A"])]
    n_rep_offerings = int(off.get("n_initial_form_c_any_platform") or 1)
    if withdrawn:
        completion = "withdrawn"
    elif amount_reported:
        completion = "completion_reported_C-U"
    elif len(issuer_car):
        completion = "inferred_sold_C-AR_filed" + ("" if n_rep_offerings == 1 else "_issuer_has_other_offerings")
    else:
        completion = "unknown"

    # -- outcome events from the issuer filing index -----------------------------------------------------
    for r in rows:
        if r["filing_date"] <= off["initial_filing_date"] and r["form"] not in ("C-TR",):
            continue
        etype, strength, note = classify_filing(r["form"], r["file_number"], fnum)
        if not etype:
            continue
        url = f"{SEC}/{cik_i}/{r['accession'].replace('-', '')}/"
        sid = ctx.source(url, "sec_filing_index_entry", r["form"], r["accession"], r["filing_date"], None, cik)
        details = note
        if r["form"] in ("D", "D/A") and r["filing_date"] > dec:
            res = ctx.fetch_doc(oid, url + "primary_doc.xml", "form_d")
            if res is not None and res.ok:
                d = parse_form_d(res.text())
                sid = ctx.source(res.url, "sec_filing_structured", r["form"], r["accession"], r["filing_date"], res, cik)
                details = (f"{note} first_sale={d['date_of_first_sale'] or ('yet to occur' if d['first_sale_yet_to_occur'] else 'n/a')}; "
                           f"offering_amount={d['total_offering_amount']}; amount_sold_as_reported={d['total_amount_sold']}; "
                           f"investors={d['investors']}; exemptions={d['exemptions']}")
        if r["form"] == "C-TR":
            reason = ctr_reason(ctx, oid, cik_i, r)
            details = f"{note} Stated reason: {reason}"
        attribution = "offering" if r["file_number"] == fnum and r["form"] in OFFERING_FORMS else "issuer"
        event(ctx, oid, cik, etype, event_date=r["filing_date"], date_basis=f"{r['form']} filing date",
              publication_date=r["filing_date"], strength=strength, source_id=sid,
              locator=f"accession {r['accession']}", details=details, attribution=attribution)
    # C-AR structured financials -> reported operating activity
    for _, r in issuer_car.iterrows():
        sid = dera_source(r)
        rev = _num(r["REVENUEMOSTRECENTFISCALYEAR"]) if r["REVENUEMOSTRECENTFISCALYEAR"] else None
        per = r["PERIOD"]
        per_s = f"{per[:4]}-{per[4:6]}-{per[6:]}" if len(per) == 8 else ""
        if rev is not None and rev > 0:
            event(ctx, oid, cik, "operating_activity_reported", event_date=per_s,
                  date_basis="C-AR PERIOD (fiscal period end as filed)", publication_date=r["FILING_DATE"].isoformat(),
                  strength="issuer_reported_financials", source_id=sid, locator="DERA C-AR REVENUEMOSTRECENTFISCALYEAR",
                  attribution="issuer", details=f"revenue={rev:,.0f} net_income={r['NETINCOMEMOSTRECENTFISCALYEAR']} "
                                                f"employees={r['CURRENTEMPLOYEES']} cash={r['CASHEQUIMOSTRECENTFISCALYEAR']}")
    # former names
    for nm in former:
        if nm and nm.lower() != off["legal_name"].lower():
            event(ctx, oid, cik, "entity_name_change_recorded", event_date="", date_basis="date not in index",
                  publication_date="", strength="sec_index", source_id=sid_sub, locator="formerNames",
                  attribution="issuer", details=f"EDGAR former name: {nm}; current name: {sub['name']}")

    # -- document probes (e.g. 10-K text about SAFE conversion) ----------------------------------------
    pr = manual["probes"]
    if len(pr):
        for _, p in pr[pr["offering_id"] == oid].iterrows():
            res = ctx.fetch_doc(oid, p["url"], "document_probe")
            if res is None or not res.ok:
                continue
            sid = ctx.source(p["url"], "sec_filing_document", p["form_type"], p.get("accession", ""),
                             p["publication_date"], res, cik)
            text = re.sub(r"<[^>]+>", " ", res.text())
            text = re.sub(r"&#160;|&nbsp;", " ", text)
            text = re.sub(r"\s+", " ", text)
            hits = []
            for pat in p["patterns"].split("||"):
                for mm in re.finditer(pat, text, re.I):
                    hits.append(text[max(0, mm.start() - 300): mm.end() + 300])
                    break
            ctx.payout.append({"offering_id": oid, "issuer_cik": cik, "evidence_type": p["evidence_type"],
                               "security_scope": p["security_scope"], "date": p["event_date"],
                               "amount": "", "currency": "", "source_id": sid,
                               "locator": f"pattern search: {p['patterns'][:120]}",
                               "excerpt": " ... ".join(hits)[:1500] if hits else "PATTERN NOT FOUND",
                               "is_cash_distribution": False, "notes": p["notes"]})

    # -- manual outcome evidence ---------------------------------------------------------------------------
    mo = manual["outcomes"]
    if len(mo):
        for _, r in mo[mo["offering_id"] == oid].iterrows():
            sid = ctx.source(r["url"], r["source_type"], pub=r["publication_date"], issuer_cik=cik,
                             note=f"retrieved via {r['retrieval_method']} on {r['retrieved_utc']}")
            event(ctx, oid, cik, r["event_type"], event_date=r["event_date"], date_basis=r["event_date_basis"],
                  publication_date=r["publication_date"], strength=r["evidence_strength"], source_id=sid,
                  locator=r["locator"], details=r["details"], attribution=r["attribution_level"])

    # -- user-provided public imports (outcome evidence; historical features only if verified) ----------
    ui = manual.get("user_imports", pd.DataFrame())
    if len(ui):
        for _, r in ui[(ui["offering_id"] == oid) & (ui["validation_errors"] == "")].iterrows():
            sid = ctx.source(r["url_or_document_identity"], "user_provided_capture",
                             pub=r["displayed_publication_or_update_date"], issuer_cik=cik,
                             note=f"captured {r['capture_date_utc']}; sha256 {r['file_sha256']}; "
                                  f"timing verified={r['publication_timing_independently_verified']}")
            event(ctx, oid, cik, f"user_import_{r['evidence_type']}",
                  event_date=r["displayed_publication_or_update_date"],
                  date_basis="displayed date" + ("" if str(r["historical_feature_eligible"]) == "True" else " (not independently verified)"),
                  publication_date=r["displayed_publication_or_update_date"], strength="user_provided_capture",
                  source_id=sid, locator=r["evidence_locator"], details=r["summary"], attribution="offering")

    # -- payout / return status ---------------------------------------------------------------------------
    pay = [p for p in ctx.payout if p["offering_id"] == oid]
    cash = [p for p in pay if p["is_cash_distribution"]]
    if not pay:
        ctx.payout.append({"offering_id": oid, "issuer_cik": cik, "evidence_type": "none_found",
                           "security_scope": "", "date": "", "amount": "", "currency": "", "source_id": "",
                           "locator": "", "excerpt": "", "is_cash_distribution": False,
                           "notes": "no investor distribution/buyback/conversion evidence found in accessible "
                                    "sources within budget (unknown, NOT zero)"})
    ev = [e for e in ctx.events if e["offering_id"] == oid]
    summ = summarize_outcomes(ev, cutoff)
    secs = time.monotonic() - t0
    return {
        "offering_id": oid, "issuer_cik": cik, "issuer_legal_name_at_offering": off["legal_name"],
        "issuer_current_edgar_name": sub.get("name", ""), "issuer_former_names": " | ".join(former),
        "offering_file_number": fnum, "initial_accession": acc0, "initial_filing_date": off["initial_filing_date"],
        "cohort_year": off["cohort_year"], "intermediary_name": off["intermediary_name"],
        "intermediary_cik": off["intermediary_cik"], "intermediary_sec_file_number": off["intermediary_file_number"],
        "security_class": off["security_class"], "security_desc_raw": off["security_desc_raw"],
        "decision_date": dec, "outcome_cutoff": cutoff,
        "deadline_in_effect_at_decision": deadline, "availability_at_decision": avail,
        "availability_evidence": "inferred from filings (deadline, C-W, C-U dated <= decision); no archived campaign page",
        "completion_status": completion, "amount_reported_at_close_usd": amount_reported or "",
        "completion_report_date": completion_date, "completion_text": completion_note,
        "n_amendments_total": int((off_rows["SUBMISSION_TYPE"] == "C/A").sum()),
        "n_amendments_before_decision": int((pre["SUBMISSION_TYPE"] == "C/A").sum()),
        "form_c_pdf_url": pdf_url, "form_c_xml_url": xml_res.url if xml_res else "",
        "xml_offering_amount": xml.get("offeringAmount", ""), "xml_deadline": xml.get("deadlineDate", ""),
        **summ,
        "followup_years_from_decision": round((dt.date.fromisoformat(cutoff) - dt.date.fromisoformat(dec)).days / 365.25, 2),
        "documents_fetched_counted": ctx.doc_count.get(oid, 0),
        "budget_notes": "; ".join(ctx.budget_notes.get(oid, [])),
        "payout_evidence_status": ("cash_distribution_documented" if cash else
                                   (pay[0]["evidence_type"] if pay else "none_found")),
        "return_status": "not_computable",
        "return_reason": ("no documented investor cash flows (contribution dates/amounts per investor and proceeds)"
                          if not cash else "partial cash evidence only"),
        "collection_seconds": round(secs, 1),
    }


def ctr_reason(ctx: Ctx, oid: str, cik_i: str, r: dict) -> str:
    """Read C-TR documents (primary XML + any text/PDF attachment) for a stated reason."""
    base = f"{SEC}/{cik_i}/{r['accession'].replace('-', '')}/"
    idx = ctx.f.get(base + "index.json", "edgar_index")
    if not idx.ok:
        return "index unavailable"
    names = [i["name"] for i in json.loads(idx.text())["directory"]["item"]]
    att = [n for n in names if n.lower().endswith((".txt", ".htm", ".html", ".pdf")) and "index" not in n
           and not n.startswith(r["accession"])]
    if not att:
        return "no attachment; Form C-TR XML has no reason field (reason not stated in filing)"
    res = ctx.fetch_doc(oid, base + att[0], "c_tr_attachment")
    if res is None or not res.ok:
        return f"attachment {att[0]} not fetched (budget)"
    if att[0].lower().endswith(".pdf"):
        import pdfplumber
        with pdfplumber.open(res.path) as pdf:
            txt = " ".join((pg.extract_text() or "") for pg in pdf.pages[:5])
        if not txt.strip():
            return f"PDF attachment {att[0]}: no extractable text"
    else:
        txt = res.text()
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    m = (re.search(r"[^.]{0,200}(?:227\.)?202\s*\(b\)\s*\(\d\)[^.]{0,200}", txt, re.I)
         or re.search(r"terminat[^.]{0,300}", txt, re.I))
    return (m.group(0) if m else txt[:300]).strip()


def cmd_collect(cfg: Config, args) -> int:
    f = Fetcher(cfg)
    sample = pd.read_csv(cfg.path("sample_dir") / "frozen_sample.csv", dtype=str, keep_default_na=False)
    fr = pd.read_csv(cfg.path("frame_dir") / "sampling_frame.csv", dtype=str, keep_default_na=False)
    sample = sample.merge(fr[["offering_id", "n_initial_form_c_any_platform"]], on="offering_id", how="left",
                          suffixes=("", "_fr"))
    if args.only == "pilot":
        sel = sample[sample["is_pilot"] == "True"]
    elif args.only in ("", "all"):
        sel = sample
    else:
        sel = sample[sample["offering_id"].isin(args.only.split(","))]
    tabs = dera.load_tables(cfg, f)
    m = tabs["FORM_C_SUBMISSION"].merge(tabs["FORM_C_ISSUER_INFORMATION"].drop(columns=["SOURCE_QUARTER", "SOURCE_URL"]),
                                        on="ACCESSION_NUMBER", how="left") \
        .merge(tabs["FORM_C_DISCLOSURE"].drop(columns=["SOURCE_QUARTER", "SOURCE_URL"]), on="ACCESSION_NUMBER", how="left")
    m = m.fillna("")
    manual = {"facts": load_manual(cfg, "pilot_manual_facts.csv"),
              "outcomes": load_manual(cfg, "outcome_evidence_manual.csv"),
              "probes": load_manual(cfg, "document_probes.csv")}
    uip = cfg.path("tables_dir") / "user_imports_public.csv"
    manual["user_imports"] = pd.read_csv(uip, dtype=str, keep_default_na=False) if uip.exists() else pd.DataFrame()
    ctx = Ctx(cfg, f)
    offs = []
    started = utcnow_iso()
    for _, off in sel.sort_values("collection_order", key=lambda s: s.astype(int)).iterrows():
        try:
            offs.append(collect_offering(ctx, off, {"m": m}, manual))
            print(f"collected {off['offering_id']} {off['legal_name']}")
        except BudgetExhausted as exc:
            print(f"BUDGET EXHAUSTED at {off['offering_id']}: {exc}")
            break
    td = cfg.path("tables_dir")
    suffix = "_pilot" if args.only == "pilot" else ""
    pd.DataFrame(offs).to_csv(td / f"offerings{suffix}.csv", index=False)
    pd.DataFrame(ctx.facts).to_csv(td / f"facts{suffix}.csv", index=False)
    pd.DataFrame(list(ctx.sources.values())).to_csv(td / f"sources{suffix}.csv", index=False)
    pd.DataFrame(ctx.events).to_csv(td / f"outcome_events{suffix}.csv", index=False)
    pd.DataFrame(ctx.payout).to_csv(td / f"payout_evidence{suffix}.csv", index=False)
    pd.DataFrame(ctx.filings).to_csv(td / f"issuer_filings{suffix}.csv", index=False)
    # cash_flows: only documented investor cash flows; none fabricated
    pd.DataFrame(columns=["offering_id", "date", "amount", "kind", "security_class", "evidence_source_id",
                          "notes"]).to_csv(td / f"cash_flows{suffix}.csv", index=False)
    with open(td / f"collect_run{suffix}.json", "w") as fh:
        json.dump({"started_utc": started, "finished_utc": utcnow_iso(), "network_requests": f.network_requests,
                   "offerings": len(offs)}, fh, indent=2)
    print(f"offerings={len(offs)} facts={len(ctx.facts)} events={len(ctx.events)} "
          f"sources={len(ctx.sources)} network_requests={f.network_requests}")
    return 0
