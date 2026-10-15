"""Evaluation scaffolding: five separate tracks and baseline-vs-challenger comparisons on the SAME frozen packs.

Rules:
* A version must be registered before its outputs are evaluated against outcomes (registration time is stored).
* Development cases (used while writing a prompt) are excluded from evaluation of that version.
* Outcomes count only if they were resolved after BOTH versions were registered.
* Repeated observations of the same issuer are grouped (one issuer = one cluster).
* With few resolved events the report says "insufficient evidence"; no version is promoted automatically.
* Forecast accuracy is not investment profitability.
"""
from __future__ import annotations

import json
from collections import defaultdict

from . import journal, ledger
from .core import Ctx

MIN_RESOLVED_FOR_COMPARISON = 30     # proposed research convention, not a statistical guarantee


def _q(ctx: Ctx, sql: str, *a) -> list[dict]:
    return [dict(r) for r in ctx.con.execute(sql, a)]


def forecast_track(ctx: Ctx) -> dict:
    fs = journal.forecast_status(ctx)
    # forecasts from prompt-development cases are excluded from the evaluation of that version
    meta = {r["prediction_id"]: r for r in _q(ctx, "SELECT m.* FROM prediction_meta m JOIN analysis_runs a USING(analysis_id) "
                                                   "WHERE a.split = 'evaluation'")}
    by_version: dict = defaultdict(list)
    for f in fs:
        m = meta.get(f["prediction_id"])
        if m and f["revises_prediction_id"] is None:
            f["version_id"] = m["version_id"]
            by_version[m["version_id"]].append(f)
    out = {}
    for v, rows in by_version.items():
        b = journal.brier(rows)
        issuers = {ctx.con.execute("SELECT issuer_id FROM offerings WHERE offering_id=?", (r["offering_id"],)).fetchone()[0]
                   for r in rows if r["state"].startswith("resolved")}
        b["resolved_issuer_clusters"] = len(issuers)
        b["verdict"] = ("insufficient evidence" if b["n_resolved"] < MIN_RESOLVED_FOR_COMPARISON
                        else "estimable (conditional on observed resolution)")
        out[v] = b
    return out


def comparison(ctx: Ctx, baseline: str, challenger: str) -> dict:
    """Compare two registered versions on packs analysed by both. Outcomes only after both registrations."""
    vb, vc = [ctx.con.execute("SELECT * FROM analyst_versions WHERE version_id=?", (v,)).fetchone() for v in (baseline, challenger)]
    if vb is None or vc is None:
        return {"error": "both versions must be registered"}
    after = max(vb["registered_utc"], vc["registered_utc"])
    dev = set(json.loads(vb["development_offering_ids"])) | set(json.loads(vc["development_offering_ids"]))
    runs = _q(ctx, "SELECT * FROM analysis_runs WHERE version_id IN (?,?) AND split='evaluation'", baseline, challenger)
    by_pack = defaultdict(dict)
    for r in runs:
        if r["offering_id"] not in dev:
            by_pack[r["pack_sha256"]][r["version_id"]] = r
    shared = {k: v for k, v in by_pack.items() if len(v) == 2}
    agree = sum(1 for v in shared.values() if v[baseline]["status"] == v[challenger]["status"])
    resolved_after = _q(ctx, "SELECT COUNT(*) n FROM prediction_resolutions WHERE resolved_utc > ? AND outcome IN ('true','false')",
                        after)[0]["n"]
    return {"shared_frozen_packs": len(shared), "status_agreement": agree,
            "outcome_resolutions_after_registration": resolved_after,
            "verdict": "insufficient evidence" if resolved_after < MIN_RESOLVED_FOR_COMPARISON else "estimable; inspect clusters",
            "note": "no automatic promotion; prompt-development cases excluded"}


def evaluation_report(ctx: Ctx) -> dict:
    runs = _q(ctx, "SELECT status, version_id, split, COUNT(*) n FROM analysis_runs GROUP BY status, version_id, split")
    checks = _q(ctx, "SELECT result, method, COUNT(*) n FROM citation_checks GROUP BY result, method")
    user = _q(ctx, """SELECT a.status AS ai_status, COALESCE(p.status, d.status, 'no_user_action') AS user_action, COUNT(*) n
        FROM analysis_runs a
        LEFT JOIN (SELECT offering_id, status FROM approvals) p ON p.offering_id = a.offering_id
        LEFT JOIN (SELECT offering_id, status FROM decisions WHERE user_confirmed=1) d ON d.offering_id = a.offering_id
        GROUP BY 1, 2""")
    pos = ledger.positions(ctx)
    return {
        "track1_extraction_and_citations": {"automatic_validation": runs, "spot_checks": checks},
        "track2_forecasting": forecast_track(ctx),
        "track3_research_screen_behavior": runs,
        "track4_user_selection_behavior": user,
        "track5_actual_investment_outcomes": {"positions": len(pos),
                                             "realized": sum(1 for p in pos if p["realized_multiple"] is not None),
                                             "note": "insufficient evidence" if len(pos) < 10 else "see positions"},
        "caveats": ["forecast accuracy is not investment profitability",
                    "investors may receive private updates unavailable for non-investments: visibility differs",
                    "AI-passed, AI-failed, needs-information, approved, passed and unreviewed offerings follow the same schedule"],
    }
