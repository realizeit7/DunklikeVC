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

CALCULATOR_VERSION = "calculator_v1"


def _cit(claims: dict, cid: str) -> list:
    c = claims.get(cid)
    return [{"doc_id": x["doc_id"], "page": x["page"]} for x in (c or {}).get("citations", [])]


def _inp(name, value, unit, as_of, cid, claims):
    return {"name": name, "value": value, "unit": unit, "as_of": as_of, "claim_id": cid, "citations": _cit(claims, cid)}


def implied_equity(valuation_inputs: dict, claims: dict, valid_claim_ids: set) -> list[dict]:
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
    base_assumptions = ["single price applies to all issued shares of the classes counted",
                        "implied value is arithmetic on the offering price, not a valuation opinion"]

    def rec(kind, formula, inputs, value, result_kind, withheld="", assumptions=None, included=None, excl=None):
        out.append({"calc_id": f"K{len(out) + 1}", "calc_type": kind, "formula": formula, "inputs": inputs, "units": "USD",
                    "result_value": value, "result_kind": result_kind, "withheld_reason": withheld,
                    "assumptions": (assumptions or []) + base_assumptions, "included_instruments": included or [],
                    "excluded_instruments": excl if excl is not None else excluded, "calculator_version": CALCULATOR_VERSION})

    if price is None or pcid not in valid_claim_ids:
        rec("implied_pre_money_equity", "price_per_share * issued_shares", [], None, "withheld",
            "price per share missing or not supported by a valid citation")
        return out
    p_in = _inp("price_per_share", price, "USD/share", "", pcid, claims)
    if not issued:
        rec("implied_pre_money_equity", "price_per_share * issued_shares", [p_in], None, "withheld",
            "no cited issued/outstanding share count (authorized shares are never used)")
        return out
    distinct = sorted({c["value"] for c in issued})
    latest = sorted(issued, key=lambda c: c.get("as_of") or "")[-1]
    conflict = len(distinct) > 1
    kind = "illustrative" if conflict else "computed"
    conflict_note = ([f"conflicting issued share counts in the pack: " +
                      "; ".join(f"{c['value']:,.0f} ({c['share_class']}, as of {c['as_of'] or 'undated'}, claim {c['claim_id']})"
                                for c in issued) + f". Using the latest-dated count {latest['value']:,.0f}."]
                     if conflict else [])
    s_in = _inp("issued_shares", latest["value"], "shares", latest.get("as_of", ""), latest["claim_id"], claims)
    included = [f"issued/outstanding {latest['share_class']} shares as of {latest.get('as_of') or 'undated'}"]
    pre = price * latest["value"]
    rec("implied_pre_money_equity", "price_per_share * issued_shares", [p_in, s_in], round(pre, 2), kind,
        assumptions=conflict_note, included=included)
    for label, o in (("minimum", omin), ("maximum", omax)):
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
