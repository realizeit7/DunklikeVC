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
    # ---- v2: policies, analysis, briefs -------------------------------------------------------------------
    sub.add_parser("migrations", help="show applied schema migrations and their backups")
    ak = sub.add_parser("ack-policy", help="acknowledge the screening or budget policy (required before live approvals)")
    ak.add_argument("kind", choices=["screening", "budget"])
    ak.add_argument("--statement", required=True)
    ci = sub.add_parser("confirm-issuer", help="user-confirmed issuer aggregation (rounds/brands/SPVs share one issuer limit)")
    ci.add_argument("member_cik")
    ci.add_argument("--issuer-key", required=True)
    ci.add_argument("--basis", required=True)
    pk = sub.add_parser("pack", help="freeze an evidence pack for an offering")
    pk.add_argument("offering")
    pk.add_argument("--cutoff")
    rv = sub.add_parser("analyst-register", help="register an analyst version BEFORE using it")
    rv.add_argument("version_id")
    rv.add_argument("--role", choices=["baseline", "challenger"], required=True)
    rv.add_argument("--description", required=True)
    rv.add_argument("--model")
    rv.add_argument("--dev-offering", action="append", default=[])
    rv.add_argument("--prompt-version", default="analyst_prompt_v1")
    rv.add_argument("--repair-rounds", type=int, default=0)
    an = sub.add_parser("analyze", help="run the 4-stage analysis on a frozen pack")
    an.add_argument("offering")
    an.add_argument("--version", required=True)
    an.add_argument("--pack")
    an.add_argument("--adapter", choices=["claude_cli", "files"], default="claude_cli")
    an.add_argument("--dir", help="stage-output directory for --adapter files")
    an.add_argument("--model")
    an.add_argument("--max-budget-usd", type=float, default=5.0)
    ex = sub.add_parser("analysis-export", help="manual route: write prompt, schemas and payloads for a pack")
    ex.add_argument("pack_id")
    ex.add_argument("--out", required=True)
    rvd = sub.add_parser("revalidate", help="re-validate an earlier run's stored outputs under the current schema (new run, no LLM call)")
    rvd.add_argument("analysis_id", type=int)
    br = sub.add_parser("brief", help="Korean review brief for an analysis")
    br.add_argument("analysis_id", type=int)
    # ---- v2.1 ---------------------------------------------------------------------------------------------------
    r2 = sub.add_parser("analyst-register-v2", help="register an analyst-v2 pipeline version BEFORE using it")
    r2.add_argument("version_id")
    r2.add_argument("--description", required=True)
    r2.add_argument("--dev-offering", action="append", default=[])
    r2.add_argument("--repair-rounds", type=int, default=2, help="cap on targeted repair requests per stage")
    r2.add_argument("--model")
    a2 = sub.add_parser("analyze-v2", help="v2 pipeline (A-F, criteria, support check, computed assessment) on a frozen pack")
    a2.add_argument("offering")
    a2.add_argument("--version", required=True)
    a2.add_argument("--pack", required=True)
    a2.add_argument("--model")
    a2.add_argument("--max-budget-usd", type=float, default=5.0)
    a2.add_argument("--note", default="")
    b2 = sub.add_parser("brief-v2", help="Korean brief, v2.1 layout (top summary + appendix)")
    b2.add_argument("analysis_id", type=int)
    ap2 = sub.add_parser("access-probe", help="ONE ordinary access attempt (logged); refused during a block cooldown")
    ap2.add_argument("url")
    ap2.add_argument("--method", choices=["http", "browser"], default="http")
    tg = sub.add_parser("target-ocr", help="bounded OCR page targeting of a large/image PDF, then a NEW pack")
    tg.add_argument("document_id", type=int)
    tg.add_argument("--offering", required=True)
    tg.add_argument("--cutoff", required=True, help="evidence cutoff for the new pack (documents observed by then)")
    tg.add_argument("--cap", type=int, default=60)
    fl = sub.add_parser("forecast-flag", help="record a separate lineage note on a forecast (the original is never changed)")
    fl.add_argument("prediction_id", type=int)
    fl.add_argument("--relation", choices=["redefined_by", "split_into", "flagged_compound", "superseded_definition"], required=True)
    fl.add_argument("--reason", required=True)
    fl.add_argument("--successor", type=int)
    hs = sub.add_parser("support-check-manual", help="record a human spot check of one claim against the source page")
    hs.add_argument("analysis_id", type=int)
    hs.add_argument("claim_id")
    hs.add_argument("--verdict", choices=["supported", "partially_supported", "not_supported"], required=True)
    hs.add_argument("--overstatement", choices=["none", "minor", "material"], default="none")
    hs.add_argument("--omitted", default="")
    hs.add_argument("--note", required=True)
    hs.add_argument("--checker", default="human:analyst")
    # ---- v2: approvals and ledger ------------------------------------------------------------------------------
    ap = sub.add_parser("approve", help="USER approval for manual investment (explicit amount; reserves budget if executable)")
    ap.add_argument("offering")
    ap.add_argument("--amount-usd", required=True)
    ap.add_argument("--fee-usd")
    ap.add_argument("--fee-basis", choices=["confirmed", "upper_bound"])
    ap.add_argument("--issuer-key", required=True)
    ap.add_argument("--analysis-id", type=int)
    ap.add_argument("--min-investment-usd")
    ap.add_argument("--terms", default="")
    ap.add_argument("--availability", default="")
    ap.add_argument("--contract-doc", type=int)
    ap.add_argument("--override-rationale", default="")
    ap.add_argument("--expiry-days", type=int)
    ap.add_argument("--supersedes", type=int)
    ap.add_argument("--i-am-the-user", action="store_true", required=True, help="explicit confirmation that the user is acting")
    rl = sub.add_parser("release", help="user-confirmed cancellation of an approval's reservation")
    rl.add_argument("approval_id", type=int)
    rl.add_argument("--reason", required=True)
    lr = sub.add_parser("ledger-record", help="record something that actually happened (manual investment, fee, refund, ...)")
    lr.add_argument("--type", required=True)
    lr.add_argument("--offering", required=True)
    lr.add_argument("--date", required=True, help="effective date (America/New_York)")
    lr.add_argument("--amount-usd", default="0")
    lr.add_argument("--fee-usd", default="0")
    lr.add_argument("--approval", type=int)
    lr.add_argument("--related", type=int)
    lr.add_argument("--ref", help="confirmation/transaction reference (duplicate imports are ignored)")
    lr.add_argument("--doc-file", help="confirmation/contract file: stored PRIVATELY outside git")
    lr.add_argument("--verification", default="user_reported",
                    choices=["user_reported", "platform_confirmation", "document_verified"])
    lr.add_argument("--security")
    lr.add_argument("--quantity")
    lr.add_argument("--note", default="")
    lv = sub.add_parser("ledger-void", help="append a correction that voids an earlier ledger event")
    lv.add_argument("event_id", type=int)
    lv.add_argument("--reason", required=True)
    sub.add_parser("budget", help="current budget period, limits, reservations")
    sub.add_parser("positions", help="positions (written to the private directory)")
    sc = sub.add_parser("spot-check", help="re-find cited quotes in the original snapshots with an independent extractor")
    sc.add_argument("analysis_id", type=int)
    sc.add_argument("--n", type=int, default=6)
    sub.add_parser("eval-report")
    sub.add_parser("report-monthly-v2")
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
    if a.cmd == "migrations":
        return {"migrations": [dict(r) for r in ctx.con.execute("SELECT * FROM schema_migrations")]}
    if a.cmd == "ack-policy":
        from . import ledger
        path = ledger.SCREENING_POLICY if a.kind == "screening" else ledger.POLICY_DIR / "budget_policy_v1.yaml"
        ver = "screening_policy_v1" if a.kind == "screening" else "budget_policy_v1"
        return {"ack_id": ledger.acknowledge_policy(ctx, a.kind, ver, path, a.statement)}
    if a.cmd == "confirm-issuer":
        from . import ledger
        ledger.confirm_issuer(ctx, a.member_cik.zfill(10), a.issuer_key, a.basis)
        return {"member_cik": a.member_cik, "issuer_key": a.issuer_key}
    if a.cmd == "pack":
        from . import packs
        r = packs.build_pack(ctx, a.offering, a.cutoff)
        return {k: r[k] for k in ("pack_id", "sha256", "n_documents", "n_pages", "gaps", "critical_checklist")}
    if a.cmd == "analyst-register":
        from . import analysis
        analysis.register_version(ctx, a.version_id, a.role, a.description, a.model, a.dev_offering, a.prompt_version,
                                  a.repair_rounds)
        return {"registered": a.version_id}
    if a.cmd == "analyze":
        from . import analysis, packs
        pack_id = a.pack or packs.build_pack(ctx, a.offering)["pack_id"]
        adapter = (analysis.FileAdapter(Path(a.dir)) if a.adapter == "files"
                   else analysis.ClaudeCLIAdapter(model=a.model, max_budget_usd=a.max_budget_usd))
        return {"pack_id": pack_id, **analysis.run_analysis(ctx, a.offering, pack_id, adapter, a.version)}
    if a.cmd == "analysis-export":
        from . import analysis
        return {"written": analysis.export_stage_prompts(ctx, a.pack_id, Path(a.out))}
    if a.cmd == "revalidate":
        from . import analysis
        return analysis.revalidate(ctx, a.analysis_id)
    if a.cmd == "analyst-register-v2":
        from . import analysis_v2
        analysis_v2.register_v2(ctx, a.version_id, a.description, a.dev_offering, a.repair_rounds, a.model)
        return {"registered": a.version_id}
    if a.cmd == "analyze-v2":
        from . import analysis, analysis_v2
        r = analysis_v2.run_v2(ctx, a.offering, a.pack, analysis.ClaudeCLIAdapter(model=a.model, max_budget_usd=a.max_budget_usd),
                               a.version, note=a.note)
        r.pop("usage", None)
        return r
    if a.cmd == "brief-v2":
        from . import brief_v2
        return {"brief": str(brief_v2.build_brief_v2(ctx, a.analysis_id))}
    if a.cmd == "access-probe":
        from . import access
        cd = access.cooldown_active(ctx, host=a.url.split("/")[2], days=int(ctx.cfg["platform"]["block_cooldown_days"]))
        if cd:
            return {"refused": f"block recorded {cd['attempted_utc']} ({cd['result']}) is within the cooldown; no retry"}
        csvp = ctx.root / "reports" / "republic_access_attempts.csv"
        fn = access.http_attempt if a.method == "http" else access.browser_attempt
        r = fn(ctx, a.url, csvp)
        return {k: r[k] for k in ("attempt_id", "url", "method", "http_status", "result", "challenge_state", "login_state")}
    if a.cmd == "target-ocr":
        from . import packs, targeted
        t = targeted.target(ctx, a.document_id, cap=a.cap)
        p = packs.build_pack(ctx, a.offering, a.cutoff, ocr_overrides={a.document_id: t})
        return {"pack_id": p["pack_id"], "selected_pages": t["selected"], "unprocessed_pages": len(t["unprocessed"]),
                "gaps": p["gaps"]}
    if a.cmd == "forecast-flag":
        from . import analysis_v2
        return {"lineage_id": analysis_v2.forecast_lineage(ctx, a.prediction_id, a.relation, a.reason, a.successor)}
    if a.cmd == "support-check-manual":
        ctx.con.execute("INSERT INTO support_checks(analysis_id, claim_id, checker, judgment_label, citation_exists, passage_supports, "
                        "omitted_qualifications, evidence_type, conflicts, overstatement, verdict, note, checked_utc) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (a.analysis_id, a.claim_id, a.checker, "human_spot_check_against_source_page", 1,
                         {"supported": "yes", "partially_supported": "partly"}.get(a.verdict, "no"), a.omitted, "",
                         "", a.overstatement, a.verdict, a.note, ctx.now()))
        ctx.con.commit()
        return {"recorded": a.claim_id}
    if a.cmd == "brief":
        from . import brief
        return {"brief": str(brief.build_brief(ctx, a.analysis_id))}
    if a.cmd == "approve":
        from . import ledger
        return ledger.approve(ctx, offering_id=a.offering, amount_usd=a.amount_usd, fee_usd=a.fee_usd, fee_basis=a.fee_basis,
                              issuer_key_confirmed=a.issuer_key, analysis_id=a.analysis_id, min_investment_usd=a.min_investment_usd,
                              applicable_terms=a.terms, availability_note=a.availability, contract_document_id=a.contract_doc,
                              override_rationale=a.override_rationale, expiry_days=a.expiry_days, supersedes=a.supersedes)
    if a.cmd == "release":
        from . import ledger
        return {"event_id": ledger.release_reservation(ctx, a.approval_id, a.reason)}
    if a.cmd == "ledger-record":
        from . import ledger
        doc_id = None
        if a.doc_file:
            import hashlib
            data = Path(a.doc_file).read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            d = ctx.root / ctx.cfg.raw["paths"]["private_dir"] / "blobs"
            d.mkdir(parents=True, exist_ok=True)
            (d / sha).write_bytes(data)
            doc_id = ctx.record_document(url=f"private-ledger-doc:{sha[:12]}", source_type="user_import", offering_id=a.offering,
                                         data=data, visibility="private", description=f"ledger evidence ({a.type})",
                                         extraction_method="user_import", blob_override=(sha, str((d / sha).relative_to(ctx.root))))
        return ledger.record_event(ctx, event_type=a.type, offering_id=a.offering, effective_date=a.date, amount_usd=a.amount_usd,
                                   fee_usd=a.fee_usd, approval_id=a.approval, related_event_id=a.related, external_ref=a.ref,
                                   document_id=doc_id, verification_status=a.verification, security=a.security,
                                   quantity=a.quantity, note=a.note)
    if a.cmd == "ledger-void":
        from . import ledger
        return {"event_id": ledger.void_event(ctx, a.event_id, a.reason)}
    if a.cmd == "budget":
        from . import ledger
        st = ledger.current_state(ctx)
        return {"period": st.period_label, "anchor": str(st.anchor), "period_start": str(st.period_start),
                "period_end_exclusive": str(st.period_end_exclusive), "annual_used": ledger.usd(st.annual_used_cents),
                "annual_remaining": ledger.usd(st.annual_remaining_cents),
                "active_reservations": ledger.usd(st.active_reservation_cents),
                "issuers": {k: ledger.usd(v) for k, v in st.issuer_used_cents.items()}}
    if a.cmd == "positions":
        from . import ledger
        out = ctx.root / ctx.cfg.raw["paths"]["private_dir"] / "reports" / "positions.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(ledger.positions(ctx), indent=1, default=str))
        return {"written_privately_to": str(out)}
    if a.cmd == "spot-check":
        from . import spot_check
        return spot_check.check(ctx, a.analysis_id, a.n)
    if a.cmd == "eval-report":
        from . import evaluation
        return evaluation.evaluation_report(ctx)
    if a.cmd == "report-monthly-v2":
        from . import portfolio_report
        return {"report": portfolio_report.monthly_v2(ctx)}
    raise ValueError(a.cmd)
