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
def import_evidence(ctx: Ctx, csv_path: Path) -> dict:
    """Import user-captured evidence listed in a CSV (templates/evidence_import_template.csv).

    The system observation time is the import time, never the claimed publication or capture date, so a late
    document cannot enter an earlier decision. Private items are stored outside git and excluded from exports.
    """
    stats = {"imported": 0, "private": 0, "rejected": 0}
    for row in csv.DictReader(open(csv_path)):
        src = (csv_path.parent / row["file"]).resolve() if row.get("file") else None
        if row["source_type"] not in IMPORT_TYPES or (src and not src.exists()) or not row.get("offering_id"):
            stats["rejected"] += 1
            ctx.gap("parse_failure", row.get("url", ""), f"import row rejected: {row}")
            continue
        vis = "private" if row["source_type"] in PRIVATE_BY_DEFAULT or row.get("visibility") == "private" else "public"
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
                                        f"(user capture time {row.get('captured_utc', 'not given')})",
                            extraction_method="user_import", blob_override=blob)
        stats["imported"] += 1
        stats["private"] += vis == "private"
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
                 "effort_log", "pilot_clock"]


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
            w.writerows([tuple(r) for r in rows])
        counts[t] = len(rows)
    return counts
