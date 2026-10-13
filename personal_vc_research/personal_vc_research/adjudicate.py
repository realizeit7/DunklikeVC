"""Apply docs/label_adjudication_rules.md to the 40-offering outcome pass.

Outputs (data/tables/):
  republic_holdings_claims_40.csv  one row per (offering, Republic holdings row) for associated/ambiguous rows
  outcome_fields_40.csv            evidence fields per offering (kept separate)
  outcome_labels_40.csv            strict label + sensitivity labels + conflicts per offering
"""
from __future__ import annotations

import re

import pandas as pd

from .config import Config
from .entity_match import norm
from .outcomes import _d, source_tier

LEGEND = {
    "*": "To Republic Crowd-Invest's knowledge the issuer is insolvent, dormant, or has dissolved and Republic Crowd-Invest does not expect to receive any cash proceeds as a result of its securities holdings.",
    "+": "Security has converted due to a qualifying equity financing, liquidity event or equivalent event for a digital asset security, but Republic Crowd-Invest has not realized cash proceeds from such conversion.",
}
INTERP = {
    "*": ("issuer_status_composite_and_holding_expectation",
          "Platform claim (composite): issuer insolvent OR dormant OR dissolved, to Republic's knowledge; Republic expects no cash from its holding. No component is selected."),
    "+": ("security_conversion_on_republic_holding",
          "Platform claim: Republic's commission security converted in a qualifying event; no cash realized by Republic. Not a business success/failure label."),
    "": ("listed_without_mark", "Holding listed without a status mark; no claim about the issuer's health."),
}


def footnote_text(legends: pd.DataFrame, as_of: str, n: str) -> str:
    """Verbatim text of numbered note `n` in the legend of the filing with this as-of date.

    2022 (Republic Note Form C): "6. Issuer conducted a tender offer ..." (rows carry superscript ⁶).
    2023+ (Republic Core C-AR): the text layer puts "(n)" mid-sentence: "<first line> (n) <rest>".
    """
    if not n:
        return ""
    t = legends[legends["holdings_as_of"] == as_of]["legend_text_verbatim"]
    if not len(t):
        return ""
    t = re.sub(r"\[page \d+\]", " ", t.iloc[0])
    t = re.sub(r"\s+", " ", t)
    m = re.search(rf"(?<![\d(]){n}\. (Issuer .*?)(?= \d+\. Issuer | \(1\) The dollar amount|$)", t)
    if m:
        return m.group(1).strip()
    m = re.search(rf"(The securities [^()]*?)\(\s*{n}\s*\)\s*([^()]*?)(?= The securities |\s*\(\d+\)|$)", t)
    if m:
        return re.sub(r"\s\d{2,3}$", "", (m.group(1).strip() + " " + m.group(2).strip()))
    return ""


def series_status(cc):
    out = []
    for sid, g in cc.groupby("series_id"):
        g = g.sort_values("holdings_as_of")
        yrs = [(r.holdings_as_of, r.mark, r.footnote_no) for r in g.itertuples()]
        star = [y for y, m, _ in yrs if "*" in m]
        plus = [y for y, m, _ in yrs if "+" in m]
        fns = [(y, f) for y, _, f in yrs if f]
        if star:
            first = star[0]
            prev = [y for y, m, _ in yrs if y < first and "*" not in m]
            interval = f"({prev[-1] if prev else 'unknown'}, {first}]"
        else:
            interval = ""
        disappeared = bool(star and any("*" not in m for y, m, _ in yrs if y > star[0])) or \
                      bool(plus and any("+" not in m for y, m, _ in yrs if y > plus[0]))
        out.append({"series": sid, "years": ";".join(y[:4] for y, _, _ in yrs), "star_first_as_of": star[0] if star else "",
                    "star_interval": interval, "plus_years": ";".join(p[:4] for p in plus),
                    "footnotes": ";".join(f"{y[:4]}:({f})" for y, f in fns), "mark_disappeared": disappeared,
                    "listed_last_as_of": yrs[-1][0]})
    return out



def decide_strict(withdrawn: bool, listed: bool, registry_dissolved: bool, ctr_b5: bool, indep_closure: bool,
                  conflicts: list, insolvency: bool, star_offering: bool, last_ops: str, n_ctr: int,
                  recent_from: str = "2024-10-10") -> tuple[str, str]:
    """Strict label in the pre-registered order (docs/label_adjudication_rules.md section C)."""
    if withdrawn:
        return "offering_withdrawn", "Form C-W; no completion report"
    if listed:
        return "listed_public", "424B4 + 8-A12B"
    if registry_dissolved:
        return "dissolved_or_liquidated_documented", "registry record"
    if ctr_b5:
        return "dissolved_or_liquidated_documented", "C-TR cites 227.202(b)(5)"
    if indep_closure:
        return "operational_closure_documented", "company announcement + independent report (legal dissolution not established)"
    if conflicts:
        return "unresolved", "conflicting sources"
    if insolvency:
        return "unresolved", "insolvency proceeding reported (not dissolution)"
    if star_offering:
        return "unresolved", "platform adverse claim only"
    if last_ops and last_ops >= recent_from:
        return "unresolved", "recent operating evidence only (not a terminal outcome)"
    if n_ctr:
        return "unresolved", "reporting terminated; no later dated evidence"
    return "unresolved", "no terminal evidence"


def build(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    td = cfg.path("tables_dir")
    off = pd.read_csv(td / "offerings_outcomes40.csv", dtype=str, keep_default_na=False)
    ev = pd.read_csv(td / "outcome_events_outcomes40.csv", dtype=str, keep_default_na=False)
    pay = pd.read_csv(td / "payout_evidence_outcomes40.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(cfg.path("manual_dir") / "entity_alias_review.csv", dtype=str, keep_default_na=False)
    h = pd.read_csv(td / "republic_holdings_rows.csv", dtype=str, keep_default_na=False)
    legends = pd.read_csv(td / "republic_holdings_legends.csv", dtype=str, keep_default_na=False)
    ui_p = td / "user_imports_public.csv"
    ui = pd.read_csv(ui_p, dtype=str, keep_default_na=False) if ui_p.exists() else pd.DataFrame()
    cutoff = cfg["study"]["outcome_cutoff_utc"]
    h["label_norm"] = h["listed_entity_label"].map(norm)
    h["cap_num"] = pd.to_numeric(h["capital_raised_usd"], errors="coerce").round(2)  # "714053" == "714053.00"

    # ---- claims table -------------------------------------------------------------------------
    claims = []
    for _, a in al[al["match_class"].isin(["exact", "corroborated_alias", "ambiguous"])].iterrows():
        ln, im = norm(a["listed_label"]), a["issuance_month"]
        seed = h[(h["label_norm"] == ln) & (h["issuance_month"] == im)]
        if not len(seed):
            continue
        cap = seed["cap_num"].iloc[0]
        series = h[(h["label_norm"] == ln) & (h["cap_num"] == cap)]  # same issuance across years
        months = sorted(series["issuance_month"].unique())
        for _, r in series.sort_values("holdings_as_of").iterrows():
            mk = r["marks"]
            cat, interp = INTERP.get(mk, ("other_mark", "unrecognized mark"))
            fn = r["footnote_no"]
            fnt = footnote_text(legends, r["holdings_as_of"], fn)
            if fn:
                cat, interp = ("disposal_of_republic_holding", "Platform claim: Republic's holding liquidated/repurchased as stated; proceeds to Republic Core (not retail).")
            unc = ["unaudited, internally prepared table (filer statement)", "holdings as-of date is not the event date"]
            if len(months) > 1:
                unc.append(f"issuance date differs across filings ({', '.join(months)})")
            if fn and r["holdings_as_of"] == "2022-12-31":
                unc.append("2022 note numbering (superscript, '1.'-'10.') is independent of the 2023+ '(n)' numbering")
            claims.append({
                "offering_id": a["offering_id"], "legal_name": a["legal_name"], "match_class": a["match_class"],
                "association_level": a["association_level"], "entity_match_evidence": a.get("review_note", ""),
                "accession": r["accession"], "filing_url": r["filing_url"], "page": r["page"], "row_text": r["raw_line"],
                "listed_entity": r["listed_entity_label"],
                "security_description": "not stated in table; filer narrative: commission securities 'in the same form and manner as the securities sold by such company'",
                "issuance_month": r["issuance_month"], "capital_raised_usd": r["capital_raised_usd"],
                "holdings_as_of": r["holdings_as_of"], "filing_public_date": r["filing_date"],
                "mark": mk, "footnote_no": fn, "legend_verbatim": LEGEND.get(mk, ""), "footnote_text_verbatim": fnt,
                "claim_category": cat, "interpretation": interp, "uncertainty": "; ".join(unc), "conflicts": "",
                "series_id": f"{a['offering_id']}|{ln}|{cap}"})
    C = pd.DataFrame(claims).drop_duplicates(subset=["offering_id", "accession", "page", "row_text"])

    # ---- per-offering fields + labels -----------------------------------------------------------
    F, L = [], []
    for _, o in off.iterrows():
        oid = o["offering_id"]
        e = ev[ev["offering_id"] == oid].copy()
        e["pub"] = e["publication_date"].map(_d)
        e = e[(e["pub"] <= cutoff) | (e["pub"] == "")]
        e["tier"] = e["evidence_strength"].map(source_tier)
        c = C[(C["offering_id"] == oid)]
        co = c[c["association_level"] == "offering"]
        ci = c[c["association_level"] == "issuer"]
        ops = e[e["event_type"].isin(["operating_activity_reported", "periodic_report_10k", "operating_activity_independent_report",
                                      "operating_activity_company_claim", "company_publication_latest"])]
        fin = e[e["event_type"].isin(["securities_offering_notice_form_d", "follow_on_reg_cf_offering_filed", "other_reg_cf_offering_progress_reported", "reg_a_offering_filed",
                                      "financing_independent_report"])]
        listed = {"ipo_prospectus_final", "exchange_registration_8a12b"} <= set(e["event_type"])
        ctr = e[e["event_type"] == "reporting_termination"]
        ctr_b5 = ctr["details"].str.contains(r"202\(b\)\(5\)", regex=True).any()
        closure = e[e["event_type"] == "operational_closure_announced"]
        insolv = e[e["event_type"] == "insolvency_proceeding_reported"]
        reg = ui[(ui["offering_id"] == oid) & (ui["evidence_type"].str.contains("registry", case=False))] if len(ui) else pd.DataFrame()

        so, si = series_status(co), series_status(ci)
        star_o = [s for s in so if s["star_first_as_of"]]
        star_i = [s for s in si if s["star_first_as_of"]]
        plus_o = [s for s in so if s["plus_years"]]
        fn_o = [s for s in so if s["footnotes"]]
        conflicts = []
        if star_o + star_i and listed:
            conflicts.append("platform '*' vs SEC listing/reporting evidence")
        if any(s["mark_disappeared"] for s in so + si):
            conflicts.append("platform mark disappears in later filing (instability; not a reversal)")
        if (e["attribution_level"] == "issuer_identity_uncertain").any():
            conflicts.append("external report names a differently-suffixed entity (identity uncertain)")
        amb = al[(al["offering_id"] == oid) & (al["match_class"] == "ambiguous")]
        last_sec = e[e["tier"] == "sec_issuer"]["pub"].max() if len(e[e["tier"] == "sec_issuer"]) else ""
        last_ext = e[e["tier"] == "external"]["pub"].max() if len(e[e["tier"] == "external"]) else ""
        # a holding listed WITHOUT a mark/note is not an observation of the issuer (rules section A)
        c_obs = c[(c["mark"] != "") | (c["footnote_no"] != "")]
        last_plat = c_obs["filing_public_date"].max() if len(c_obs) else ""
        last_any = max([x for x in (last_sec, last_ext, last_plat) if x], default="")
        last_ops = ops["pub"].max() if len(ops) else ""
        last_ops_tier = ops.sort_values("pub")["tier"].iloc[-1] if len(ops) else ""
        p = pay[pay["offering_id"] == oid]
        F.append({
            "offering_id": oid, "legal_name": o["issuer_legal_name_at_offering"], "cohort_year": o["cohort_year"],
            "issuer_cik": o["issuer_cik"], "completion_status": o["completion_status"],
            "legal_status": (reg["summary"].iloc[0] if len(reg) else "not_accessed (registries blocked; no user import)"),
            "last_operating_evidence_date": last_ops, "last_operating_evidence_tier": last_ops_tier,
            "last_observation_sec_issuer": last_sec, "last_observation_platform": last_plat, "last_observation_external": last_ext,
            "last_observation_any": last_any,
            "n_financing_events": len(fin), "last_financing_event": fin["pub"].max() if len(fin) else "",
            "acquisition_or_listing": "listed (424B4 + 8-A12B)" if listed else "none found",
            "reporting_terminations": len(ctr), "ctr_reason_202b5": bool(ctr_b5),
            "operational_closure_claims": "; ".join(closure["details"].str[:120]) if len(closure) else "",
            "insolvency_proceedings_reported": "; ".join(insolv["details"].str[:100]) if len(insolv) else "",
            "security_conversion_or_disposal": "; ".join(
                [f"issuer filing: {t}" for t in p["evidence_type"] if t.startswith("security_class")] +
                [f"platform '+' {s['plus_years']}" for s in plus_o] + [f"platform footnote {s['footnotes']}" for s in fn_o]),
            "investor_distributions": "; ".join(
                (["company-announced return of capital (unquantified)"] if (e["event_type"] == "investor_distribution_announced_company_claim").any() else []) +
                [f"platform claim ({r.holdings_as_of[:4]} note {r.footnote_no}): {r.footnote_text_verbatim[:110]} [retail participation/proceeds unknown]"
                 for r in co.itertuples() if re.match(r"Issuer (conducted a tender offer|elected to repurchase)", r.footnote_text_verbatim)])
                or "none recovered from accessible sources",
            "last_listed_platform_unmarked_or_marked": c["filing_public_date"].max() if len(c) else "",
            "platform_status_offering_level": "; ".join(f"* first as-of {s['star_first_as_of']} interval {s['star_interval']}" for s in star_o),
            "platform_status_issuer_level_only": "; ".join(f"* first as-of {s['star_first_as_of']}" for s in star_i),
            "republic_series_offering_level": len(so), "republic_series_issuer_level": len(si),
            "republic_rows_offering_level": len(co), "entity_match_best": (
                "offering_level" if len(co) else ("issuer_level_only" if len(ci) else ("ambiguous" if len(amb) else "unmatched"))),
            "conflicts": "; ".join(conflicts),
        })
        # strict label
        indep_closure = len(closure) and (closure["evidence_strength"] == "company_announcement_corroborated").any()
        strict, reason = decide_strict(
            o["completion_status"] == "withdrawn", listed,
            bool(len(reg) and reg["summary"].str.contains("dissolv|cancel|forfeit", case=False).any()),
            bool(ctr_b5), bool(indep_closure), conflicts, bool(len(insolv)), bool(star_o), last_ops, len(ctr))
        sens = []
        if star_o and not any("platform '*'" in c_ for c_ in conflicts):
            sens.append("platform_claim_insolvent_dormant_or_dissolved")
        if star_i and not star_o:
            sens.append("platform_claim_adverse_issuer_level_only")
        if plus_o:
            sens.append("platform_claim_converted_no_cash")
        if fn_o:
            sens.append("platform_claim_holding_disposed")
        if last_ops and last_ops >= "2024-10-10":
            sens.append("operating_claim_recent")
        if last_any and last_any < "2023-10-10":
            sens.append("unobserved_gt_3y")
        if len(insolv):
            sens.append("insolvency_proceeding_reported")
        if (e["event_type"] == "closure_claim_weak_aggregator").any():
            sens.append("closure_claim_weak")
        if conflicts:
            sens.append("conflicted")
        L.append({"offering_id": oid, "legal_name": o["issuer_legal_name_at_offering"], "cohort_year": o["cohort_year"],
                  "strict_label": strict, "strict_reason": reason, "sensitivity_labels": ";".join(sens),
                  "conflicts": "; ".join(conflicts),
                  "business_outcome_denominator": strict != "offering_withdrawn"})
    return C, pd.DataFrame(F), pd.DataFrame(L)


def cmd_adjudicate(cfg: Config, args) -> int:
    C, F, L = build(cfg)
    td = cfg.path("tables_dir")
    C.to_csv(td / "republic_holdings_claims_40.csv", index=False)
    F.to_csv(td / "outcome_fields_40.csv", index=False)
    L.to_csv(td / "outcome_labels_40.csv", index=False)
    print(f"claims rows={len(C)} offerings={len(F)}")
    print(L["strict_label"].value_counts().to_string())
    print(L["strict_reason"].value_counts().to_string())
    return 0
