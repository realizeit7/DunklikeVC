"""Typed calculation requests (v2.2.1). The model selects an ALLOWLISTED kind and the cited input facts; this module
owns the equation, units, arithmetic and rendering. Nothing the model writes is evaluated, parsed as code or eval'd.

Every input carries a role, a value, a unit, a claim id, an as-of date and (for shares and prices) a security class.
Checks before any arithmetic:
* the value must appear in the cited claim's text or quotes (commas ignored): the request cannot introduce numbers;
* each role has the right unit;
* price and share classes match on the base class;
* runway needs period-aligned cash and spending;
* a planned instrument is never an issued share count or debt.

The result is computed with Decimal, or withheld with a reason. Legacy free-form formulas (v3_0 outputs) are handled
only by `normalize_legacy_formula`, which strips a recognised display label such as "K1:" when the remainder already
parses under the legacy grammar, logs the original and the normalized text, and never changes numbers, signs,
operators or operands.
"""
from __future__ import annotations

import ast
import datetime as dt
import re
from decimal import Decimal, InvalidOperation

TYPED_CALC_VERSION = "typed_calc_v1"
KINDS = {
    "implied_equity": {"price": "USD_per_share", "shares_outstanding": "shares"},
    "post_money": {"price": "USD_per_share", "shares_outstanding": "shares", "shares_offered": "shares"},
    "ownership_percent": {"holder_shares": "shares", "total_shares": "shares"},
    "runway_months": {"cash": "USD", "spending": "USD"},
    "ref": {},   # cite an existing software calculation (K id); no arithmetic
}


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v).replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"not a number: {v!r}") from exc


def _numbers_in(claim: dict) -> set[Decimal]:
    txt = claim.get("claim_text", "") + " " + " ".join(c.get("quote", "") for c in claim.get("citations", []))
    out = set()
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", txt):
        try:
            out.add(Decimal(m.replace(",", "")))
        except InvalidOperation:
            pass
    return out


def _base(cls: str) -> str:
    return re.sub(r"\(.*?\)", "", cls or "").replace("shares", "").replace("stock", "").strip().lower()


def compute(req: dict, claims: dict, calcs: dict | None = None, planned_claim_ids: set | None = None) -> dict:
    """Returns {kind, result_kind: computed|withheld|reference, result_value (str), units, inputs, withheld_reason,
    version}. Validation problems are returned as `errors` (they make the stage invalid)."""
    kind = req.get("kind")
    out = {"kind": kind, "version": TYPED_CALC_VERSION, "inputs": req.get("inputs", []), "errors": [], "withheld_reason": "",
           "result_value": None, "units": ""}
    if kind not in KINDS:
        out["errors"].append(f"calculation kind {kind!r} is not allowlisted")
        return out
    if kind == "ref":
        k = (calcs or {}).get(req.get("k_ref", ""))
        if not k:
            out["errors"].append(f"ref to unknown software calculation {req.get('k_ref')!r}")
        else:
            out.update(result_kind="reference", result_value=None if k.get("result_value") is None else str(k["result_value"]),
                       units=k.get("units", ""), withheld_reason=k.get("withheld_reason", ""))
        return out
    need = KINDS[kind]
    by_role = {}
    for i in req.get("inputs", []):
        role = i.get("role")
        if role not in need:
            out["errors"].append(f"{kind}: unexpected input role {role!r}")
            continue
        if i.get("unit") != need[role]:
            out["errors"].append(f"{kind}: {role} must be in {need[role]}, got {i.get('unit')!r}")
            continue
        c = claims.get(i.get("claim_id"))
        if c is None:
            out["errors"].append(f"{kind}: {role} cites unknown claim {i.get('claim_id')!r}")
            continue
        try:
            val = _dec(i.get("value"))
        except ValueError as exc:
            out["errors"].append(f"{kind}: {role}: {exc}")
            continue
        if val not in _numbers_in(c) and abs(val) not in _numbers_in(c):
            out["errors"].append(f"{kind}: {role} value {i.get('value')} does not appear in claim {i['claim_id']}")
            continue
        if planned_claim_ids and i["claim_id"] in planned_claim_ids and role in ("shares_outstanding", "holder_shares", "total_shares"):
            out["errors"].append(f"{kind}: {role} uses a PLANNED instrument (claim {i['claim_id']}); planned is not issued")
            continue
        by_role[role] = {**i, "_v": val}
    missing = [r for r in need if r not in by_role]
    if out["errors"]:
        return out
    if missing:
        out.update(result_kind="withheld", withheld_reason="missing inputs: " + ", ".join(missing))
        return out
    if kind in ("implied_equity", "post_money"):
        p, s = by_role["price"], by_role["shares_outstanding"]
        classes = {_base(x.get("security_class", "")) for x in by_role.values() if x.get("security_class")}
        if len(classes) > 1:
            out["errors"].append(f"{kind}: security classes differ {sorted(classes)}")
            return out
        shares = s["_v"] + (by_role["shares_offered"]["_v"] if kind == "post_money" else 0)
        out.update(result_kind="computed", result_value=str(p["_v"] * shares), units="USD",
                   assumptions=["arithmetic on the offering price; not a valuation opinion",
                                f"shares as of {s.get('as_of') or 'undated'}"])
    elif kind == "ownership_percent":
        h, t = by_role["holder_shares"]["_v"], by_role["total_shares"]["_v"]
        if t <= 0 or h > t:
            out["errors"].append("ownership_percent: holder shares must be positive and not exceed total shares")
            return out
        out.update(result_kind="computed", result_value=str((h / t * 100).quantize(Decimal("0.0001"))), units="percent")
    elif kind == "runway_months":
        cash, sp = by_role["cash"], by_role["spending"]
        try:
            cd = dt.date.fromisoformat(cash["as_of"])
            ps, pe = dt.date.fromisoformat(sp["period_start"]), dt.date.fromisoformat(sp["period_end"])
        except (KeyError, TypeError, ValueError):
            out.update(result_kind="withheld", withheld_reason="runway needs a dated cash figure and a dated spending period")
            return out
        if not (0 <= (cd - pe).days <= 92) or (pe - ps).days < 28:
            out.update(result_kind="withheld", withheld_reason=f"spending period {ps}..{pe} is not aligned with cash dated {cd}; "
                                                               "no current runway from stale spending")
            return out
        monthly = abs(sp["_v"]) / (Decimal((pe - ps).days) / Decimal("30.4375"))
        out.update(result_kind="computed", result_value=str((cash["_v"] / monthly).quantize(Decimal("0.1"))), units="months",
                   assumptions=[f"runway at {cd}, not a current runway"])
    return out


# ---- legacy (v3_0) free-form formulas: cosmetic normalisation only --------------------------------------------------
_LABEL = re.compile(r"^\s*(K\d{1,2})\s*:\s*")
_OK_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant, ast.Load, ast.Add, ast.Sub, ast.Mult, ast.Div,
             ast.USub, ast.UAdd)


def _parses(expr: str) -> bool:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return False
    return all(isinstance(n, _OK_NODES) for n in ast.walk(tree))


def normalize_legacy_formula(formula: str) -> dict:
    """Strip a leading display label (e.g. 'K1:') and surrounding whitespace ONLY if the remainder already parses under
    the legacy grammar. Returns {ok, original, normalized, label, log}; ok=False means 'reject, do not guess'."""
    m = _LABEL.match(formula or "")
    if not m:
        return {"ok": _parses((formula or "").strip()), "original": formula, "normalized": (formula or "").strip(), "label": None,
                "log": "no label; whitespace trimmed only" if _parses((formula or "").strip()) else "unparseable; rejected"}
    rest = formula[m.end():].strip()
    if not _parses(rest):
        return {"ok": False, "original": formula, "normalized": None, "label": m.group(1), "log": "label stripped but remainder does not parse; rejected"}
    return {"ok": True, "original": formula, "normalized": rest, "label": m.group(1), "log": f"display label '{m.group(1)}:' removed"}
