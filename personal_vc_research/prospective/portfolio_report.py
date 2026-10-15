"""Monthly v2 report: budget, approvals, ledger positions, new risks, forecasts, evaluation and operations.

Position-level amounts are personal: in live mode the report is written to the gitignored private directory. Only a
synthetic demo database writes it to reports/.
"""
from __future__ import annotations

import datetime as dt
import json

from . import evaluation, journal, ledger
from .core import Ctx, iso, parse_utc


def _md(rows, cols):
    if not rows:
        return ["_none_"]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "")).replace("|", "/")[:140] for c in cols) + " |")
    return out


def monthly_v2(ctx: Ctx) -> str:
    demo = ctx.cfg.raw.get("ledger_mode") == "demo"
    now = ctx.now()
    start = iso(parse_utc(now) - dt.timedelta(days=30))
    pol = ledger.load_budget_policy()
    st = ledger.current_state(ctx, now, pol)
    issuers = [{"issuer_key": k, "committed": ledger.usd(v), "remaining": ledger.usd(pol["issuer_lifetime_committed_limit_cents"] - v)}
               for k, v in sorted(st.issuer_used_cents.items())]
    appr = [dict(r) for r in ctx.con.execute("SELECT approval_id, offering_id, issuer_key, amount_cents, fee_cents, fee_basis, status, "
                                             "approved_utc, expires_utc FROM approvals ORDER BY approval_id")]
    for a in appr:
        a["amount"] = ledger.usd(a["amount_cents"])
        a["fee"] = ledger.usd(a["fee_cents"]) if a["fee_cents"] is not None else "unknown"
        a["reservation_active"] = any(e["approval_id"] == a["approval_id"] for e in st.active_reservations)
    pos = ledger.positions(ctx)
    for p in pos:
        for k in ("funded_cost_cents", "refunds_cents", "distributions_cents", "sale_proceeds_net_cents"):
            p[k.replace("_cents", "")] = ledger.usd(p[k])
    flagged = [dict(r) for r in ctx.con.execute("SELECT event_id, event_type, offering_id, effective_date, policy_flags FROM ledger_events "
                                                "WHERE policy_flags != '' ORDER BY event_id")]
    risks = [dict(r) for r in ctx.con.execute(
        "SELECT offering_id, event_type, event_date, interpretation FROM events WHERE observed_utc > ? ORDER BY event_date", (start,))]
    fs = journal.forecast_status(ctx)
    fstate = {}
    for f in fs:
        fstate[f["state"]] = fstate.get(f["state"], 0) + 1
    ev = evaluation.evaluation_report(ctx)
    eff = ctx.con.execute("SELECT ROUND(SUM(minutes)) FROM effort_log WHERE activity_date > ?", (start[:10],)).fetchone()[0]
    gaps = [dict(r) for r in ctx.con.execute("SELECT kind, COUNT(*) n FROM gaps WHERE utc > ? GROUP BY kind", (start,))]
    runs = [dict(r) for r in ctx.con.execute("SELECT status, COUNT(*) n, ROUND(SUM(cost_usd),2) llm_cost_usd FROM analysis_runs "
                                             "WHERE finished_utc > ? GROUP BY status", (start,))]
    period = (f"{st.period_label}: {st.period_start} → {st.period_end_exclusive} (exclusive), anchor {st.anchor}"
              if st.anchor else "pre_start (no actual investment yet; the 12-month clock has not started)")
    L = [f"# Monthly portfolio and research report — {now[:10]}" + (" — **SYNTHETIC DEMO DATA**" if demo else ""), "",
         "No orders are placed and no money is moved by this system. Amounts are what the user recorded.", "",
         "## Budget (budget_policy_v1; the annual limit is a ceiling, not a target)", "",
         f"* Budget period: {period}",
         f"* Annual committed: {ledger.usd(st.annual_used_cents)} of {ledger.usd(st.annual_limit_cents)} "
         f"(funded in period {ledger.usd(st.annual_funded_cents)} + active reservations {ledger.usd(st.active_reservation_cents)}); "
         f"remaining {ledger.usd(st.annual_remaining_cents)}",
         "* Per-issuer lifetime committed (limit $1,200 each; does not reset after sales, losses or write-offs):", "",
         *_md(issuers, ["issuer_key", "committed", "remaining"]),
         "", "## Approvals and reservations", "",
         *_md(appr, ["approval_id", "offering_id", "issuer_key", "amount", "fee", "fee_basis", "status", "expires_utc", "reservation_active"]),
         "", "## Positions (funded cost, refunds, distributions and holdings kept separate)", "",
         *_md(pos, ["position_id", "status", "funded_cost", "refunds", "distributions", "sale_proceeds_net", "holding",
                    "realized_note", "flags"]),
         "", "## Policy flags on recorded transactions (recorded truthfully, never altered)", "", *_md(flagged, list(flagged[0]) if flagged else []),
         "", "## Material new filings/contract events (last 30 days)", "", *_md(risks, ["offering_id", "event_type", "event_date", "interpretation"]),
         "", "## Forecasts", "", *_md([{"state": k, "n": v} for k, v in fstate.items()], ["state", "n"]),
         "", "Unknown outcomes are never scored as false. Probabilities are uncalibrated model judgments.",
         "", "## Analyst versions and evaluation", "", "```json", json.dumps(ev["track2_forecasting"], indent=1), "```",
         "", *_md(runs, ["status", "n", "llm_cost_usd"]),
         "", "## User time and operations", "", f"* User time recorded (30 days): {eff or 0} minutes (budget: about 6 h/week).",
         *_md(gaps, ["kind", "n"]), ""]
    text = "\n".join(L)
    if demo:
        out = ctx.root / ctx.cfg.raw["paths"]["reports_dir"] / f"monthly_v2_DEMO_{now[:10]}.md"
    else:
        out = ctx.root / ctx.cfg.raw["paths"]["private_dir"] / "reports" / f"monthly_v2_{now[:10]}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    return str(out)
