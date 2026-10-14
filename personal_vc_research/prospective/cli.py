"""CLI for the prospective pilot. Run from personal_vc_research/:  python -m prospective <command> [options]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import collect, discover, journal, outputs
from .core import Ctx, get_clock

DEFAULT_CONFIG = str(Path(__file__).parent / "config.yaml")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m prospective")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the database and show the pilot clock (does not start it)")
    sub.add_parser("discover", help="scan EDGAR daily indexes; the first successful run starts the pilot clock")
    c = sub.add_parser("capture", help="full snapshot of newly discovered eligible offerings (bounded batch)")
    c.add_argument("--limit", type=int)
    c.add_argument("--offering", action="append")
    sub.add_parser("followup", help="change/follow-up checks for offerings that are due (equal rules for all decisions)")
    sub.add_parser("run", help="daily job: discover + capture + followup + export")
    i = sub.add_parser("import-evidence", help="import user-captured evidence from a CSV (see templates/)")
    i.add_argument("csv")
    k = sub.add_parser("packet", help="generate a review packet with an evidence cutoff")
    k.add_argument("offering")
    k.add_argument("--retrospective-as-of", help="label as a retrospective reconstruction using evidence observed by this time")
    d = sub.add_parser("decide", help="record a decision (select/pass/defer need --user-confirmed)")
    d.add_argument("offering")
    d.add_argument("--status", choices=["select", "pass", "defer", "unreviewed"], required=True)
    d.add_argument("--analyst", required=True)
    d.add_argument("--user-confirmed", action="store_true")
    d.add_argument("--reasons", default="")
    d.add_argument("--counterarguments", default="")
    d.add_argument("--unresolved", default="")
    d.add_argument("--draft-recommendation", default="")
    d.add_argument("--paper-amount-usd", type=float)
    d.add_argument("--packet")
    d.add_argument("--retrospective-as-of")
    dc = sub.add_parser("decide-csv", help="record decisions from templates/decision_template.csv")
    dc.add_argument("csv")
    f = sub.add_parser("forecast-add")
    f.add_argument("offering")
    f.add_argument("--event", required=True)
    f.add_argument("--kind", choices=["business", "disclosure"], required=True)
    f.add_argument("--horizon-months", type=int, choices=[6, 12], required=True)
    f.add_argument("--probability", type=float, required=True)
    f.add_argument("--resolution-rule", required=True)
    f.add_argument("--reporting-lag-days", type=int, required=True)
    f.add_argument("--missing-evidence", required=True, help="treatment of missing evidence (never 'counts as false')")
    f.add_argument("--permitted-evidence", default="")
    f.add_argument("--forecaster", required=True)
    f.add_argument("--decision-id", type=int)
    fr = sub.add_parser("forecast-revise")
    fr.add_argument("prediction_id", type=int)
    fr.add_argument("--probability", type=float, required=True)
    fr.add_argument("--forecaster", required=True)
    fs = sub.add_parser("forecast-resolve")
    fs.add_argument("prediction_id", type=int)
    fs.add_argument("--outcome", choices=["true", "false", "unresolved_unknown"], required=True)
    fs.add_argument("--evidence", default="")
    fs.add_argument("--adjudicator", required=True)
    e = sub.add_parser("log-effort")
    e.add_argument("--minutes", type=float, required=True)
    e.add_argument("--activity", required=True, choices=["weekly_review", "packet_review", "import", "forecasting", "admin", "other"])
    e.add_argument("--date", required=True)
    e.add_argument("--note", default="")
    qq = sub.add_parser("queue", help="show this week's review queue; --pick records a discretionary review")
    qq.add_argument("--week", required=True, help="ISO week, e.g. 2026-W42")
    qq.add_argument("--pick", action="append")
    sub.add_parser("report-weekly")
    sub.add_parser("report-monthly")
    sub.add_parser("export")
    sub.add_parser("restore", help="rebuild an empty database from the committed public CSV exports")
    sub.add_parser("status")
    a = p.parse_args(argv)

    offline = a.cmd not in ("discover", "capture", "followup", "run")
    ctx = Ctx(a.config, a.cmd, offline=offline)
    try:
        res = dispatch(ctx, a)
        ctx.finish("ok", json.dumps(res, default=str)[:2000])
        print(json.dumps(res, indent=2, default=str))
        return 0
    except Exception as exc:  # noqa: BLE001 - every failure is recorded on the run
        ctx.gap("run_failure", "", repr(exc))
        ctx.finish("failed", repr(exc))
        print(f"FAILED: {exc!r}", file=sys.stderr)
        return 1


def dispatch(ctx: Ctx, a) -> dict:
    if a.cmd == "init":
        return {"db": str(ctx.cfg.path("db")), "pilot_clock": get_clock(ctx) or "not started (starts at first successful discover)"}
    if a.cmd == "discover":
        return discover.cmd_discover(ctx)
    if a.cmd == "capture":
        return collect.cmd_capture(ctx, a.limit, a.offering)
    if a.cmd == "followup":
        return collect.cmd_followup(ctx)
    if a.cmd == "run":
        out = {"discover": discover.cmd_discover(ctx), "capture": collect.cmd_capture(ctx),
               "followup": collect.cmd_followup(ctx)}
        out["export"] = outputs.export_public(ctx)
        return out
    if a.cmd == "import-evidence":
        return outputs.import_evidence(ctx, Path(a.csv))
    if a.cmd == "packet":
        path, sha = journal.build_packet(ctx, a.offering, a.retrospective_as_of,
                                         "retrospective_reconstruction" if a.retrospective_as_of else "prospective")
        return {"packet": str(path), "sha256": sha}
    if a.cmd == "decide":
        did = journal.record_decision(ctx, a.offering, a.status, a.analyst, a.user_confirmed, a.reasons, a.counterarguments,
                                      a.unresolved, a.draft_recommendation, a.paper_amount_usd,
                                      Path(a.packet).resolve() if a.packet else None, a.retrospective_as_of)
        return {"decision_id": did}
    if a.cmd == "decide-csv":
        import csv
        ids = []
        for r in csv.DictReader(open(a.csv)):
            ids.append(journal.record_decision(
                ctx, r["offering_id"], r["status"], r["analyst"], r["user_confirmed"].strip().lower() in ("1", "true", "yes"),
                r.get("reasons", ""), r.get("counterarguments", ""), r.get("unresolved_questions", ""),
                r.get("draft_recommendation", ""), float(r["paper_amount_usd"]) if r.get("paper_amount_usd") else None,
                Path(r["packet"]).resolve() if r.get("packet") else None))
        return {"decision_ids": ids}
    if a.cmd == "forecast-add":
        return {"prediction_id": journal.add_forecast(ctx, a.offering, a.event, a.kind, a.horizon_months, a.probability,
                                                      a.resolution_rule, a.reporting_lag_days, a.missing_evidence,
                                                      a.forecaster, a.permitted_evidence, a.decision_id)}
    if a.cmd == "forecast-revise":
        orig = ctx.con.execute("SELECT * FROM predictions WHERE prediction_id=?", (a.prediction_id,)).fetchone()
        return {"prediction_id": journal.add_forecast(ctx, orig["offering_id"], orig["target_event"], orig["event_kind"],
                                                      orig["horizon_months"], a.probability, orig["resolution_rule"],
                                                      orig["reporting_lag_days"], orig["missing_evidence_treatment"],
                                                      a.forecaster, orig["permitted_evidence"], orig["decision_id"],
                                                      revises=a.prediction_id)}
    if a.cmd == "forecast-resolve":
        return {"resolution_id": journal.resolve_forecast(ctx, a.prediction_id, a.outcome, a.evidence, a.adjudicator)}
    if a.cmd == "log-effort":
        journal.log_effort(ctx, a.minutes, a.activity, a.date, a.note)
        return {"logged_minutes": a.minutes}
    if a.cmd == "queue":
        return {"week": a.week, "queue": journal.build_queue(ctx, a.week, a.pick)}
    if a.cmd == "report-weekly":
        return {"report": str(outputs.weekly_report(ctx))}
    if a.cmd == "report-monthly":
        return {"report": str(outputs.monthly_report(ctx))}
    if a.cmd == "restore":
        get_clock(ctx)
        return outputs.restore_from_exports(ctx)
    if a.cmd == "export":
        return outputs.export_public(ctx)
    if a.cmd == "status":
        rows = ctx.con.execute("SELECT cohort, eligibility, COUNT(*) n FROM offerings GROUP BY cohort, eligibility").fetchall()
        return {"pilot_clock": get_clock(ctx), "offerings": [dict(r) for r in rows],
                "forecasts": journal.brier(journal.forecast_status(ctx))}
    raise ValueError(a.cmd)
