"""Deterministic valuation arithmetic (calculator_v1). The model extracts cited inputs; the arithmetic is done here.

Rules
* Every result keeps its formula, inputs (value, unit, as-of date, source claim id and citation), assumptions,
  included and excluded instruments.
* Implied equity value uses ISSUED/OUTSTANDING shares, never authorized shares. Authorized shares are listed as
  excluded with the reason.
* Pre-money = price x issued shares. Post-money is given at the offering minimum and maximum.
* Fully diluted value is WITHHELD when any convertible instrument's conversion terms are undisclosed: convertibles are
  never silently included or ignored.
* If inputs conflict (different issued counts from different sources/dates) the result is labelled `illustrative`
  and the conflict is stated. If an input is missing the result is `withheld`.
* An implied value is arithmetic, not an opinion that the price is too high. "Arbitrary price" is a disclosure, not
  proof of overvaluation. No comparables are used or invented.
"""
from __future__ import annotations

CALCULATOR_VERSION = "calculator_v1_3"
# v1_3 (2026-10-17, Hope-Neuron run 15/16): (a) on one date, a Form C capitalization-table total is preferred over a
# component count (75,000,000 ratified to the founder vs 75,000,001 total), so this is no longer called a conflict;
# (b) share classes compare on the base class name, so 'Common (total incl. ...)' and 'Common' are the same class.
# v1_2 (2026-10-17, v2.2): issued counts dated differently are history, not a conflict (e.g. 1 share on the audited
# 2025-12-31 balance sheet vs 75,000,001 after a 2026 ratification). The latest-dated count is used and the earlier one
# is shown. Only counts with the same date and different values are 'illustrative'. Planned (not yet issued)
# convertibles are listed apart and never block or enter the fully diluted figure. Also new: runway() and
# investor_proceeds(), which withhold unless their inputs truly exist.
# v1_1 (2026-10-15, analysis 12): no per-share implied equity for SAFEs or convertible notes. The "price" there is a
# purchase unit ($1.00), not a share price, and v1 multiplied it by common shares ($1,000,000 "equity" for
# Mightylicious). For such securities the valuation cap is a contract term and is not converted into an equity value.
# Also withheld: offered units of a different class than the issued shares.
NON_SHARE_SECURITIES = {"safe", "convertible_note"}


def _base_class(cls: str) -> str:
    import re
    return re.sub(r"\(.*?\)", "", cls or "").replace("shares", "").replace("stock", "").strip().lower()


def _cit(claims: dict, cid: str) -> list:
    c = claims.get(cid)
    return [{"doc_id": x["doc_id"], "page": x["page"]} for x in (c or {}).get("citations", [])]


def _inp(name, value, unit, as_of, cid, claims):
    return {"name": name, "value": value, "unit": unit, "as_of": as_of, "claim_id": cid, "citations": _cit(claims, cid)}


def implied_equity(valuation_inputs: dict, claims: dict, valid_claim_ids: set, security_class: str = "") -> list[dict]:
    """Returns calculation records K1.. (pre-money, post-money min/max, fully diluted)."""
    vi = valuation_inputs or {}
    out: list[dict] = []
    price = vi.get("price_per_share_usd")
    pcid = vi.get("price_claim_id", "")
    counts = vi.get("share_counts") or []
    usable = [c for c in counts if c["claim_id"] in valid_claim_ids]
    issued = [c for c in usable if c["kind"] == "issued_outstanding"]
    authorized = [c for c in usable if c["kind"] == "authorized"]
    omin = next((c for c in usable if c["kind"] == "offered_minimum"), None)
    omax = next((c for c in usable if c["kind"] == "offered_maximum"), None)
    convs = vi.get("convertible_instruments") or []
    unverified = [c["claim_id"] for c in counts if c["claim_id"] not in valid_claim_ids]
    excluded = [{"instrument": f"authorized shares ({a['share_class']}): {a['value']:,.0f}",
                 "reason": "authorized but unissued shares are not outstanding equity"} for a in authorized]
    excluded += [{"instrument": f"share count from claim {u}", "reason": "claim has no valid citation"} for u in unverified]
    planned = [c for c in convs if c.get("status") == "planned"]
    convs = [c for c in convs if c.get("status", "existing") != "planned"]
    excluded += [{"instrument": f"{c['instrument']} (planned, not issued as of {c.get('as_of') or 'the filing'})",
                  "reason": "planned instrument: not outstanding; listed, not counted"} for c in planned]
    base_assumptions = ["single price applies to all issued shares of the classes counted",
                        "implied value is arithmetic on the offering price, not a valuation opinion"]

    def rec(kind, formula, inputs, value, result_kind, withheld="", assumptions=None, included=None, excl=None):
        out.append({"calc_id": f"K{len(out) + 1}", "calc_type": kind, "formula": formula, "inputs": inputs, "units": "USD",
                    "result_value": value, "result_kind": result_kind, "withheld_reason": withheld,
                    "assumptions": (assumptions or []) + base_assumptions, "included_instruments": included or [],
                    "excluded_instruments": excl if excl is not None else excluded, "calculator_version": CALCULATOR_VERSION})

    if security_class in NON_SHARE_SECURITIES:
        rec("implied_pre_money_equity", "price_per_share * issued_shares", [], None, "withheld",
            f"security is a {security_class}: the offering price is a purchase unit, not a share price; the valuation cap "
            "is a contract term (see the contract claims), not a computed equity value")
        return out
    if price is None or pcid not in valid_claim_ids:
        rec("implied_pre_money_equity", "price_per_share * issued_shares", [], None, "withheld",
            "price per share missing or not supported by a valid citation")
        return out
    p_in = _inp("price_per_share", price, "USD/share", "", pcid, claims)
    if not issued:
        rec("implied_pre_money_equity", "price_per_share * issued_shares", [p_in], None, "withheld",
            "no cited issued/outstanding share count (authorized shares are never used)")
        return out
    latest = sorted(issued, key=lambda c: c.get("as_of") or "")[-1]
    same_date = [c for c in issued if (c.get("as_of") or "") == (latest.get("as_of") or "")]
    cap_table = [c for c in same_date if c.get("basis") == "form_c_capitalization_table"]
    if len({c["value"] for c in same_date}) > 1 and len({c["value"] for c in cap_table}) == 1:
        latest = cap_table[0]                       # the capitalization-table total; the others are components
        same_date = cap_table
    conflict = len({c["value"] for c in same_date}) > 1 or (not latest.get("as_of") and len({c["value"] for c in issued}) > 1)
    history = [c for c in issued if c is not latest and c not in same_date]
    kind = "illustrative" if conflict else "computed"
    history_note = [f"earlier issued count {c['value']:,.0f} ({c['share_class']}, as of {c['as_of'] or 'undated'}, "
                    f"{c.get('basis', 'basis not stated')}, claim {c['claim_id']}) is historical; the count effective "
                    f"{latest.get('as_of') or 'undated'} is used" for c in history]
    conflict_note = ([f"conflicting issued share counts in the pack: " +
                      "; ".join(f"{c['value']:,.0f} ({c['share_class']}, as of {c['as_of'] or 'undated'}, claim {c['claim_id']})"
                                for c in issued) + f". Using the latest-dated count {latest['value']:,.0f}."]
                     if conflict else [])
    s_in = _inp("issued_shares", latest["value"], "shares", latest.get("as_of", ""), latest["claim_id"], claims)
    included = [f"issued/outstanding {latest['share_class']} shares as of {latest.get('as_of') or 'undated'}"]
    pre = price * latest["value"]
    rec("implied_pre_money_equity", "price_per_share * issued_shares", [p_in, s_in], round(pre, 2), kind,
        assumptions=conflict_note + history_note, included=included)
    for label, o in (("minimum", omin), ("maximum", omax)):
        if o is not None and _base_class(o["share_class"]) != _base_class(latest["share_class"]):
            rec(f"implied_post_money_equity_at_offering_{label}", "price_per_share * (issued_shares + offered_shares)",
                [p_in, s_in], None, "withheld", f"offered class '{o['share_class']}' differs from issued class "
                f"'{latest['share_class']}'; units are not additive")
            continue
        if o is None:
            rec(f"implied_post_money_equity_at_offering_{label}", "price_per_share * (issued_shares + offered_shares)",
                [p_in, s_in], None, "withheld", f"offered {label} share count not cited")
            continue
        o_in = _inp(f"offered_shares_{label}", o["value"], "shares", o.get("as_of", ""), o["claim_id"], claims)
        rec(f"implied_post_money_equity_at_offering_{label}", "price_per_share * (issued_shares + offered_shares)",
            [p_in, s_in, o_in], round(price * (latest["value"] + o["value"]), 2), kind, assumptions=conflict_note,
            included=included + [f"offered shares at the {label}"])
    unknown_conv = [c for c in convs if not c["conversion_terms_disclosed"]]
    conv_desc = [f"{c['instrument']} (principal {('$' + format(c['principal_usd'], ',.0f')) if c['principal_usd'] is not None else 'unknown'})"
                 for c in convs]
    if unknown_conv:
        rec("implied_fully_diluted_equity", "price_per_share * (issued + offered + converted + reserved)", [p_in, s_in], None,
            "withheld", "conversion terms undisclosed for: " + "; ".join(conv_desc[i] for i, c in enumerate(convs)
                                                                       if not c["conversion_terms_disclosed"]),
            included=included, excl=excluded + [{"instrument": d, "reason": "listed; terms undisclosed, so neither included nor ignored"}
                                                for d in conv_desc])
    elif convs:
        rec("implied_fully_diluted_equity", "price_per_share * (issued + offered + converted + reserved)", [p_in, s_in], None,
            "withheld", "conversion share counts are not extracted as numbers; compute manually from the cited terms",
            included=included, excl=excluded + [{"instrument": d, "reason": "terms disclosed but share count not computed"} for d in conv_desc])
    return out


def runway(cash_points: list[dict], spending_points: list[dict], valid_claim_ids: set, max_gap_days: int = 92) -> dict:
    """Months of cash at the latest cash date. Computed ONLY if a spending figure covers a period ending within
    `max_gap_days` before that cash date. Otherwise withheld: stale spending never silently yields a current runway."""
    import datetime as dt
    cps = sorted([c for c in cash_points if c["claim_id"] in valid_claim_ids], key=lambda c: c["as_of"])
    if not cps:
        return {"calc_type": "runway_months", "result_kind": "withheld", "result_value": None, "units": "months",
                "withheld_reason": "no cited cash figure", "inputs": [], "calculator_version": CALCULATOR_VERSION}
    cash = cps[-1]
    cd = dt.date.fromisoformat(cash["as_of"])
    usable = []
    for s in spending_points:
        if s["claim_id"] not in valid_claim_ids or s["kind"] == "issuer_stated_monthly_burn":
            continue
        pe = dt.date.fromisoformat(s["period_end"])
        ps = dt.date.fromisoformat(s["period_start"]) if s.get("period_start") else None
        if ps and 0 <= (cd - pe).days <= max_gap_days and (pe - ps).days > 27:
            usable.append((s, (pe - ps).days / 30.4375))
    base = {"calc_type": "runway_months", "units": "months", "calculator_version": CALCULATOR_VERSION,
            "inputs": [{"name": "cash", "value": cash["amount_usd"], "as_of": cash["as_of"], "assurance": cash["assurance"],
                        "claim_id": cash["claim_id"]}]}
    if not usable:
        stale = [f"{s['kind']} {s['amount_usd']:,.0f} for period ending {s['period_end']}" for s in spending_points]
        return {**base, "result_kind": "withheld", "result_value": None,
                "withheld_reason": (f"no spending figure for a period ending within {max_gap_days} days before the latest cash "
                                    f"date {cash['as_of']}; available spending is stale ({'; '.join(stale) or 'none'}). "
                                    "A current runway is not computed. An issuer-stated runway is an issuer claim, not a calculation.")}
    s, months = usable[-1]
    monthly = abs(s["amount_usd"]) / months
    return {**base, "result_kind": "computed" if cash["assurance"] != "unaudited_issuer_statement" else "illustrative",
            "result_value": round(cash["amount_usd"] / monthly, 1) if monthly else None,
            "inputs": base["inputs"] + [{"name": "monthly_spend", "value": round(monthly, 2), "period_end": s["period_end"],
                                         "claim_id": s["claim_id"]}],
            "withheld_reason": "", "as_of": cash["as_of"],
            "assumptions": ["spending continues at the same-period average rate",
                            f"runway measured at the cash date {cash['as_of']}; it is NOT a current runway"]}


def investor_proceeds(security_class: str, inputs: dict) -> dict:
    """Never assumes an exit value, probability, timing or return. Returns 'withheld' plus the missing inputs unless the
    caller supplies every required input explicitly as a labelled scenario."""
    required = ["exit_equity_value_usd_assumption", "holding_period_years_assumption", "investor_ownership_at_exit",
                "senior_claims_at_exit_usd", "conversion_terms_or_share_count", "investor_fees_usd"]
    missing = [k for k in required if inputs.get(k) is None]
    if missing:
        return {"calc_type": "investor_cash_proceeds_scenario", "result_kind": "withheld", "result_value": None, "units": "USD",
                "withheld_reason": "inputs not established: " + ", ".join(missing),
                "note": "company value is not investor cash; no exit value, probability or return is assumed",
                "calculator_version": CALCULATOR_VERSION}
    gross = max(0.0, inputs["exit_equity_value_usd_assumption"] - inputs["senior_claims_at_exit_usd"]) * inputs["investor_ownership_at_exit"]
    return {"calc_type": "investor_cash_proceeds_scenario", "result_kind": "illustrative",
            "result_value": round(gross - inputs["investor_fees_usd"], 2), "units": "USD",
            "assumptions": [f"{k} = {v} (ASSUMPTION)" for k, v in inputs.items() if k.endswith("assumption")],
            "holding_period_years": inputs["holding_period_years_assumption"], "withheld_reason": "",
            "calculator_version": CALCULATOR_VERSION}
