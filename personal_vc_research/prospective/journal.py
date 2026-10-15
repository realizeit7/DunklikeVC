"""Review packets, decision journal, paper selections, forecasts, effort log and the weekly review queue.

Rules enforced here and in the schema:
* A decision's evidence is exactly the documents observed (retrieved) at or before its evidence cutoff.
* A prospective decision's cutoff equals its decision timestamp; a retrospective reconstruction is labelled as such.
* Only a user-confirmed entry can be select/pass/defer; drafts stay 'unreviewed' with a draft_recommendation.
* No numeric investment-quality score; no return series; no assumed fill for paper selections.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from .core import Ctx, iso, norm_utc, parse_utc


def evidence_docs(ctx: Ctx, oid: str, cutoff: str) -> list:
    o = ctx.con.execute("SELECT issuer_id FROM offerings WHERE offering_id=?", (oid,)).fetchone()
    return ctx.con.execute(
        "SELECT * FROM documents WHERE (offering_id=? OR (offering_id='' AND issuer_cik=?)) AND retrieved_utc <= ? "
        "AND http_status=200 ORDER BY retrieved_utc, document_id", (oid, o["issuer_id"] if o else "", cutoff)).fetchall()


def facts_as_of(ctx: Ctx, oid: str, cutoff: str) -> list:
    """Latest fact per (field, period) among facts observed at or before the cutoff."""
    rows = ctx.con.execute("SELECT * FROM facts WHERE offering_id=? AND observed_utc <= ? ORDER BY observed_utc, fact_id",
                           (oid, cutoff)).fetchall()
    latest: dict = {}
    for r in rows:
        if r["verification_status"] == "text_regex_unreviewed" and r["field"].endswith("_candidate"):
            latest[(r["field"], r["fact_id"])] = r   # keep every candidate hit
        else:
            latest[(r["field"], r["financial_period"] or "")] = r
    return list(latest.values())


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_packet(ctx: Ctx, oid: str, cutoff: str | None = None, label: str = "prospective") -> tuple[Path, str]:
    cutoff = norm_utc(cutoff) if cutoff else ctx.now()
    o = ctx.con.execute("SELECT * FROM offerings WHERE offering_id=?", (oid,)).fetchone()
    docs = evidence_docs(ctx, oid, cutoff)
    facts = facts_as_of(ctx, oid, cutoff)
    f = {(r["field"], r["financial_period"] or ""): r for r in facts if not r["field"].endswith("_candidate")}
    cands = [r for r in facts if r["field"].endswith("_candidate")]

    def val(field, period=""):
        r = f.get((field, period))
        return (r["value"] if r and r["value"] is not None else None), r

    L = [f"# Review packet — {o['legal_name']} ({oid})", "",
         f"* Packet type: **{label}**. Generated {ctx.now()}. **Evidence cutoff: {cutoff}** (only documents retrieved at or "
         "before this time are used).",
         f"* Cohort: `{o['cohort']}`. Eligibility: {o['eligibility']} ({o['security_class']}). "
         f"Initial Form C {o['initial_accession']} filed {o['initial_filing_date']} (accepted {o['initial_acceptance_utc']}).",
         f"* Availability: **{o['availability_status']}** — {o['availability_evidence']}. Deadline in Form C: {o['deadline_date'] or 'n/a'} "
         "(a future deadline is not proof the offering is open).",
         "* Decision status: **unreviewed** until the user records a decision. This packet is not a recommendation and contains "
         "no investment-quality score.", "",
         "## 1. What the company sells and who pays", "",
         f"* Legal form / jurisdiction / incorporated: {val('legal_form')[0]} / {val('jurisdiction')[0]} / {val('date_incorporation')[0]}",
         f"* Website (issuer-reported): {val('issuer_website')[0]}",
         "* Product, customer and payer: **not extracted automatically** — read the Form C business description "
         "(evidence documents below) and record it in the decision entry.", "",
         "## 2. Evidence for business claims (issuer-reported Form C XML; unaudited unless the attached statements say otherwise)", "",
         "| Field | Most recent FY | Prior FY | Locator / status |", "|---|---|---|---|"]
    for field in ["revenue", "cost_of_goods_sold", "net_income", "cash_and_equivalents", "total_assets", "short_term_debt",
                  "long_term_debt", "taxes_paid"]:
        a, ra = val(field, "most_recent_fiscal_year")
        b, rb = val(field, "prior_fiscal_year")
        loc = (ra or rb)["verification_status"] if (ra or rb) else "not captured"
        L.append(f"| {field} | {a if a is not None else 'missing'} | {b if b is not None else 'missing'} | {loc} |")
    emp = val("current_employees")[0]
    L.append(f"| current_employees | {emp if emp is not None else 'missing'} | | |")
    r1, r0 = _num(val("revenue", "most_recent_fiscal_year")[0]), _num(val("revenue", "prior_fiscal_year")[0])
    if r1 is not None and r0:
        L += ["", f"* Derived: revenue growth = (most recent FY − prior FY) / prior FY = ({r1:,.0f} − {r0:,.0f}) / {r0:,.0f} = "
                  f"{(r1 - r0) / r0:+.1%}. Assumes both fiscal years are full, comparable periods (not verified)."]
    else:
        L += ["", "* Derived revenue growth: not computed (an input is missing or the prior-year value is 0)."]
    L += ["", "## 3. Contract and price considerations", "",
          f"* Security: {val('security_type')[0]} — {val('security_description')[0]} (class `{o['security_class']}`).",
          f"* Price per security: {val('price_per_security')[0]} ({val('price_determination_method')[0]}); target "
          f"{val('target_offering_amount')[0]}; maximum {val('maximum_offering_amount')[0]}; oversubscription {val('oversubscription_accepted')[0]}.",
          f"* Intermediary compensation (as filed): {val('intermediary_compensation_text')[0]}",
          f"* Intermediary financial interest (as filed): {val('intermediary_financial_interest_text')[0]}",
          f"* Contract coverage: {val('contract_coverage')[0] or 'not assessed'}. Summary text is **not** equivalent to reading the contract.",
          "* Term candidates found by text search (**unreviewed**; confirm against the contract before relying on them):", ""]
    if cands:
        L += ["| Field | Value | Locator |", "|---|---|---|"]
        for c in cands[:25]:
            L.append(f"| {c['field']} | {c['value']} | {c['locator'][:160].replace('|', '/')} |")
        if len(cands) > 25:
            L.append(f"| … | {len(cands) - 25} more | see facts table |")
    else:
        L.append("  * none found (terms may be in an unreadable text layer, an exhibit, or not disclosed).")
    missing = sorted({r["field"] for r in facts if r["verification_status"] == "missing"})
    status_lines = [r["value"] for r in facts if r["field"] == "document_text_status"]
    L += ["", "## 4. Main risks and counterarguments (to be completed by the reviewer)", "",
          "* Write the strongest case against participating. Facts above are issuer claims; nothing here is verified by a third party.",
          "", "## 5. What information is missing", "",
          f"* Structured fields absent from the Form C XML: {', '.join(missing) if missing else 'none'}.",
          "* Not extracted in v1 (requires reading the documents): founders/team (count, roles, prior ventures), customers and "
          "traction evidence, use of proceeds, valuation-cap vs. valuation basis (pre/post-money), discount, conversion triggers, "
          "liquidity-event and investor-rights provisions.",
          *[f"* Document text: {s}" for s in status_lines],
          "", "## 6. What future evidence would change the judgment", "",
          "* List observable items (e.g. a C-U with completion language, next C-AR revenue, a financing with closing evidence).",
          "  Optional forecasts can be recorded with `forecast-add` (explicit event, horizon, probability, resolution rule).", "",
          "## Evidence documents (retrieved at or before the cutoff)", "",
          "| doc id | type | name | filed | retrieved (UTC) | sha256 |", "|---|---|---|---|---|---|"]
    for d in docs:
        L.append(f"| {d['document_id']} | {d['source_type']} | {d['description'] or d['source_url'][-50:]} | "
                 f"{d['claimed_publication_date']} | {d['retrieved_utc']} | {(d['sha256'] or '')[:12]} |")
    meta = {"offering_id": oid, "evidence_cutoff_utc": cutoff, "evidence_document_ids": [d["document_id"] for d in docs],
            "label": label}
    L += ["", "```json", json.dumps(meta), "```", ""]
    out = ctx.root / ctx.cfg.raw["paths"]["packets_dir"] / f"{oid}_{cutoff.replace(':', '').replace('+0000', 'Z')}_{label}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(L)
    out.write_text(text)
    return out, hashlib.sha256(text.encode()).hexdigest()


def packet_meta(path: Path) -> dict:
    t = path.read_text()
    return json.loads(t.rsplit("```json", 1)[1].split("```", 1)[0])


def record_decision(ctx: Ctx, oid: str, status: str, analyst: str, user_confirmed: bool, reasons: str = "",
                    counterarguments: str = "", unresolved: str = "", draft_recommendation: str = "",
                    paper_amount_usd: float | None = None, packet: Path | None = None,
                    retrospective_as_of: str | None = None) -> int:
    now = ctx.now()
    kind = "retrospective_reconstruction" if retrospective_as_of else "prospective"
    cutoff = norm_utc(retrospective_as_of) if retrospective_as_of else now
    if not user_confirmed and status != "unreviewed":
        raise ValueError("only the user can record select/pass/defer; drafts stay 'unreviewed' with a draft_recommendation")
    ids = None
    psha = None
    if packet is not None:
        meta = packet_meta(packet)
        if meta["offering_id"] != oid or meta["evidence_cutoff_utc"] > cutoff:
            raise ValueError("packet belongs to another offering or its evidence cutoff is after the decision cutoff")
        ids = meta["evidence_document_ids"]
        psha = hashlib.sha256(packet.read_text().encode()).hexdigest()
    cur = ctx.con.execute(
        """INSERT INTO decisions(offering_id, decision_utc, kind, evidence_cutoff_utc, status, draft_recommendation, reasons,
           counterarguments, unresolved_questions, analyst, user_confirmed, paper_amount_usd, packet_path, packet_sha256)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (oid, now, kind, cutoff, status, draft_recommendation, reasons, counterarguments, unresolved, analyst,
         1 if user_confirmed else 0, paper_amount_usd, str(packet.relative_to(ctx.root)) if packet else None, psha))
    did = cur.lastrowid
    if ids is None:
        ids = [d["document_id"] for d in evidence_docs(ctx, oid, cutoff)]
    for i in ids:   # the schema trigger rejects any document retrieved after the cutoff
        ctx.con.execute("INSERT INTO decision_evidence(decision_id, document_id) VALUES (?,?)", (did, i))
    ctx.con.commit()
    return did


# ---- forecasts ---------------------------------------------------------------------------------------
def add_forecast(ctx: Ctx, oid: str, target_event: str, event_kind: str, horizon_months: int, probability: float,
                 resolution_rule: str, reporting_lag_days: int, missing_evidence_treatment: str, forecaster: str,
                 permitted_evidence: str = "", decision_id: int | None = None, revises: int | None = None,
                 deadline_override: str | None = None) -> int:
    now = parse_utc(ctx.now())
    if revises is not None:
        orig = ctx.con.execute("SELECT * FROM predictions WHERE prediction_id=?", (revises,)).fetchone()
        deadline = orig["deadline_utc"]          # a revision never moves the original deadline
        horizon_months = orig["horizon_months"]
    elif deadline_override:                      # v2.1 forecasts carry an explicit deadline
        deadline = norm_utc(deadline_override)
    else:
        deadline = iso(now + dt.timedelta(days=round(30.4375 * horizon_months)))
    cur = ctx.con.execute(
        """INSERT INTO predictions(offering_id, decision_id, created_utc, forecaster, target_event, event_kind, horizon_months,
           deadline_utc, probability, resolution_rule, reporting_lag_days, missing_evidence_treatment, permitted_evidence,
           revises_prediction_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (oid, decision_id, iso(now), forecaster, target_event, event_kind, horizon_months, deadline, probability,
         resolution_rule, reporting_lag_days, missing_evidence_treatment, permitted_evidence, revises))
    ctx.con.commit()
    return cur.lastrowid


def resolve_forecast(ctx: Ctx, pid: int, outcome: str, evidence: str, adjudicator: str) -> int:
    p = ctx.con.execute("SELECT * FROM predictions WHERE prediction_id=?", (pid,)).fetchone()
    now = parse_utc(ctx.now())
    window_end = parse_utc(p["deadline_utc"]) + dt.timedelta(days=int(p["reporting_lag_days"]))
    if outcome == "false" and now < window_end:
        raise ValueError(f"cannot resolve false before deadline + reporting lag ({iso(window_end)})")
    if outcome in ("true", "false") and not evidence.strip():
        raise ValueError("a true/false resolution needs cited evidence")
    cur = ctx.con.execute("INSERT INTO prediction_resolutions(prediction_id, resolved_utc, outcome, evidence, adjudicator) "
                          "VALUES (?,?,?,?,?)", (pid, iso(now), outcome, evidence, adjudicator))
    ctx.con.commit()
    return cur.lastrowid


def forecast_status(ctx: Ctx) -> list[dict]:
    """Current state per ORIGINAL forecast and per revision. Missing evidence never becomes 'false'."""
    out = []
    now = ctx.now()
    for p in ctx.con.execute("SELECT * FROM predictions ORDER BY prediction_id"):
        res = ctx.con.execute("SELECT outcome FROM prediction_resolutions WHERE prediction_id=? ORDER BY resolution_id DESC LIMIT 1",
                              (p["prediction_id"],)).fetchone()
        window_end = iso(parse_utc(p["deadline_utc"]) + dt.timedelta(days=int(p["reporting_lag_days"])))
        if res and res["outcome"] in ("true", "false"):
            state = f"resolved_{res['outcome']}"
        elif now < window_end:
            state = "pending"
        else:
            state = "unresolved_unknown" if (res and res["outcome"] == "unresolved_unknown") else "due_unadjudicated"
        out.append({**dict(p), "state": state, "window_end_utc": window_end})
    return out


def brier(rows: list[dict]) -> dict:
    """Brier score on ORIGINAL forecasts with a true/false resolution only; denominators always reported."""
    orig = [r for r in rows if r["revises_prediction_id"] is None]
    resolved = [r for r in orig if r["state"] in ("resolved_true", "resolved_false")]
    score = (sum((r["probability"] - (1.0 if r["state"] == "resolved_true" else 0.0)) ** 2 for r in resolved) / len(resolved)
             if resolved else None)
    return {"n_original": len(orig), "n_resolved": len(resolved), "n_unresolved": len(orig) - len(resolved), "brier": score,
            "note": "conditional on observed resolution; may be biased"}


# ---- effort and the review queue ------------------------------------------------------------------
def log_effort(ctx: Ctx, minutes: float, activity: str, activity_date: str, note: str = "") -> None:
    ctx.con.execute("INSERT INTO effort_log(entered_utc, activity_date, minutes, activity, note) VALUES (?,?,?,?,?)",
                    (ctx.now(), activity_date, minutes, activity, note))
    ctx.con.commit()


def unreviewed(ctx: Ctx, cohort: str | None = None) -> list:
    sql = ("SELECT o.* FROM offerings o WHERE eligibility='eligible' AND cohort IN ('inception','initial_watchlist') "
           "AND NOT EXISTS (SELECT 1 FROM decisions d WHERE d.offering_id=o.offering_id AND d.user_confirmed=1 "
           "AND d.kind='prospective')")
    rows = ctx.con.execute(sql + " ORDER BY (cohort='inception') DESC, initial_acceptance_utc, offering_id").fetchall()
    return [r for r in rows if cohort is None or r["cohort"] == cohort]


def build_queue(ctx: Ctx, week: str, discretionary: list[str] | None = None) -> list[str]:
    """Transparent default: oldest unreviewed first (inception cohort before watchlist), size from config."""
    n = int(ctx.cfg["schedule"]["review_queue_size"])
    existing = [r["offering_id"] for r in ctx.con.execute("SELECT offering_id FROM review_queue_log WHERE week=? ORDER BY position",
                                                          (week,))]
    if existing and not discretionary:
        return existing
    picks = [o["offering_id"] for o in unreviewed(ctx)][:n]
    for i, oid in enumerate(picks):
        ctx.con.execute("INSERT INTO review_queue_log(utc, week, offering_id, rule, position, discretionary) VALUES (?,?,?,?,?,0)",
                        (ctx.now(), week, oid, ctx.cfg["schedule"]["review_queue_rule"], i + 1))
    for j, oid in enumerate(discretionary or []):
        ctx.con.execute("INSERT INTO review_queue_log(utc, week, offering_id, rule, position, discretionary, note) "
                        "VALUES (?,?,?,?,?,1,?)", (ctx.now(), week, oid, "user_discretionary", n + j + 1,
                                                   "user-chosen review (reviewing is not selecting)"))
    ctx.con.commit()
    return picks + list(discretionary or [])
