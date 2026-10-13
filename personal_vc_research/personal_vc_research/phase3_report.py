"""Phase-3 deliverable tables (outcome coverage and label validation) -> reports/phase3_tables/*.csv + .md.

Every count carries its denominator. No single "resolved %" headline is computed on purpose.
"""
from __future__ import annotations

import pandas as pd

from .config import Config

RECENT3 = "2023-10-10"   # cutoff - 3 years
RECENT2 = "2024-10-10"   # cutoff - 2 years


def _md(df: pd.DataFrame) -> str:
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |")
    return "\n".join(lines)


def build_tables(cfg: Config) -> dict[str, pd.DataFrame]:
    td, md = cfg.path("tables_dir"), cfg.path("manual_dir")
    off = pd.read_csv(td / "offerings_outcomes40.csv", dtype=str, keep_default_na=False)
    F = pd.read_csv(td / "outcome_fields_40.csv", dtype=str, keep_default_na=False)
    L = pd.read_csv(td / "outcome_labels_40.csv", dtype=str, keep_default_na=False)
    C = pd.read_csv(td / "republic_holdings_claims_40.csv", dtype=str, keep_default_na=False)
    ev = pd.read_csv(td / "outcome_events_outcomes40.csv", dtype=str, keep_default_na=False)
    al = pd.read_csv(md / "entity_alias_review.csv", dtype=str, keep_default_na=False)
    pilot = pd.read_csv(td / "offerings_pilot.csv", dtype=str, keep_default_na=False)
    sample = pd.read_csv(cfg.path("sample_dir") / "frozen_sample.csv", dtype=str, keep_default_na=False)
    web = pd.read_csv(td / "website_checks_35.csv", dtype=str, keep_default_na=False)
    X = F.merge(L[["offering_id", "strict_label", "strict_reason", "sensitivity_labels"]], on="offering_id")
    X["pilot"] = X["offering_id"].isin(pilot["offering_id"])
    n, nc = len(X), int((X["completion_status"] != "withdrawn").sum())
    T = {}

    # 1. coverage before/after ------------------------------------------------------------------
    ev_post = ev[ev["event_type"].isin(["annual_report_filed", "reporting_termination", "securities_offering_notice_form_d",
                                        "follow_on_reg_cf_offering_filed", "other_reg_cf_offering_progress_reported",
                                        "periodic_report_10k", "ipo_prospectus_final", "exchange_registration_8a12b",
                                        "reg_a_offering_filed", "registration_statement_filed",
                                        "securities_offering_notice_form_d_amendment"])]
    marked = C[(C["association_level"] == "offering") & ((C["mark"] != "") | (C["footnote_no"] != ""))]["offering_id"].unique()
    ext = ev[ev["evidence_strength"].map(lambda s: s not in ("filing_evidence", "issuer_reported_financials", "sec_index",
                                                               "platform_claim_in_sec_filing"))
             & ~ev["event_type"].isin(["website_unreachable", "website_live_undated", "website_domain_not_controlled"])]
    P, N = X[X["pilot"]], X[~X["pilot"]]
    ext_ids = set(ext["offering_id"])
    post_ids = set(ev_post["offering_id"])
    defin = ["listed_public", "acquired", "dissolved_or_liquidated_documented", "operational_closure_documented"]
    checks = [
        ("Completion status parsed (C-U text or C-W)", lambda d: int((d["completion_status"] != "").sum())),
        ("≥1 post-offering SEC issuer filing recorded", lambda d: int(d["offering_id"].isin(post_ids).sum())),
        ("Last SEC-issuer observation on/after 2023-10-10", lambda d: int((d["last_observation_sec_issuer"] >= RECENT3).sum())),
        ("Republic holding linked at offering level (manually reviewed)", lambda d: int((d["entity_match_best"] == "offering_level").sum())),
        ("Republic status mark or numbered note on the offering-level holding", lambda d: int(d["offering_id"].isin(marked).sum())),
        ("Dated operating evidence, any tier", lambda d: int((d["last_operating_evidence_date"] != "").sum())),
        ("Dated operating evidence on/after 2024-10-10", lambda d: int((d["last_operating_evidence_date"] >= RECENT2).sum())),
        ("External dated evidence item (excl. website reachability)", lambda d: int(d["offering_id"].isin(ext_ids).sum())),
        ("Any observation on/after 2023-10-10 (SEC issuer, Republic mark/note, external)",
         lambda d: int((d["last_observation_any"] >= RECENT3).sum())),
        ("Legal status from a state registry", lambda d: int((~d["legal_status"].str.startswith("not_accessed")).sum())),
        ("Strict definitive label (listed/acquired/dissolved/closure); denominator excludes withdrawn",
         lambda d: f"{int(d['strict_label'].isin(defin).sum())}/{int((d['completion_status'] != 'withdrawn').sum())}"),
        ("Investor cash flows recovered from accessible sources", lambda d: 0),
    ]
    rows = [(name, f(P), "0 (not collected)", f(N), f(X)) for name, f in checks]
    T["t1_coverage_before_after"] = pd.DataFrame(rows, columns=[
        "field", f"pilot n={len(P)} (phase 2 sources, phase-3 rules)", f"non-pilot n={len(N)} before phase 3",
        f"non-pilot n={len(N)} after", f"all n={len(X)} after"])

    # 2. unique issuers vs offerings ----------------------------------------------------------------
    issuer_level = C[C["association_level"] == "issuer"]["offering_id"].nunique()
    later_rounds = ev[ev["event_type"] == "follow_on_reg_cf_offering_filed"]["offering_id"].nunique()
    T["t2_issuers_vs_offerings"] = pd.DataFrame([
        ("Sampled offerings", n), ("Unique issuer CIKs", sample["issuer_cik"].nunique()),
        ("Issuers with >1 Republic offering inside the 2018–2020 frame", int((sample["n_republic_offerings_for_issuer"].astype(float) > 1).sum())),
        ("Issuers with a later Form C (any platform) after the sampled offering", later_rounds),
        ("Issuers with ≥1 other Republic holding series kept at issuer level (other round)", issuer_level),
        ("Offerings whose Republic holding has >1 yearly row (repeated observations of one series)",
         int(C[C["association_level"] == "offering"].groupby("offering_id")["holdings_as_of"].nunique().gt(1).sum())),
    ], columns=["quantity", "count"])

    # 3. claims vs adjudicated -----------------------------------------------------------------------
    co = C[C["association_level"] == "offering"]
    claim_rows = []
    for oid, g in co.groupby("offering_id"):
        kinds = []
        if (g["mark"].str.contains(r"\*")).any():
            kinds.append("* insolvent/dormant/dissolved (composite)")
        if (g["mark"].str.contains(r"\+")).any():
            kinds.append("+ converted, no cash to Republic")
        if (g["footnote_no"] != "").any():
            kinds.append("numbered note: Republic holding liquidated/tendered")
        for k in kinds:
            lab = X[X["offering_id"] == oid].iloc[0]
            claim_rows.append({"platform_claim": k, "offering": lab["legal_name"], "strict_label": lab["strict_label"],
                               "strict_reason": lab["strict_reason"]})
    for _, r in X[X["platform_status_issuer_level_only"] != ""].iterrows():
        claim_rows.append({"platform_claim": "* on another round only (issuer level)", "offering": r["legal_name"],
                           "strict_label": r["strict_label"], "strict_reason": r["strict_reason"]})
    T["t3_claims_vs_adjudicated"] = pd.DataFrame(claim_rows).sort_values(["platform_claim", "offering"])

    # 4. outcomes by cohort and source --------------------------------------------------------------------------
    t4 = pd.crosstab(X["strict_label"] + " — " + X["strict_reason"], X["cohort_year"], margins=True, margins_name="all")
    T["t4a_strict_by_cohort"] = t4.reset_index().rename(columns={"row_0": "strict label — reason"})
    sens = X.assign(s=X["sensitivity_labels"].str.split(";")).explode("s").reset_index(drop=True)
    sens = sens[sens["s"] != ""]
    T["t4b_sensitivity_by_cohort"] = pd.crosstab(sens["s"], sens["cohort_year"], margins=True, margins_name="all").reset_index() \
        .rename(columns={"s": "sensitivity label (not exclusive)"})
    src = X[["offering_id", "cohort_year"]].copy()
    src["sec_issuer"] = X["last_observation_sec_issuer"] != ""
    src["sec_platform_mark_or_note"] = X["last_observation_platform"] != ""
    src["external"] = X["last_observation_external"] != ""
    T["t4c_source_presence_by_cohort"] = src.groupby("cohort_year")[["sec_issuer", "sec_platform_mark_or_note", "external"]].sum() \
        .assign(offerings=src.groupby("cohort_year").size()).reset_index()

    # 5. last observation and follow-up ---------------------------------------------------------------------------
    X["decision_date"] = X["offering_id"].map(dict(zip(off["offering_id"], off["decision_date"])))
    X["followup_years"] = ((pd.Timestamp(cfg["study"]["outcome_cutoff_utc"]) - pd.to_datetime(X["decision_date"])).dt.days / 365.25).round(1)
    X["last_obs_year_any"] = X["last_observation_any"].str[:4].replace("", "none")
    X["last_obs_year_sec"] = X["last_observation_sec_issuer"].str[:4].replace("", "none")
    t5 = X.groupby("cohort_year").agg(offerings=("offering_id", "size"), followup_min=("followup_years", "min"),
                                      followup_max=("followup_years", "max"),
                                      last_any_ge_2023_10_10=("last_observation_any", lambda s: int((s >= RECENT3).sum())),
                                      last_sec_issuer_ge_2023_10_10=("last_observation_sec_issuer", lambda s: int((s >= RECENT3).sum())))
    T["t5a_followup_by_cohort"] = t5.reset_index()
    T["t5b_last_observation_year"] = pd.crosstab(X["last_obs_year_any"], X["cohort_year"], margins=True, margins_name="all").reset_index() \
        .rename(columns={"last_obs_year_any": "year of last observation (any tier)"})

    # 6. missingness ----------------------------------------------------------------------------------------------
    miss = [
        ("legal_status", int(X["legal_status"].str.startswith("not_accessed").sum()), n,
         "state registries blocked from this environment (DE CAPTCHA, CA bot protection, NY/FL refused); no user import"),
        ("last_operating_evidence_date", int((X["last_operating_evidence_date"] == "").sum()), n,
         "no C-AR with revenue, no 10-K, no dated company/independent item found"),
        ("Republic holding at offering level", int((X["entity_match_best"] != "offering_level").sum()), n,
         "4 withdrawn offerings (no issuance), 1 issuer-level only (Linen), 1 ambiguous (Gesture)"),
        ("investor_distributions", int((X["investor_distributions"] == "none recovered from accessible sources").sum()), n,
         "no issuer filing or investor document; platform notes describe Republic's holding"),
        ("acquisition_or_listing", int((X["acquisition_or_listing"] == "none found").sum()), n,
         "absence of a filing/report is not evidence of no event"),
        ("archived campaign pages / platform updates", n, n, "republic.com behind Cloudflare challenge; Wayback blocked by proxy"),
    ]
    T["t6_missingness"] = pd.DataFrame(miss, columns=["field", "missing", "denominator", "cause"])

    # 7. conflicts -------------------------------------------------------------------------------------------------
    T["t7_conflicts"] = X[X["conflicts"] != ""][["legal_name", "conflicts", "strict_label", "strict_reason"]]

    # 8. linkage uncertainty ---------------------------------------------------------------------------------------------
    best = al.sort_values("match_class", key=lambda s: s.map({"exact": 0, "corroborated_alias": 1, "ambiguous": 2, "unmatched": 3}))
    b1 = best.drop_duplicates("offering_id")[["offering_id", "match_class"]].merge(F[["offering_id", "entity_match_best"]], on="offering_id")
    T["t8a_match_class_offering_level"] = b1.groupby(["match_class", "entity_match_best"]).size().rename("offerings").reset_index() \
        .rename(columns={"match_class": "best match class (rejected = candidate rejected on review)", "entity_match_best": "association used"})
    ser = co.groupby("series_id")["issuance_month"].nunique()
    T["t8b_linkage_uncertainty"] = pd.DataFrame([
        ("Offering-level series via corroborated alias (brand ≠ legal name)", co[co["match_class"] == "corroborated_alias"]["offering_id"].nunique()),
        ("Offering-level series whose issuance month differs across filings", int((ser > 1).sum())),
        ("Ambiguous candidate series (never used in labels)", int((al["match_class"] == "ambiguous").sum())),
        ("Ambiguous aliases used in any label", int(C[(C["match_class"] == "ambiguous")]["offering_id"].isin(
            X[X["strict_label"] != "unresolved"]["offering_id"]).sum())),
        ("External items with identity uncertain (suffix mismatch)", int((ev["attribution_level"] == "issuer_identity_uncertain").sum())),
    ], columns=["linkage issue", "count"])

    # 9. source yield --------------------------------------------------------------------------------------------------
    tl = pd.read_csv(md / "phase3_time_log.csv", dtype=str, keep_default_na=False)
    web_ok = web["status"].value_counts().to_dict() if "status" in web else {}
    srch = pd.read_csv(md / "web_search_log.csv", dtype=str, keep_default_na=False)
    srch3 = srch[srch["date_utc"] >= "2026-10-13"]
    T["t9_source_yield"] = pd.DataFrame([
        ("EDGAR submissions/index (issuer filings)", 40, ev_post["offering_id"].nunique(), "automated; 0 network requests on re-run (cached)"),
        ("Republic holdings tables (4 SEC filings, 2,184 rows)", 40, len(marked), "status marks/notes on offering-level holdings"),
        ("Company websites (35 non-pilot)", len(web), int((web["status"] == "live_dated_content").sum()),
         "; ".join(f"{k}={v}" for k, v in web_ok.items())),
        ("Selective web searches (phase 3)", len(srch3), int(srch3["used_as_evidence"].str.startswith("yes").sum()), "searches -> items used"),
        ("State registries", 4, 0, "all blocked"),
    ], columns=["source", "attempted (offerings or searches)", "yielding usable dated evidence", "note"])
    return T


def cmd_report_p3(cfg: Config, args) -> int:
    T = build_tables(cfg)
    out = cfg.root / "reports" / "phase3_tables"
    out.mkdir(parents=True, exist_ok=True)
    parts = []
    for k, df in T.items():
        df.to_csv(out / f"{k}.csv", index=False)
        parts.append(f"### {k}\n\n{_md(df)}\n")
    (out / "phase3_tables.md").write_text("\n".join(parts))
    print("\n".join(parts))
    return 0
