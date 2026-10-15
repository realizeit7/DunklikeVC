"""Budget policy, user approvals/reservations and the append-only personal investment ledger.

All money is integer cents. Nothing here submits an order or moves funds: every investment, fee, refund,
distribution or sale is something the user did manually elsewhere and records here, with a supporting document.

Budget semantics (see policies/budget_policy_v1.yaml and the README):
* Budget periods are anchored on the effective date (America/New_York) of the first actual investment, and repeat on
  consecutive anniversaries. A Feb-29 anchor has Feb-28 anniversaries in non-leap years.
* Annual usage for the period containing the check date = funded cost (principal + investor-paid fees) of investments
  effective in that period, less verified refunds attributed to the original investment's period, plus ALL active
  reservations (conservative rollover: an unsettled reservation always counts in the period being checked).
* Before the first investment there is no anchor: the 'pre_start' bucket = all active reservations.
* Issuer usage (lifetime, per user-confirmed issuer_key) = funded cost + fees + active reservations - verified refunds.
  Distributions, sale proceeds, losses, write-offs and conversions never restore budget.
* A reservation stops counting when the approved investment is submitted (consumed, no double count), when the user
  confirms a cancellation (released), or when the approval expires unexecuted.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .core import Ctx, iso, norm_utc, parse_utc

POLICY_DIR = Path(__file__).parent / "policies"
NY = ZoneInfo("America/New_York")
FUNDING_TYPES = {"investment_submitted"}
NO_BUDGET_EFFECT = {"investment_finalized", "investment_canceled", "security_conversion", "corporate_action",
                    "cash_distribution", "sale_proceeds", "sale_fee", "write_off_observed", "residual_holding_update"}


def cents(usd: str | float | Decimal) -> int:
    return int((Decimal(str(usd)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def usd(c: int) -> str:
    return f"${Decimal(c) / 100:,.2f}"


def load_budget_policy(version: str = "budget_policy_v1") -> dict:
    p = POLICY_DIR / f"{version}.yaml"
    pol = yaml.safe_load(p.read_text())
    pol["_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    return pol


def add_years(d: dt.date, n: int) -> dt.date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:            # Feb 29 -> Feb 28 in a non-leap year
        return d.replace(year=d.year + n, day=28)


def ny_date(utc_iso: str) -> dt.date:
    return parse_utc(utc_iso).astimezone(NY).date()


# ---- pure budget computation --------------------------------------------------------------------------
@dataclass
class BudgetState:
    as_of: dt.date
    anchor: dt.date | None
    period_label: str
    period_start: dt.date | None
    period_end_exclusive: dt.date | None
    annual_funded_cents: int = 0
    active_reservation_cents: int = 0
    annual_used_cents: int = 0
    annual_limit_cents: int = 0
    issuer_used_cents: dict = field(default_factory=dict)
    issuer_limit_cents: int = 0
    active_reservations: list = field(default_factory=list)

    @property
    def annual_remaining_cents(self) -> int:
        return self.annual_limit_cents - self.annual_used_cents

    def issuer_remaining_cents(self, issuer_key: str) -> int:
        return self.issuer_limit_cents - self.issuer_used_cents.get(issuer_key, 0)


def _live(events: list[dict]) -> list[dict]:
    voided = {e["related_event_id"] for e in events if e["event_type"] == "correction_void"}
    return [e for e in events if e["event_id"] not in voided and e["event_type"] != "correction_void"]


def period_of(anchor: dt.date | None, d: dt.date) -> tuple[str, dt.date | None, dt.date | None]:
    if anchor is None or d < anchor:
        return "pre_start", None, anchor
    k = d.year - anchor.year
    while add_years(anchor, k) > d:
        k -= 1
    while add_years(anchor, k + 1) <= d:
        k += 1
    return f"P{k + 1}", add_years(anchor, k), add_years(anchor, k + 1)


def active_reservations(events: list[dict], as_of_utc: str, approvals: dict[int, dict]) -> list[dict]:
    ev = _live(events)
    consumed = {e["approval_id"] for e in ev if e["event_type"] in FUNDING_TYPES and e["approval_id"]}
    released = {e["approval_id"] for e in ev if e["event_type"] == "reservation_released" and e["approval_id"]}
    out = []
    for e in ev:
        if e["event_type"] != "reservation_created" or e["approval_id"] in consumed | released:
            continue
        a = approvals.get(e["approval_id"])
        if a and a["expires_utc"] <= as_of_utc:
            continue      # expired, unexecuted approvals no longer reserve budget
        out.append(e)
    return out


def budget_state(events: list[dict], approvals: dict[int, dict], as_of_utc: str, policy: dict) -> BudgetState:
    ev = _live(events)
    funding = [e for e in ev if e["event_type"] in FUNDING_TYPES]
    anchor = min((dt.date.fromisoformat(e["effective_date"]) for e in funding), default=None)
    as_of = ny_date(as_of_utc)
    label, start, end = period_of(anchor, as_of)
    st = BudgetState(as_of, anchor, label, start, end, annual_limit_cents=policy["annual_committed_limit_cents"],
                     issuer_limit_cents=policy["issuer_lifetime_committed_limit_cents"])
    by_id = {e["event_id"]: e for e in ev}

    def inv_period(e: dict) -> str:
        return period_of(anchor, dt.date.fromisoformat(e["effective_date"]))[0]

    for e in ev:
        t = e["event_type"]
        cost = 0
        attributed = None
        if t in FUNDING_TYPES:
            cost, attributed = e["amount_cents"] + e["fee_cents"], inv_period(e)
        elif t == "investor_fee_paid":
            rel = by_id.get(e["related_event_id"])
            cost, attributed = e["fee_cents"] + e["amount_cents"], inv_period(rel or e)
        elif t == "refund_verified":
            rel = by_id.get(e["related_event_id"])
            orig = (rel["amount_cents"] + rel["fee_cents"]) if rel else 0
            prior = sum(x["amount_cents"] + x["fee_cents"] for x in ev if x["event_type"] == "refund_verified"
                        and x["related_event_id"] == e["related_event_id"] and x["event_id"] < e["event_id"])
            refund = min(e["amount_cents"] + e["fee_cents"], max(0, orig - prior))   # only refunded eligible cost
            cost, attributed = -refund, (inv_period(rel) if rel else label)
        if cost:
            st.issuer_used_cents[e["issuer_key"]] = st.issuer_used_cents.get(e["issuer_key"], 0) + cost
            if attributed == label and label != "pre_start":
                st.annual_funded_cents += cost
    act = active_reservations(events, as_of_utc, approvals)
    st.active_reservations = act
    st.active_reservation_cents = sum(e["amount_cents"] + e["fee_cents"] for e in act)
    for e in act:
        st.issuer_used_cents[e["issuer_key"]] = st.issuer_used_cents.get(e["issuer_key"], 0) + e["amount_cents"] + e["fee_cents"]
    st.annual_used_cents = st.annual_funded_cents + st.active_reservation_cents
    return st


def check_commitment(state: BudgetState, issuer_key: str, total_cents: int) -> dict:
    annual_after = state.annual_used_cents + total_cents
    issuer_after = state.issuer_used_cents.get(issuer_key, 0) + total_cents
    ok_a, ok_i = annual_after <= state.annual_limit_cents, issuer_after <= state.issuer_limit_cents
    return {"annual_ok": ok_a, "issuer_ok": ok_i, "ok": ok_a and ok_i, "period": state.period_label,
            "annual_used_before": state.annual_used_cents, "annual_after": annual_after,
            "annual_limit": state.annual_limit_cents, "issuer_used_before": state.issuer_used_cents.get(issuer_key, 0),
            "issuer_after": issuer_after, "issuer_limit": state.issuer_limit_cents}


# ---- database access ----------------------------------------------------------------------------------
def events(ctx: Ctx) -> list[dict]:
    return [dict(r) for r in ctx.con.execute("SELECT * FROM ledger_events ORDER BY event_id")]


def approvals(ctx: Ctx) -> dict[int, dict]:
    return {r["approval_id"]: dict(r) for r in ctx.con.execute("SELECT * FROM approvals")}


def current_state(ctx: Ctx, as_of_utc: str | None = None, policy: dict | None = None) -> BudgetState:
    return budget_state(events(ctx), approvals(ctx), as_of_utc or ctx.now(), policy or load_budget_policy())


def issuer_key_for(ctx: Ctx, cik: str) -> tuple[str, bool]:
    r = ctx.con.execute("SELECT issuer_key, user_confirmed FROM issuer_groups WHERE member_cik=? ORDER BY row_id DESC LIMIT 1",
                        (cik,)).fetchone()
    return (r["issuer_key"], bool(r["user_confirmed"])) if r else (f"CIK{int(cik)}", False)


def confirm_issuer(ctx: Ctx, member_cik: str, issuer_key: str, basis: str) -> None:
    ctx.con.execute("INSERT INTO issuer_groups(member_cik, issuer_key, basis, user_confirmed, created_utc) VALUES (?,?,?,1,?)",
                    (member_cik, issuer_key, basis, ctx.now()))
    ctx.con.commit()


def acknowledge_policy(ctx: Ctx, kind: str, version: str, path: Path, statement: str) -> int:
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    cur = ctx.con.execute("INSERT INTO policy_acknowledgments(policy_kind, policy_version, policy_sha256, acknowledged_utc, "
                          "statement) VALUES (?,?,?,?,?)", (kind, version, sha, ctx.now(), statement))
    ctx.con.commit()
    return cur.lastrowid


def policy_acknowledged(ctx: Ctx, kind: str, version: str, path: Path) -> bool:
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    return bool(ctx.con.execute("SELECT 1 FROM policy_acknowledgments WHERE policy_kind=? AND policy_version=? AND "
                                "policy_sha256=?", (kind, version, sha)).fetchone())


def _insert_event(ctx: Ctx, **e) -> int:
    pol = load_budget_policy()
    cols = ["event_type", "approval_id", "position_id", "issuer_key", "offering_id", "security", "effective_date",
            "observed_utc", "amount_cents", "fee_cents", "currency", "quantity", "related_event_id", "document_id",
            "external_ref", "verification_status", "policy_flags", "note", "budget_policy_version"]
    e.setdefault("observed_utc", ctx.now())
    e.setdefault("budget_policy_version", pol["version"])
    e.setdefault("currency", "USD")
    e.setdefault("policy_flags", "")
    vals = [e.get(c, 0 if c in ("amount_cents", "fee_cents") else None) for c in cols]
    cur = ctx.con.execute(f"INSERT INTO ledger_events({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
    return cur.lastrowid


# ---- approvals ------------------------------------------------------------------------------------------
SCREENING_POLICY = POLICY_DIR / "screening_policy_v1.md"


def approve(ctx: Ctx, *, offering_id: str, amount_usd: str, fee_usd: str | None, fee_basis: str | None,
            issuer_key_confirmed: str, analysis_id: int | None, min_investment_usd: str | None,
            applicable_terms: str, availability_note: str, contract_document_id: int | None,
            override_rationale: str = "", expiry_days: int | None = None, supersedes: int | None = None,
            screening_policy_version: str = "screening_policy_v1") -> dict:
    """Record an explicit user approval. Only an 'executable' approval creates a budget reservation."""
    pol = load_budget_policy()
    now = ctx.now()
    o = ctx.con.execute("SELECT * FROM offerings WHERE offering_id=?", (offering_id,)).fetchone()
    if o is None:
        raise ValueError(f"unknown offering {offering_id}")
    amount = cents(amount_usd)
    checks, blockers = {}, []
    # 1. screening policy acknowledged before any live approval
    checks["screening_policy_acknowledged"] = policy_acknowledged(ctx, "screening", screening_policy_version, SCREENING_POLICY)
    if not checks["screening_policy_acknowledged"]:
        blockers.append("screening policy not acknowledged (run `ack-policy`)")
    # 2. issuer aggregation confirmed by the user
    key, confirmed = issuer_key_for(ctx, o["issuer_id"])
    checks["issuer_key"] = key
    checks["issuer_aggregation_confirmed"] = confirmed and key == issuer_key_confirmed
    if not checks["issuer_aggregation_confirmed"]:
        blockers.append(f"issuer aggregation not confirmed (stored key {key}, confirmed={confirmed}; run `confirm-issuer`)")
    # 3. analysis exists; failed/incomplete screens need an explicit override rationale
    a = ctx.con.execute("SELECT * FROM analysis_runs WHERE analysis_id=?", (analysis_id,)).fetchone() if analysis_id else None
    checks["ai_status"] = a["status"] if a else "no_analysis"
    failed = []
    if a is None or a["status"] != "passes_research_screen":
        failed = [dict(r) for r in ctx.con.execute("SELECT gate, result FROM analysis_gates WHERE analysis_id=? AND result!='pass'",
                                                   (analysis_id,))] if a else [{"gate": "analysis", "result": "missing"}]
        if not override_rationale.strip():
            blockers.append(f"AI screen is '{checks['ai_status']}': an explicit override rationale is required")
    # 4. material changes since the analysis evidence cutoff
    if a is not None:
        cutoff = ctx.con.execute("SELECT cutoff_utc FROM evidence_packs WHERE pack_id=?", (a["pack_id"],)).fetchone()[0]
        changed = ctx.con.execute(
            "SELECT event_type, accession FROM events WHERE offering_id=? AND observed_utc > ? AND event_type IN "
            "('offering_amendment_filed','offering_withdrawn_c_w','progress_update_filed')", (offering_id, cutoff)).fetchall()
        newdocs = ctx.con.execute("SELECT COUNT(*) FROM documents WHERE offering_id=? AND retrieved_utc > ? AND source_type IN "
                                  "('sec_primary_xml','sec_attachment','user_import') AND http_status=200",
                                  (offering_id, cutoff)).fetchone()[0]
        checks["material_changes_since_analysis"] = [dict(r) for r in changed]
        checks["new_documents_since_analysis"] = newdocs
        if changed or newdocs:
            blockers.append("new filings/documents since the analysis evidence cutoff: fresh review required")
        age = (parse_utc(now) - parse_utc(a["finished_utc"])).days
        checks["analysis_age_days"] = age
    # 5. availability: never assumed
    if o["availability_status"] in ("withdrawn", "closed_reported"):
        blockers.append(f"offering availability is '{o['availability_status']}'")
    if not availability_note.strip():
        blockers.append("user must state how availability was confirmed on the platform")
    # 6. minimum investment and applicable (tiered/early-bird) terms
    if not min_investment_usd:
        blockers.append("applicable minimum investment not confirmed")
    elif amount < cents(min_investment_usd):
        blockers.append(f"amount {usd(amount)} is below the confirmed minimum {usd(cents(min_investment_usd))}")
    if not applicable_terms.strip():
        blockers.append("applicable terms (security, cap/price, tier) not confirmed")
    if contract_document_id is None:
        blockers.append("contract version (document id) not specified")
    # 7. fees: confirmed amount or user-confirmed upper bound; otherwise incomplete
    incomplete = fee_usd is None or fee_basis not in ("confirmed", "upper_bound")
    fee = cents(fee_usd) if fee_usd is not None else None
    # 8. budget (both limits, all active reservations, fees included)
    state = current_state(ctx, now, pol)
    chk = check_commitment(state, key, amount + (fee or 0))
    checks["budget"] = chk
    if not chk["ok"]:
        blockers.append("budget limit would be exceeded (limits cannot be overridden at approval)")
    days = int(expiry_days or pol["reservations"]["default_expiry_days"])
    expires = parse_utc(now) + dt.timedelta(days=days)
    if o["deadline_date"]:
        expires = min(expires, dt.datetime.combine(dt.date.fromisoformat(o["deadline_date"]), dt.time(23, 59), NY))
    status = "blocked" if blockers else ("incomplete" if incomplete else "executable")
    checks["blockers"] = blockers
    cur = ctx.con.execute(
        """INSERT INTO approvals(offering_id, issuer_key, analysis_id, pack_sha256, contract_document_id, amount_cents, fee_cents,
           fee_basis, terms, availability_note, approved_utc, expires_utc, status, checks, ai_status_at_approval,
           override_failed_conditions, override_rationale, screening_policy_version, budget_policy_version,
           supersedes_approval_id, user_confirmed) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
        (offering_id, key, analysis_id, a["pack_sha256"] if a else None, contract_document_id, amount, fee, fee_basis,
         json.dumps({"applicable_terms": applicable_terms, "min_investment_cents": cents(min_investment_usd) if min_investment_usd else None}),
         availability_note, now, iso(expires), status, json.dumps(checks, default=str), checks["ai_status"],
         json.dumps(failed), override_rationale or None, screening_policy_version, pol["version"], supersedes))
    aid = cur.lastrowid
    if status == "executable":
        _insert_event(ctx, event_type="reservation_created", approval_id=aid, issuer_key=key, offering_id=offering_id,
                      effective_date=ny_date(now).isoformat(), amount_cents=amount, fee_cents=fee,
                      verification_status="user_approval", note=f"reservation for approval {aid}")
    ctx.con.commit()
    return {"approval_id": aid, "status": status, "expires_utc": iso(expires), "blockers": blockers, "budget": chk}


def release_reservation(ctx: Ctx, approval_id: int, reason: str) -> int:
    a = ctx.con.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
    eid = _insert_event(ctx, event_type="reservation_released", approval_id=approval_id, issuer_key=a["issuer_key"],
                        offering_id=a["offering_id"], effective_date=ny_date(ctx.now()).isoformat(),
                        verification_status="user_confirmed_cancellation", note=reason)
    ctx.con.commit()
    return eid


# ---- recording what actually happened ---------------------------------------------------------------
def record_event(ctx: Ctx, *, event_type: str, offering_id: str, effective_date: str, amount_usd: str = "0",
                 fee_usd: str = "0", approval_id: int | None = None, related_event_id: int | None = None,
                 external_ref: str | None = None, document_id: int | None = None, verification_status: str = "user_reported",
                 security: str | None = None, quantity: str | None = None, note: str = "") -> dict:
    """Record an actual event. Duplicates (same type + external reference) are not inserted twice.
    Out-of-policy facts are recorded truthfully and flagged; they are never rejected or 'adjusted'."""
    if external_ref:
        dup = ctx.con.execute("SELECT event_id FROM ledger_events WHERE event_type=? AND external_ref=?",
                              (event_type, external_ref)).fetchone()
        if dup:
            return {"event_id": dup[0], "duplicate": True, "flags": ""}
    o = ctx.con.execute("SELECT issuer_id FROM offerings WHERE offering_id=?", (offering_id,)).fetchone()
    key = issuer_key_for(ctx, o["issuer_id"])[0] if o else offering_id
    amount, fee = cents(amount_usd), cents(fee_usd)
    flags = []
    if event_type in FUNDING_TYPES | {"investor_fee_paid"}:
        pol = load_budget_policy()
        eff_utc = iso(dt.datetime.combine(dt.date.fromisoformat(effective_date), dt.time(12), NY))
        evs = [e for e in events(ctx) if not (e["event_type"] == "reservation_created" and e["approval_id"] == approval_id)]
        st = budget_state(evs, approvals(ctx), max(eff_utc, ctx.now()) if event_type in FUNDING_TYPES else ctx.now(), pol)
        chk = check_commitment(st, key, amount + fee)
        if not chk["annual_ok"]:
            flags.append("OUT_OF_POLICY:annual_limit")
        if not chk["issuer_ok"]:
            flags.append("OUT_OF_POLICY:issuer_limit")
        if event_type in FUNDING_TYPES:
            ap = ctx.con.execute("SELECT * FROM approvals WHERE approval_id=?", (approval_id,)).fetchone() if approval_id else None
            if ap is None:
                flags.append("NO_APPROVAL")
            else:
                if ap["status"] != "executable":
                    flags.append(f"APPROVAL_NOT_EXECUTABLE:{ap['status']}")
                if ap["expires_utc"] < eff_utc:
                    flags.append("APPROVAL_EXPIRED")
                if amount + fee > ap["amount_cents"] + (ap["fee_cents"] or 0):
                    flags.append("EXCEEDS_APPROVED_AMOUNT")
                if ap["offering_id"] != offering_id:
                    flags.append("DIFFERENT_OFFERING_THAN_APPROVED")
    pos = f"POS-{offering_id}-{security or 'security'}"
    eid = _insert_event(ctx, event_type=event_type, approval_id=approval_id, position_id=pos, issuer_key=key,
                        offering_id=offering_id, security=security, effective_date=effective_date, amount_cents=amount,
                        fee_cents=fee, quantity=quantity, related_event_id=related_event_id, document_id=document_id,
                        external_ref=external_ref, verification_status=verification_status, policy_flags=";".join(flags),
                        note=note)
    ctx.con.commit()
    return {"event_id": eid, "duplicate": False, "flags": ";".join(flags)}


def void_event(ctx: Ctx, event_id: int, reason: str) -> int:
    e = ctx.con.execute("SELECT * FROM ledger_events WHERE event_id=?", (event_id,)).fetchone()
    eid = _insert_event(ctx, event_type="correction_void", issuer_key=e["issuer_key"], offering_id=e["offering_id"],
                        effective_date=e["effective_date"], related_event_id=event_id, verification_status="user_correction",
                        note=reason)
    ctx.con.commit()
    return eid


def positions(ctx: Ctx) -> list[dict]:
    """Per position: funded cost, refunds, distributions, sale proceeds, latest holding; never mixes them."""
    ev = _live(events(ctx))
    out: dict[str, dict] = {}
    for e in ev:
        if not e["position_id"]:
            continue
        p = out.setdefault(e["position_id"], {"position_id": e["position_id"], "issuer_key": e["issuer_key"],
                                              "offering_id": e["offering_id"], "funded_cost_cents": 0, "refunds_cents": 0,
                                              "distributions_cents": 0, "sale_proceeds_net_cents": 0, "holding": "",
                                              "status": "", "flags": set(), "written_off_observed": False})
        t = e["event_type"]
        if t in FUNDING_TYPES:
            p["funded_cost_cents"] += e["amount_cents"] + e["fee_cents"]
            p["status"] = "submitted"
        elif t == "investor_fee_paid":
            p["funded_cost_cents"] += e["amount_cents"] + e["fee_cents"]
        elif t == "investment_finalized":
            p["status"] = "finalized"
        elif t == "investment_canceled":
            p["status"] = "canceled"
        elif t == "refund_verified":
            p["refunds_cents"] += e["amount_cents"] + e["fee_cents"]
            p["status"] = "refunded"
        elif t == "cash_distribution":
            p["distributions_cents"] += e["amount_cents"]
        elif t == "sale_proceeds":
            p["sale_proceeds_net_cents"] += e["amount_cents"]
        elif t == "sale_fee":
            p["sale_proceeds_net_cents"] -= e["fee_cents"] + e["amount_cents"]
        elif t in ("residual_holding_update", "security_conversion", "corporate_action"):
            p["holding"] = f"{e['quantity'] or ''} {e['security'] or ''} ({t} {e['effective_date']})".strip()
        elif t == "write_off_observed":
            p["written_off_observed"] = True
        if e["policy_flags"]:
            p["flags"].update(e["policy_flags"].split(";"))
    for p in out.values():
        p["flags"] = ";".join(sorted(f for f in p["flags"] if f))
        exited = p["holding"].startswith("0 ") or p["written_off_observed"] or p["status"] == "refunded"
        p["realized_multiple"] = (
            round((p["distributions_cents"] + p["sale_proceeds_net_cents"]) / (p["funded_cost_cents"] - p["refunds_cents"]), 4)
            if exited and p["funded_cost_cents"] - p["refunds_cents"] > 0 and p["status"] != "refunded" else None)
        p["realized_note"] = ("realized multiple: position documented as fully exited or written off" if p["realized_multiple"] is not None
                              else "not computed: position open, incomplete, or fully refunded (conversion is not cash)")
    return list(out.values())
