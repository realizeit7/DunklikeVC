"""Manual evidence imports, weekly/monthly reports and public-only CSV exports."""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from .core import Ctx, iso, norm_utc, parse_utc
from .journal import brier, build_queue, forecast_status, unreviewed

IMPORT_TYPES = {"campaign_page", "founder_qa", "company_update", "contract_document", "investor_notice", "other"}
PRIVATE_BY_DEFAULT = {"investor_notice"}


# ---- manual imports ---------------------------------------------------------------------------------
SECRET_FILE_SUFFIXES = {".har", ".cookies", ".cookie", ".sqlite", ".db", ".json"}
SECRET_MARKERS = ["netscape http cookie file", "set-cookie:", "\"cookies\":", "authorization: bearer", "sessionid=",
                  "_session_id=", "remember_user_token", "access_token", "refresh_token"]


def screen_import_file(path: Path) -> dict:
    """Checks run on a user-captured file BEFORE it is stored or extracted.

    * Cookie jars, HAR files, browser databases and anything carrying session tokens are refused: cookies, credentials
      and tokens are never evidence.
    * HTML/text captures are classified with the access classifier: challenge, login, error and empty pages are refused.
    * PDFs are classified on their text layer (pdftotext) when available.
    """
    from .access import classify_page
    data = path.read_bytes()
    low = data[:2_000_000].decode("utf-8", errors="ignore").lower()
    if path.suffix.lower() in SECRET_FILE_SUFFIXES or any(m in low for m in SECRET_MARKERS):
        return {"ok": False, "reason": "file looks like a cookie jar / HAR / token store; cookies, credentials and tokens are not evidence"}
    text = None
    if path.suffix.lower() in (".html", ".htm", ".txt", ".mhtml"):
        text = data.decode("utf-8", errors="ignore")
    elif path.suffix.lower() == ".pdf":
        import subprocess
        try:
            text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, timeout=120).stdout
        except (OSError, subprocess.SubprocessError):
            text = None
    if text is None or (path.suffix.lower() == ".pdf" and len(text.split()) < 20):
        return {"ok": True, "reason": "not classified (binary/image capture or no text layer); review manually",
                "classified": False}
    cl = classify_page(200, "", "", text if path.suffix.lower() != ".pdf" else f"<html><body>{text}</body></html>")
    if cl["result"] != "public_content":
        return {"ok": False, "reason": f"capture is a {cl['result']} page (markers {cl['markers']}); nothing extracted",
                "classified": True}
    return {"ok": True, "reason": "classified as content", "classified": True, "markers": cl["markers"]}


def import_evidence(ctx: Ctx, csv_path: Path) -> dict:
    """Import user-captured evidence listed in a CSV (templates/evidence_import_template.csv).

    The system observation time is the import time, never the claimed publication or capture date, so a late
    document cannot enter an earlier decision or evidence pack. Three dates stay separate: the visible publication
    date (claimed_publication_date), the user's capture time (captured_utc) and the import time (observed).
    Private items (investor-only material, or anything captured while logged in) are stored outside git and excluded
    from exports. Challenge/login/error pages and cookie/token files are refused before anything is stored.
    """
    stats = {"imported": 0, "private": 0, "rejected": 0, "rows": []}
    for row in csv.DictReader(open(csv_path)):
        src = (csv_path.parent / row["file"]).resolve() if row.get("file") else None
        reason = None
        if row["source_type"] not in IMPORT_TYPES or (src and not src.exists()) or not row.get("offering_id"):
            reason = "invalid row (source_type, file or offering_id)"
        elif src:
            sc = screen_import_file(src)
            if not sc["ok"]:
                reason = sc["reason"]
        if reason:
            stats["rejected"] += 1
            stats["rows"].append({"file": row.get("file"), "status": "rejected", "reason": reason})
            ctx.gap("parse_failure", row.get("url", ""), f"import row rejected: {reason}; file={row.get('file')}")
            continue
        logged_in = (row.get("captured_while_logged_in") or "").strip().lower() in ("yes", "y", "true", "1")
        vis = ("private" if row["source_type"] in PRIVATE_BY_DEFAULT or row.get("visibility") == "private" or logged_in
               else "public")
        data = src.read_bytes() if src else None
        blob = None
        if data is not None and vis == "private":
            import hashlib
            sha = hashlib.sha256(data).hexdigest()
            d = ctx.root / ctx.cfg.raw["paths"]["private_dir"] / "blobs"
            d.mkdir(parents=True, exist_ok=True)
            (d / sha).write_bytes(data)
            blob = (sha, str((d / sha).relative_to(ctx.root)))
        o = ctx.con.execute("SELECT issuer_id FROM offerings WHERE offering_id=?", (row["offering_id"],)).fetchone()
        ctx.record_document(url=row.get("url") or f"user-import:{src.name if src else 'none'}", source_type="user_import",
                            offering_id=row["offering_id"], issuer_cik=o["issuer_id"] if o else "", data=data,
                            visibility=vis, claimed_publication_date=row.get("claimed_publication_date", ""),
                            description=f"{row['source_type']}: {row.get('description', '')} "
                                        f"(user capture time {row.get('captured_utc', 'not given')}; "
                                        f"{'captured while logged in' if logged_in else 'public view'})",
                            extraction_method="user_import", blob_override=blob)
        stats["imported"] += 1
        stats["private"] += vis == "private"
        stats["rows"].append({"file": row.get("file"), "status": "imported", "visibility": vis})
    ctx.con.commit()
    return stats


# ---- reports --------------------------------------------------------------------------------------------
def _md(rows: list[dict], cols: list[str]) -> list[str]:
    if not rows:
        return ["_none_"]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "") if r.get(c) is not None else "").replace("|", "/")[:120] for c in cols) + " |")
    return out


def weekly_report(ctx: Ctx, end_utc: str | None = None) -> Path:
    end = parse_utc(norm_utc(end_utc) if end_utc else ctx.now())
    start = end - dt.timedelta(days=7)
    s, e = iso(start), iso(end)
    week = f"{end.isocalendar().year}-W{end.isocalendar().week:02d}"
    clock = {r["key"]: r["value"] for r in ctx.con.execute("SELECT key, value FROM pilot_clock")}
    q = lambda sql, *a: [dict(r) for r in ctx.con.execute(sql, a)]  # noqa: E731
    newq = ("SELECT offering_id, legal_name, cohort, security_class, initial_filing_date, first_observed_utc FROM offerings "
            "WHERE eligibility='eligible' AND cohort=? AND first_observed_utc > ? AND first_observed_utc <= ? ORDER BY first_observed_utc")
    new_inc, new_wl = q(newq, "inception", s, e), q(newq, "initial_watchlist", s, e)
    pre = q("SELECT COUNT(*) n FROM offerings WHERE cohort='pre_start_other' AND first_observed_utc > ? AND first_observed_utc <= ?", s, e)[0]["n"]
    excl = q("SELECT COUNT(*) n FROM offerings WHERE eligibility='excluded' AND first_observed_utc > ? AND first_observed_utc <= ?", s, e)[0]["n"]
    changes = q("SELECT e.offering_id, o.legal_name, e.event_type, e.event_date, e.interpretation FROM events e JOIN offerings o "
                "USING(offering_id) WHERE e.observed_utc > ? AND e.observed_utc <= ? ORDER BY e.event_date", s, e)
    queue = build_queue(ctx, week)
    qrows = [dict(ctx.con.execute("SELECT offering_id, legal_name, cohort, initial_filing_date, availability_status FROM offerings "
                                  "WHERE offering_id=?", (oid,)).fetchone()) for oid in queue]
    due = q("SELECT offering_id, legal_name, cohort, availability_status, closing_status, next_check_due_utc, last_check_ok "
            "FROM offerings WHERE eligibility='eligible' AND cohort IN ('inception','initial_watchlist') AND next_check_due_utc <= ? "
            "ORDER BY next_check_due_utc", iso(end + dt.timedelta(days=7)))
    gaps = q("SELECT kind, COUNT(*) n, MIN(url) example FROM gaps WHERE utc > ? AND utc <= ? GROUP BY kind", s, e)
    missing = q("SELECT f.field, COUNT(DISTINCT f.offering_id) n FROM facts f WHERE f.verification_status='missing' "
                "GROUP BY f.field ORDER BY n DESC LIMIT 10")
    effort = q("SELECT activity, SUM(minutes) minutes FROM effort_log WHERE activity_date > ? AND activity_date <= ? GROUP BY activity",
               s[:10], e[:10])
    runs = q("SELECT command, COUNT(*) n, SUM(network_requests) requests, SUM(cache_hits) cache_hits, SUM(errors) errors FROM runs "
             "WHERE started_utc > ? AND started_utc <= ? GROUP BY command", s, e)
    total_min = sum(r["minutes"] or 0 for r in effort)
    L = [f"# Weekly report {week} ({s[:10]} → {e[:10]} UTC)", "",
         f"Pilot: start {clock.get('pilot_start_utc', 'not started')} ({clock.get('pilot_start_local_date', '')} New York), "
         f"end {clock.get('pilot_end_utc', '')}. Collection only happens when the commands actually run; runs this week are listed below.",
         "", "## Newly discovered eligible offerings — inception cohort (primary)", "",
         *_md(new_inc, ["offering_id", "legal_name", "security_class", "initial_filing_date", "first_observed_utc"]),
         "", "## Newly added to the initial watchlist (startup only; left-truncated; never pooled with inception)", "",
         *_md(new_wl, ["offering_id", "legal_name", "security_class", "initial_filing_date", "first_observed_utc"]),
         "", f"Ledger only (not tracked): {excl} excluded Republic offerings and {pre} pre-start offerings outside the watchlist "
             "were first observed this week.",
         "", "## Document and status changes (filings observed this week)", "",
         *_md(changes, ["offering_id", "legal_name", "event_type", "event_date", "interpretation"]),
         "", f"## Review queue ({ctx.cfg['schedule']['review_queue_rule']}, {len(queue)} of {len(unreviewed(ctx))} unreviewed)", "",
         "Reviewing a deal is not selecting it. Record any discretionary pick with `queue --pick OFFERING_ID`.", "",
         *_md(qrows, ["offering_id", "legal_name", "cohort", "initial_filing_date", "availability_status"]),
         "", "## Follow-ups due in the next 7 days (same rule for selected, passed, deferred and unreviewed)", "",
         *_md(due, ["offering_id", "legal_name", "cohort", "availability_status", "closing_status", "next_check_due_utc", "last_check_ok"]),
         "", "## Missing evidence and access problems", "",
         "Processing failures and access blocks (not the same as nondisclosure):", "", *_md(gaps, ["kind", "n", "example"]),
         "", "Most frequently absent structured Form C fields (nondisclosure or blank in the filing):", "",
         *_md(missing, ["field", "n"]),
         "", "## Collection runs this week", "", *_md(runs, ["command", "n", "requests", "cache_hits", "errors"]),
         "", "## User effort recorded this week", "", *_md(effort, ["activity", "minutes"]),
         f"", f"Total: {total_min:.0f} minutes ({total_min / 60:.1f} h of the 6 h weekly budget)."
         + (" No effort entries yet — record time with `log-effort`." if not effort else ""), ""]
    out = ctx.root / ctx.cfg.raw["paths"]["reports_dir"] / f"weekly_{week}.md"
    out.write_text("\n".join(L))
    return out


def monthly_report(ctx: Ctx, end_utc: str | None = None) -> Path:
    end = parse_utc(norm_utc(end_utc) if end_utc else ctx.now())
    start, e = iso(end - dt.timedelta(days=30)), iso(end)
    q = lambda sql, *a: [dict(r) for r in ctx.con.execute(sql, a)]  # noqa: E731
    by_cohort = q("SELECT cohort, eligibility, COUNT(*) n FROM offerings GROUP BY cohort, eligibility ORDER BY cohort")
    delay = q("SELECT cohort, COUNT(*) n, ROUND(AVG((julianday(first_observed_utc) - julianday(initial_acceptance_utc)) * 24), 1) "
              "mean_hours, ROUND(MAX((julianday(first_observed_utc) - julianday(initial_acceptance_utc)) * 24), 1) max_hours "
              "FROM offerings WHERE eligibility='eligible' AND initial_acceptance_utc != '' GROUP BY cohort")
    tracked = "eligibility='eligible' AND cohort IN ('inception','initial_watchlist')"
    snap = q(f"SELECT cohort, COUNT(*) n, SUM(captured_utc IS NOT NULL) captured FROM offerings WHERE {tracked} GROUP BY cohort")
    req_fields = ["revenue", "net_income", "cash_and_equivalents", "security_description", "price_per_security",
                  "target_offering_amount", "offering_deadline"]
    req = []
    for fld in req_fields:
        r = ctx.con.execute(f"""SELECT COUNT(DISTINCT o.offering_id) n,
            COUNT(DISTINCT CASE WHEN f.value IS NOT NULL THEN o.offering_id END) present
            FROM offerings o LEFT JOIN facts f ON f.offering_id=o.offering_id AND f.field=?
            AND (f.financial_period IN ('', 'most_recent_fiscal_year')) WHERE {tracked.replace('eligibility', 'o.eligibility').replace('cohort', 'o.cohort')}
            AND o.captured_utc IS NOT NULL""", (fld,)).fetchone()
        req.append({"field": fld, "captured_offerings": r["n"], "present": r["present"]})
    contract = q("SELECT value, COUNT(*) n FROM facts WHERE field='contract_coverage' GROUP BY value")
    follow = q(f"SELECT cohort, availability_status, closing_status, SUM(last_check_ok=1) last_ok, SUM(last_check_ok=0) last_failed, "
               f"COUNT(*) n FROM offerings WHERE {tracked} GROUP BY cohort, availability_status, closing_status")
    rev = q("SELECT d.status, d.user_confirmed, COUNT(*) n FROM decisions d GROUP BY d.status, d.user_confirmed")
    fs = forecast_status(ctx)
    fstate: dict = {}
    for r in fs:
        fstate[r["state"]] = fstate.get(r["state"], 0) + 1
    b = brier(fs)
    costs = q("SELECT command, COUNT(*) runs, SUM(network_requests) requests, SUM(cache_hits) cache_hits, SUM(errors) errors, "
              "ROUND(SUM((julianday(finished_utc) - julianday(started_utc)) * 86400)) seconds FROM runs WHERE started_utc > ? "
              "GROUP BY command", start)
    eff = q("SELECT ROUND(SUM(minutes)) minutes FROM effort_log WHERE activity_date > ?", start[:10])
    gaps = q("SELECT kind, COUNT(*) n FROM gaps WHERE utc > ? GROUP BY kind", start)
    L = [f"# Monthly coverage report ({start[:10]} → {e[:10]} UTC)", "",
         "Inception and initial-watchlist cohorts are reported separately and never pooled.", "",
         "## Offerings discovered, by cohort and eligibility", "", *_md(by_cohort, ["cohort", "eligibility", "n"]),
         "", "## Delay from EDGAR acceptance to first observation (hours)", "", *_md(delay, ["cohort", "n", "mean_hours", "max_hours"]),
         "", "Only the inception cohort measures timeliness; watchlist and pre-start delays reflect the pilot start (left truncation).",
         "", "## Snapshot coverage", "", *_md(snap, ["cohort", "n", "captured"]),
         "", "## Required-field coverage (captured offerings; missing = absent in the filing, not zero)", "",
         *_md(req, ["field", "captured_offerings", "present"]),
         "", "## Contract vs summary-only coverage", "", *_md(contract, ["value", "n"]),
         "", "## Follow-up status", "", *_md(follow, ["cohort", "availability_status", "closing_status", "n", "last_ok", "last_failed"]),
         "", "## Reviews and decisions", "", *_md(rev, ["status", "user_confirmed", "n"]),
         f"", f"Unreviewed tracked offerings: {len(unreviewed(ctx))}.",
         "", "## Forecasts", "", *_md([{"state": k, "n": v} for k, v in fstate.items()], ["state", "n"]),
         f"", f"Brier score: {b['brier'] if b['brier'] is not None else 'n/a'} on {b['n_resolved']} resolved of {b['n_original']} "
         f"original forecasts ({b['n_unresolved']} unresolved/pending). {b['note']}.",
         "", "## Collection cost", "", *_md(costs, ["command", "runs", "requests", "cache_hits", "errors", "seconds"]),
         f"", f"User review time recorded: {eff[0]['minutes'] or 0} minutes.",
         "", "## Processing failures and access gaps (reported separately from nondisclosure)", "", *_md(gaps, ["kind", "n"]), ""]
    out = ctx.root / ctx.cfg.raw["paths"]["reports_dir"] / f"monthly_{e[:10]}.md"
    out.write_text("\n".join(L))
    return out


# ---- exports -----------------------------------------------------------------------------------------
EXPORT_TABLES = ["runs", "gaps", "index_days", "discovery_ledger", "offerings", "offering_status_log", "documents", "facts",
                 "decisions", "decision_evidence", "predictions", "prediction_resolutions", "events", "review_queue_log",
                 "effort_log", "pilot_clock",
                 # v2 research tables (public-safe). Approvals, ledger, issuer groups and acknowledgments are PERSONAL
                 # and are never exported.
                 "evidence_packs", "analyst_versions", "analysis_runs", "analysis_claims", "analysis_gates", "prediction_meta",
                 "citation_checks",
                 # v2.1 tables (public-safe: attempt metadata and hashes only, no captured content or cookies)
                 "access_attempts", "source_checks", "assessments", "criterion_results", "calculations", "support_checks",
                 "forecast_definitions", "forecast_lineage", "stage_usage",
                 # v2.2 (policy_activations is PERSONAL, like policy_acknowledgments, and is never exported)
                 "rule_findings", "assessments_v3", "thesis_answers"]


NULL = "\\N"   # explicit NULL marker: a missing value must not round-trip as an empty string or 0


def export_public(ctx: Ctx) -> dict:
    """Write CSVs of every table, excluding private documents and anything derived from them."""
    d = ctx.root / ctx.cfg.raw["paths"]["exports_dir"]
    d.mkdir(parents=True, exist_ok=True)
    private = {r[0] for r in ctx.con.execute("SELECT document_id FROM documents WHERE visibility='private'")}
    counts = {}
    for t in EXPORT_TABLES:
        cur = ctx.con.execute(f"SELECT * FROM {t}")
        cols = [c[0] for c in cur.description]
        rows = [r for r in cur.fetchall()
                if not (t == "documents" and r["visibility"] == "private")
                and not (t in ("facts",) and r["document_id"] in private)
                and not (t == "decision_evidence" and r["document_id"] in private)
                and not (t == "events" and r["source_document_id"] in private)]
        with open(d / f"{t}.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(cols)
            w.writerows([tuple(NULL if v is None else v for v in r) for r in rows])
        counts[t] = len(rows)
    return counts


def restore_from_exports(ctx: Ctx) -> dict:
    """Rebuild an EMPTY database from the committed public CSV exports (e.g. on a new machine).

    Snapshot bytes are not in git: restored document rows keep their sha256 and URL, and missing blobs are reported.
    Private rows were never exported and cannot be restored from git.
    """
    if ctx.con.execute("SELECT COUNT(*) FROM documents").fetchone()[0] or ctx.con.execute("SELECT COUNT(*) FROM offerings").fetchone()[0]:
        raise RuntimeError("database is not empty; restore only into a fresh database")
    d = ctx.root / ctx.cfg.raw["paths"]["exports_dir"]
    counts = {}
    for t in EXPORT_TABLES:
        f = d / f"{t}.csv"
        if not f.exists():
            continue
        rows = list(csv.DictReader(open(f)))
        if t == "runs":
            rows = [r for r in rows if r["run_id"] != ctx.run_id]
        if t == "pilot_clock":
            if ctx.con.execute("SELECT COUNT(*) FROM pilot_clock").fetchone()[0]:
                continue   # already restored from pilot_clock.json
        for r in rows:
            cols = list(r)
            vals = [None if v == NULL else v for v in r.values()]
            ctx.con.execute(f"INSERT OR IGNORE INTO {t}({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
        counts[t] = len(rows)
    missing = [r[0] for r in ctx.con.execute("SELECT blob_path FROM documents WHERE blob_path IS NOT NULL")
               if not (ctx.root / r[0]).exists()]
    ctx.con.commit()
    counts["documents_with_missing_blob"] = len(missing)
    return counts
