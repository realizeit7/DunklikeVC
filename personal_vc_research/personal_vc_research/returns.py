"""Return calculations from *documented* investor cash flows only.

Nothing here infers cash flows from valuations, follow-on rounds, acquisition headlines or
platform marks. Callers pass dated contribution/distribution records that each carry evidence.
Results always state their completeness (`realized`, `partial`, `not_computable`) and fee basis.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


class InvalidCashFlows(ValueError):
    pass


@dataclass(frozen=True)
class CashFlow:
    date: dt.date
    amount: float          # negative = contribution (paid-in), positive = distribution
    kind: str              # "contribution" | "distribution" | "fee"
    evidence_id: str       # source_id of documenting evidence; required


@dataclass
class ReturnResult:
    status: str                       # realized | partial | not_computable
    paid_in: float | None = None
    distributed: float | None = None
    dpi: float | None = None          # distributed / paid-in
    tvpi: float | None = None         # (distributed + supported residual) / paid-in
    xirr: float | None = None
    fee_basis: str = "before_unknown_fees"
    notes: list[str] = field(default_factory=list)


def validate(flows: list[CashFlow]) -> None:
    if not flows:
        raise InvalidCashFlows("no cash flows")
    for f in flows:
        if not isinstance(f.date, dt.date):
            raise InvalidCashFlows(f"bad date {f.date!r}")
        if f.amount != f.amount or f.amount in (float("inf"), float("-inf")):
            raise InvalidCashFlows("non-finite amount")
        if not f.evidence_id:
            raise InvalidCashFlows("cash flow without evidence_id")
        if f.kind == "contribution" and f.amount >= 0:
            raise InvalidCashFlows("contributions must be negative")
        if f.kind == "distribution" and f.amount < 0:
            raise InvalidCashFlows("distributions must be non-negative")
        if f.kind not in ("contribution", "distribution", "fee"):
            raise InvalidCashFlows(f"unknown kind {f.kind!r}")
    if not any(f.kind == "contribution" for f in flows):
        raise InvalidCashFlows("no contribution: investment basis not traced")


def xirr(flows: list[tuple[dt.date, float]], lo: float = -0.9999, hi: float = 100.0, tol: float = 1e-9) -> float | None:
    """Annualised IRR by bisection on actual/365 day counts; None if no sign change."""
    if not flows:
        return None
    t0 = min(d for d, _ in flows)

    def npv(r: float) -> float:
        return sum(a / (1.0 + r) ** ((d - t0).days / 365.0) for d, a in flows)

    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo == 0:
        return lo
    if f_lo * f_hi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def compute_return(flows: list[CashFlow], position_closed: bool, residual_value: float | None = None,
                   residual_evidence_id: str | None = None, fees_documented: bool = False,
                   as_of: dt.date | None = None) -> ReturnResult:
    """Compute DPI/TVPI/XIRR from documented flows.

    position_closed: True only if evidence shows no remaining claim (e.g. full cash-out/buyback).
    residual_value: independently supportable value of remaining holdings (requires evidence id).
    """
    try:
        validate(flows)
    except InvalidCashFlows as exc:
        return ReturnResult(status="not_computable", notes=[str(exc)])
    if as_of is not None:
        flows = [f for f in flows if f.date <= as_of]
    paid_in = -sum(f.amount for f in flows if f.kind == "contribution")
    fees = -sum(f.amount for f in flows if f.kind == "fee")
    dist = sum(f.amount for f in flows if f.kind == "distribution")
    res = ReturnResult(status="partial", paid_in=paid_in, distributed=dist)
    res.fee_basis = "net_of_documented_fees" if fees_documented else "before_unknown_fees"
    basis = paid_in + (fees if fees_documented else 0.0)
    res.dpi = dist / basis if basis > 0 else None
    if residual_value is not None:
        if not residual_evidence_id:
            res.notes.append("residual value ignored: no independent evidence")
        else:
            res.tvpi = (dist + residual_value) / basis if basis > 0 else None
    if position_closed:
        res.status = "realized"
        res.tvpi = res.dpi
        res.xirr = xirr([(f.date, f.amount) for f in flows])
    else:
        res.notes.append("position not closed: DPI is a partial realized multiple, not a total return")
    return res
