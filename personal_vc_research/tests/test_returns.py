"""Return-calculation safeguards on SYNTHETIC cash flows (no real returns are computed here)."""
import datetime as dt

from personal_vc_research.returns import CashFlow, compute_return, xirr

D = dt.date


def test_no_flows_not_computable():
    assert compute_return([], position_closed=False).status == "not_computable"


def test_outstanding_position_is_not_zero_return():
    r = compute_return([CashFlow(D(2019, 1, 1), -100.0, "contribution", "syn1")], position_closed=False)
    assert r.status == "outstanding_unknown" and r.dpi is None


def test_acquisition_headline_without_payout_does_not_create_return():
    # an acquisition is a company event; with no distribution evidence the position stays unknown
    r = compute_return([CashFlow(D(2019, 1, 1), -100.0, "contribution", "syn1")], position_closed=False)
    assert r.status != "realized" and r.tvpi is None


def test_partial_distribution_is_partial():
    flows = [CashFlow(D(2019, 1, 1), -100.0, "contribution", "s1"),
             CashFlow(D(2021, 1, 1), 40.0, "distribution", "s2")]
    r = compute_return(flows, position_closed=False)
    assert r.status == "partial" and abs(r.dpi - 0.4) < 1e-12 and r.xirr is None
    assert r.fee_basis == "before_unknown_fees"


def test_realized_multiple_and_xirr():
    flows = [CashFlow(D(2019, 1, 1), -100.0, "contribution", "s1"),
             CashFlow(D(2020, 1, 1), 110.0, "distribution", "s2")]
    r = compute_return(flows, position_closed=True)
    assert r.status == "realized" and abs(r.dpi - 1.1) < 1e-12
    assert abs(r.xirr - 0.10) < 1e-3


def test_invalid_inputs_rejected():
    bad = [CashFlow(D(2019, 1, 1), 100.0, "contribution", "s1")]  # positive contribution
    assert compute_return(bad, position_closed=True).status == "not_computable"
    no_ev = [CashFlow(D(2019, 1, 1), -100.0, "contribution", "")]
    assert compute_return(no_ev, position_closed=True).status == "not_computable"
    only_dist = [CashFlow(D(2019, 1, 1), 50.0, "distribution", "s")]
    assert compute_return(only_dist, position_closed=True).status == "not_computable"


def test_residual_value_requires_evidence():
    flows = [CashFlow(D(2019, 1, 1), -100.0, "contribution", "s1"),
             CashFlow(D(2021, 1, 1), 40.0, "distribution", "s2")]
    r = compute_return(flows, position_closed=False, residual_value=500.0, residual_evidence_id=None)
    assert r.tvpi is None
    r2 = compute_return(flows, position_closed=False, residual_value=60.0, residual_evidence_id="s3")
    assert abs(r2.tvpi - 1.0) < 1e-12


def test_flows_after_as_of_are_ignored():
    flows = [CashFlow(D(2019, 1, 1), -100.0, "contribution", "s1"),
             CashFlow(D(2030, 1, 1), 300.0, "distribution", "s2")]
    r = compute_return(flows, position_closed=False, as_of=D(2026, 10, 10))
    assert r.status == "outstanding_unknown"


def test_xirr_no_sign_change():
    assert xirr([(D(2019, 1, 1), -1.0), (D(2020, 1, 1), -1.0)]) is None
