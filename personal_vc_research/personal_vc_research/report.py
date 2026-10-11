"""Report generation: reports/pilot_feasibility.md (+ manual_review_queue.csv).

Computed sections come from data/tables/*; the hand-written assessment and recommendation live in
docs/pilot_assessment.md and are appended verbatim so judgments stay separate from computed counts.
"""
from __future__ import annotations

import json

import pandas as pd

from .config import Config

CONTRACT_KEYS = ["valuation_cap", "discount_rate", "cap_basis", "conversion_trigger", "liquidity_event_treatment",
                 "company_repurchase_right", "minimum_investment"]
FOUNDER_KEYS = ["officers_directors_listed", "founder_count_labelled", "dated_prior_roles",
                "prior_ventures_documented", "co_tenure_documented", "prior_exits_documented"]


def _read(p):
    return pd.read_csv(p, dtype=str, keep_default_na=False) if p.exists() else pd.DataFrame()


def _md(df: pd.DataFrame) -> str:
    if df.empty:
        return "_(none)_\n"
    cols = list(df.columns)
    out = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for _, r in df.iterrows():
        out += "| " + " | ".join(str(r[c]).replace("|", "/").replace("\n", " ") for c in cols) + " |\n"
    return out


def pilot_rows(cfg: Config) -> tuple[pd.DataFrame, dict]:
    td = cfg.path("tables_dir")
    off = _read(td / "offerings_pilot.csv")
    facts = _read(td / "facts_pilot.csv")
    ev = _read(td / "outcome_events_pilot.csv")
    pay = _read(td / "payout_evidence_pilot.csv")
    ocr = _read(td / "ocr_log.csv")
    native = {}
    man = {}
    for line in open(cfg.path("manifest")):
        r = json.loads(line)
        man[r["url"]] = r
    rows = []
    for _, o in off.iterrows():
        oid = o["offering_id"]
        fo = facts[facts["offering_id"] == oid]
        # document/page coverage
        pdf = man.get(o["form_c_pdf_url"], {})
        npages = readable = 0
        if pdf.get("sha256"):
            nj = cfg.root / "data/cache/pages" / pdf["sha256"] / "native.json"
            if nj.exists():
                pages = json.loads(nj.read_text())
                npages = len(pages)
                readable = sum(p["quality"] >= 0.75 for p in pages)
        oc = ocr[(ocr["offering_id"] == oid) & (ocr["status"] == "ocr_done")] if len(ocr) else pd.DataFrame()
        ocr_pages = len(oc)
        ocr_secs = round(sum(float(x) for x in oc["seconds"]), 1) if len(oc) else 0.0
        native[oid] = (npages, readable)
        # historical features eligible at decision
        st = fo[(fo["extraction_method"] == "structured_field") & (fo["eligible_at_decision"] == "True")]
        fin = st[st["fact_group"] == "financial"]
        fin_cov = f"{(fin['missing'] == 'False').sum()}/{len(fin)}"
        # contract reconstruction
        cvals = {k: fo[fo["fact_name"] == k] for k in CONTRACT_KEYS}
        have = [k for k, v in cvals.items() if len(v) and (v["missing"] == "False").any()]
        located = fo[fo["fact_name"] == "form_of_security_located"]["value_text"]
        instrument = "instrument text read" if len(located) and located.iloc[0].startswith("yes") else "memorandum summary only"
        ver = fo[fo["fact_name"].isin(["valuation_cap", "discount_rate"])]["verification_status"].tolist()
        contract = f"{len(have)}/{len(CONTRACT_KEYS)} key terms; {instrument}; cap/discount: {', '.join(sorted(set(ver)))}"
        # founder information
        fhave = [k for k in FOUNDER_KEYS if len(fo[(fo["fact_name"] == k) & (fo["missing"] == "False")])]
        founder = f"{len(fhave)}/{len(FOUNDER_KEYS)} (prior exits: not documented)"
        # subsequent events
        eo = ev[ev["offering_id"] == oid]
        key_types = ["offering_completion_reported", "annual_report_filed", "securities_offering_notice_form_d",
                     "follow_on_reg_cf_offering_filed", "reporting_termination", "ipo_prospectus_final",
                     "financing_independent_report", "operating_activity_independent_report"]
        evs = []
        for t in key_types:
            x = eo[eo["event_type"] == t]
            if len(x):
                dates = sorted(d for d in x["publication_date"] if d)
                evs.append(f"{t} ×{len(x)} ({dates[0]}{'…' + dates[-1] if len(dates) > 1 else ''})")
        po = pay[pay["offering_id"] == oid]
        payout = "; ".join(sorted(set(po["evidence_type"])))
        rows.append({
            "offering": f"{o['issuer_legal_name_at_offering']} ({oid})",
            "cohort": o["cohort_year"], "decision date": o["decision_date"],
            "available at decision": o["availability_at_decision"],
            "historical docs / pages": f"Form C XML + PDF {npages}p (native-readable {readable}, OCR {ocr_pages})",
            "structured financial fields eligible (non-missing/total)": fin_cov,
            "contract reconstruction": contract, "founder info": founder,
            "completion": f"{o['completion_status']} ${float(o['amount_reported_at_close_usd'] or 0):,.0f}",
            "subsequent events (publication dates)": "; ".join(evs),
            "last observation": o["last_observation_date"], "outcome summary": o["outcome_status_summary"],
            "investor payout evidence": payout, "return": o["return_status"],
            "OCR time (s)": ocr_secs, "collect time (s)": o["collection_seconds"],
        })
    return pd.DataFrame(rows), {"native": native}


def manual_review_queue(cfg: Config) -> pd.DataFrame:
    td = cfg.path("tables_dir")
    q = []
    fr = _read(cfg.path("frame_dir") / "sampling_frame_all_candidates.csv")
    for _, r in fr[fr["needs_manual_review"] == "True"].iterrows():
        q.append({"offering_id": r["offering_id"], "scope": "frame", "issue": r["review_note"] or r["exclusion_reason"],
                  "priority": "high" if r["eligible"] == "True" else "medium"})
    facts = _read(td / "facts_pilot.csv")
    for _, f in facts[(facts["verification_status"] == "ocr_read_not_visually_verified")].iterrows():
        if f["fact_group"] == "contract":
            q.append({"offering_id": f["offering_id"], "scope": "pilot_fact",
                      "issue": f"verify OCR contract term '{f['fact_name']}' against rendered page {f['locator']}",
                      "priority": "medium"})
    audit = _read(cfg.path("reports_dir") / "pilot_second_pass_audit.csv")
    for _, a in audit[audit["match"] == "False"].iterrows():
        q.append({"offering_id": a["offering_id"], "scope": "audit_discrepancy",
                  "issue": f"{a['check']}: {a['value_a']} vs {str(a['value_b'])[:120]}", "priority": "high"})
    ev = _read(td / "outcome_events_pilot.csv")
    for _, e in ev[ev["event_type"] == "reporting_termination"].iterrows():
        if "not stated" in e["details"]:
            q.append({"offering_id": e["offering_id"], "scope": "outcome",
                      "issue": "C-TR without stated reason; business status unknown", "priority": "medium"})
    off = _read(td / "offerings_pilot.csv")
    for _, o in off.iterrows():
        if o["visibility_lost_gt_3y"] == "True":
            q.append({"offering_id": o["offering_id"], "scope": "outcome",
                      "issue": f"no observation since {o['last_observation_date']} (>3y): status unknown",
                      "priority": "medium"})
        if o["n_annual_reports_filed"] == "0" and o["completion_status"].startswith("completion"):
            q.append({"offering_id": o["offering_id"], "scope": "outcome",
                      "issue": "offering reported closed but no Form C-AR ever filed (reporting non-compliance?)",
                      "priority": "medium"})
    pay = _read(td / "payout_evidence_pilot.csv")
    for _, p in pay[pay["evidence_type"].str.startswith("security_class_conversion")].iterrows():
        q.append({"offering_id": p["offering_id"], "scope": "payout",
                  "issue": "SAFE conversion reported at pooled level; per-round/per-investor shares and basis not traceable",
                  "priority": "high"})
    return pd.DataFrame(q).drop_duplicates()


def cmd_report(cfg: Config, args) -> int:
    rd = cfg.path("reports_dir")
    td = cfg.path("tables_dir")
    table, meta = pilot_rows(cfg)
    q = manual_review_queue(cfg)
    q.to_csv(rd / "manual_review_queue.csv", index=False)
    facts = _read(td / "facts_pilot.csv")
    ev = _read(td / "outcome_events_pilot.csv")
    src = _read(td / "sources_pilot.csv")
    ocr = _read(td / "ocr_log.csv")
    audit = _read(rd / "pilot_second_pass_audit.csv")
    screen = _read(td / "form_c_text_screening.csv")
    run = json.loads((td / "collect_run_pilot.json").read_text()) if (td / "collect_run_pilot.json").exists() else {}
    fz = json.loads((cfg.path("sample_dir") / "sample_freeze.json").read_text())
    ff = json.loads((cfg.path("frame_dir") / "frame_freeze.json").read_text())

    real_events = ev[~ev["event_type"].isin(["entity_name_change_recorded"])]
    lines = []
    lines.append("# Pilot feasibility report — Republic Reg CF 2018–2020 (5 frozen pilot offerings)\n")
    lines.append(f"Generated by `python -m personal_vc_research report`. Outcome cutoff {cfg['study']['outcome_cutoff_utc']} "
                 f"(run UTC start date). Frame sha256 `{ff['frame_sha256'][:12]}` ({ff['n_eligible']} eligible of "
                 f"{ff['n_candidates']} candidates); sample sha256 `{fz['sample_sha256'][:12]}` (n={fz['n']}, seed {fz['seed']}). "
                 "Five observations evaluate the workflow; they cannot establish statistical feasibility or investment performance.\n")
    lines.append("## 1. Per-offering coverage\n")
    lines.append(_md(table))
    lines.append("\nColumn notes: *available at decision* is inferred from filings dated on or before the decision date "
                 "(deadline in effect, no C-W, no closing C-U); no archived campaign page was accessible, so it is never "
                 "'verified'. *Structured financial fields* are the Form C cover-page fields (DERA) published on or before "
                 "the decision date, counted per filing (initial Form C + pre-decision C/As). Completion amounts come "
                 "from C-U progress updates and are **completion evidence, not investor profit**.\n")
    lines.append("## 2. Counts (denominators shown)\n")
    man = facts[facts["extraction_method"] != "structured_field"]
    cnt = {
        "pilot offerings processed": f"{len(table)}/5",
        "facts recorded (all)": len(facts),
        "facts eligible at decision date": f"{(facts['eligible_at_decision'] == 'True').sum()}/{len(facts)}",
        "facts published after decision (stored, excluded from features)": int((facts['eligible_at_decision'] == 'False').sum()),
        "missing-value facts (with reason, not zero)": int((facts['missing'] == 'True').sum()),
        "manual (PDF/OCR) facts": len(man),
        "  of which verified against rendered page": int((man['verification_status'] == 'verified_rendered_page').sum()),
        "  of which native text read": int((man['verification_status'] == 'native_text_read').sum()),
        "  of which OCR read, not visually verified": int((man['verification_status'] == 'ocr_read_not_visually_verified').sum()),
        "outcome events (excluding name-change records)": len(real_events),
        "sources": len(src),
        "network requests in final pilot collect run (cache reused)": run.get("network_requests", ""),
        "OCR pages processed (pilot)": int((ocr['status'] == 'ocr_done').sum()) if len(ocr) else 0,
        "OCR seconds (pilot, final runs)": round(sum(float(x) for x in ocr[ocr['status'] == 'ocr_done']['seconds']), 1) if len(ocr) else 0,
        "second-pass audit checks / discrepancies": f"{(audit['match'] != '').sum()} / {(audit['match'] == 'False').sum()}",
        "documented investor cash flows": 0,
        "returns calculated on real data": 0,
    }
    lines.append(_md(pd.DataFrame({"measure": list(cnt.keys()), "value": [str(v) for v in cnt.values()]})))
    lines.append("\n### Event counts by type (pilot)\n")
    lines.append(_md(real_events.groupby("event_type").size().reset_index(name="n").sort_values("n", ascending=False)))
    lines.append("\n## 3. OCR log summary (bounded, targeted)\n")
    if len(ocr):
        g = ocr.groupby(["offering_id", "status"]).agg(pages=("page", "count"),
                                                      seconds=("seconds", lambda s: round(sum(float(x) for x in s), 1)),
                                                      batches=("batch", lambda s: ",".join(sorted(set(s))))).reset_index()
        lines.append(_md(g))
    lines.append("\nPage selection rationale per batch: `data/manual/ocr_page_plan.csv`; per-page status: "
                 "`data/tables/ocr_log.csv`. Pages not OCR'd in garbled documents are **not extracted within budget**, "
                 "not 'not disclosed'. Earlier (pre-pilot) whole-document OCR attempt: 2 documents, ~21 min, 0 pages "
                 "(tesseract OpenMP oversubscription; fixed with OMP_THREAD_LIMIT=1).\n")
    lines.append("## 4. Second-pass audit (same agent — not independent validation)\n")
    if len(audit):
        a = audit[audit["match"] != ""].copy()
        a["family"] = a["check"].str.split(":").str[0]
        lines.append(_md(a.groupby("family")["match"].agg(checks="count", matched=lambda s: (s == "True").sum()).reset_index()))
        lines.append("\nDiscrepancies:\n")
        lines.append(_md(audit[audit["match"] == "False"][["offering_id", "check", "value_a", "value_b"]]))
    lines.append("\n## 5. Traced source examples (rule: first contract term, first completion event, first post-decision "
                 "outcome event per pilot offering, in collection order)\n")
    for _, o in _read(td / "offerings_pilot.csv").iterrows():
        oid = o["offering_id"]
        lines.append(f"\n**{o['issuer_legal_name_at_offering']}** (`{oid}`, initial Form C {o['initial_filing_date']}, decision {o['decision_date']})\n")
        fo = facts[(facts["offering_id"] == oid) & (facts["fact_name"] == "valuation_cap")]
        for _, f in fo.head(1).iterrows():
            s = src[src["source_id"] == f["source_id"]]
            lines.append(f"- Contract: valuation cap = {f['value_text'] or 'MISSING'} ({f['locator']}, {f['extraction_method']}, "
                         f"{f['verification_status']}); source {s['url'].iloc[0] if len(s) else ''}; excerpt: “{f['evidence_excerpt'][:160]}”\n")
        eo = ev[(ev["offering_id"] == oid)]
        for t in ["offering_completion_reported"]:
            for _, e in eo[eo["event_type"] == t].head(1).iterrows():
                lines.append(f"- Completion: {e['details'][:220]} (published {e['publication_date']}; {e['locator']})\n")
        post = eo[(eo["publication_date"] > o["decision_date"]) & ~eo["event_type"].isin(
            ["offering_completion_reported", "progress_update", "entity_name_change_recorded"])].sort_values("publication_date")
        for _, e in post.head(1).iterrows():
            s = src[src["source_id"] == e["source_id"]]
            lines.append(f"- First later event: {e['event_type']} published {e['publication_date']} — {e['details'][:220]} "
                         f"({s['url'].iloc[0] if len(s) else ''})\n")
    if len(screen):
        lines.append("\n## 6. Native-text screening of the other sampled Form C documents (no OCR)\n")
        s = screen.copy()
        lines.append(_md(s.groupby("text_layer_class").size().reset_index(name="documents")))
        lines.append("\nPer document: `data/tables/form_c_text_screening.csv`.\n")
    lines.append("\n## 7. Manual review queue\n")
    lines.append(f"{len(q)} items in `reports/manual_review_queue.csv` "
                 f"(high {int((q['priority'] == 'high').sum())}, medium {int((q['priority'] == 'medium').sum())}).\n")
    assess = cfg.root / "docs" / "pilot_assessment.md"
    if assess.exists():
        lines.append("\n" + assess.read_text())
    (rd / "pilot_feasibility.md").write_text("\n".join(lines))
    if (td / "phase1_offerings_pilot_snapshot.csv").exists():
        (rd / "outcome_recovery.md").write_text(outcome_recovery_report(cfg))
        print(f"wrote {rd / 'outcome_recovery.md'}")
    print(f"wrote {rd / 'pilot_feasibility.md'} and manual_review_queue.csv ({len(q)} items)")
    return 0


# ---------------------------------------------------------------------------------------------
# Phase 2: outcome-recovery report
# ---------------------------------------------------------------------------------------------
COVERAGE_FIELDS = [
    ("financial", ["revenue", "net_income", "total_assets", "cash_and_equivalents"]),
    ("offering_terms", ["target_offering_amount", "maximum_offering_amount", "offering_deadline", "price_per_security",
                        "minimum_investment", "employees"]),
    ("contract", ["valuation_cap", "discount_rate", "cap_basis", "conversion_trigger", "liquidity_event_treatment",
                  "company_repurchase_right", "dissolution_treatment"]),
    ("company", ["fiscal_year_end_most_recent", "prior_securities_outstanding", "date_incorporation"]),
    ("founder", ["officers_directors_listed", "founder_count_labelled", "prior_ventures_documented", "prior_exits_documented"]),
]


def field_coverage(facts: pd.DataFrame) -> pd.DataFrame:
    """One cell per (field, offering): S = structured filing field eligible at decision; V = manual, verified on
    rendered page or native text; O = manual from OCR not visually verified; '-' = missing/not extracted."""
    offs = sorted(facts["offering_id"].unique())
    rows = []
    for group, names in COVERAGE_FIELDS:
        for n in names:
            row = {"group": group, "field": n}
            for o in offs:
                x = facts[(facts["offering_id"] == o) & (facts["fact_name"] == n) & (facts["missing"] == "False")
                          & (facts["eligible_at_decision"] == "True")]
                if not len(x):
                    cell = "-"
                elif (x["extraction_method"] == "structured_field").any():
                    cell = "S"
                elif x["verification_status"].isin(["verified_rendered_page", "native_text_read"]).any():
                    cell = "V"
                else:
                    cell = "O"
                row[o.split("-")[1]] = cell
            rows.append(row)
    return pd.DataFrame(rows)


def outcome_recovery_report(cfg: Config) -> str:
    td, rd = cfg.path("tables_dir"), cfg.path("reports_dir")
    before = _read(td / "phase1_offerings_pilot_snapshot.csv")
    after = _read(td / "offerings_pilot.csv")
    ev = _read(td / "outcome_events_pilot.csv")
    pay = _read(td / "payout_evidence_pilot.csv")
    facts = _read(td / "facts_pilot.csv")
    tl = _read(cfg.path("manual_dir") / "phase2_time_log.csv")
    jt = _read(cfg.path("manual_dir") / "janover_security_trace.csv")
    tc = _read(rd / "phase2_targeted_high_impact_checks.csv")
    out = ["# Outcome-recovery experiment — 5 pilot offerings (phase 2)\n",
           f"Frozen sample unchanged (seed {cfg.seed}); outcome cutoff {cfg['study']['outcome_cutoff_utc']}. "
           "Source tiers are kept separate: **SEC-issuer** (the company's own filings), **SEC-platform** (Republic's "
           "SEC-filed claims about its 2% commission holdings), **external** (company websites, press, observations).\n"]
    out.append("## 1. Before vs after, per company\n")
    rows = []
    for _, a in after.iterrows():
        b = before[before["offering_id"] == a["offering_id"]]
        b = b.iloc[0] if len(b) else {}
        eo = ev[ev["offering_id"] == a["offering_id"]]
        plat = a.get("platform_status_marks", "")
        po = pay[pay["offering_id"] == a["offering_id"]]
        rows.append({
            "company": a["issuer_legal_name_at_offering"],
            "BEFORE: last observation (phase 1; SEC + 2 Hemster press items)": b.get("last_observation_date", "") if len(b) else "",
            "AFTER: last SEC-issuer obs.": a["last_observation_sec_issuer"],
            "AFTER: last SEC-platform obs.": a["last_observation_sec_platform"],
            "AFTER: last external obs.": a["last_observation_external"] or "-",
            "operating evidence (SEC-issuer / external)": f"{a['last_operating_evidence_sec_issuer'] or '-'} / {a['last_operating_evidence_external'] or '-'}",
            "legal status": "unknown — registries not accessible",
            "Republic marks (as-of year)": plat,
            "platform mark conflicts SEC": a["platform_mark_conflicts_with_sec_evidence"],
            "payout visibility": "; ".join(sorted(set(po["evidence_type"]))),
            "summary BEFORE → AFTER": f"{b.get('outcome_status_summary', '') if len(b) else ''} → {a['outcome_status_summary']}",
        })
    out.append(_md(pd.DataFrame(rows)))
    out.append("\nRepublic legend (verbatim, SEC filings by Republic Core LLC / Republic Note): `*` = \"to Republic "
               "Crowd-Invest's knowledge the issuer is insolvent, dormant, or has dissolved and [it] does not expect to "
               "receive any cash proceeds\"; `+` = \"security has converted due to a qualifying equity financing, liquidity "
               "event ... but [it] has not realized cash proceeds\"; numbered notes = liquidation at stated cents on the dollar. "
               "These are platform claims about Republic's own commission securities, not registry facts.\n")
    out.append("## 2. Event counts by source tier (pilot, after phase 2)\n")
    from .outcomes import source_tier
    ev2 = ev.copy()
    ev2["tier"] = ev2["evidence_strength"].map(source_tier)
    b_ev = _read(td / "phase1_outcome_events_pilot_snapshot.csv")
    t = ev2.groupby("tier").size().reset_index(name="events_after")
    t["events_before"] = t["tier"].map(b_ev.assign(tier=b_ev["evidence_strength"].map(source_tier)).groupby("tier").size()).fillna(0).astype(int)
    out.append(_md(t))
    out.append("\n## 3. Field coverage by offering (historical, eligible at decision date)\n")
    out.append("`S` structured filing field · `V` manual, verified (rendered page or native text) · `O` manual from OCR, "
               "not visually verified · `-` missing / not extracted. 404 stored fact rows are **not** 404 independent "
               "observations: they repeat fields across the initial Form C and pre-decision amendments, and include "
               "post-decision rows that are excluded from features.\n")
    out.append(_md(field_coverage(facts)))
    out.append("\n## 4. Janover security reconstruction (2020 Republic Crowd SAFE)\n")
    out.append(_md(jt[["level", "event_or_as_of", "claim", "status", "notes"]]))
    out.append("\nLevels: 1 issuer-wide aggregate conversions · 2 shares attributable to the Republic offering · "
               "3 shares per original dollar · 4 legal/practical tradability · 5 actual investor cash proceeds. "
               "**Stopped at level 1**: the conversion class pools the Republic SAFEs with a $50,000 non-Republic SAFE and "
               "the disclosed amounts conflict, so no proportional allocation was made. No price history was retrieved; "
               "no hypothetical liquidation was computed.\n")
    out.append("## 5. Targeted high-impact checks (separate from the random audit)\n")
    out.append(_md(tc))
    out.append("\n## 6. Time and source yield\n")
    if len(tl):
        tl2 = tl.copy()
        starts = tl2[tl2["start_utc"] != ""].groupby("task")["start_utc"].min()
        ends = tl2[tl2["end_utc"] != ""].groupby("task")["end_utc"].max()
        tt = pd.DataFrame({"start": starts, "end": ends}).dropna()
        tt["agent_minutes_measured"] = ((pd.to_datetime(tt["end"]) - pd.to_datetime(tt["start"])).dt.total_seconds() / 60).round(1)
        out.append(_md(tt.reset_index()))
        out.append(f"\nMeasured agent wall-clock for the experiment: **{tt['agent_minutes_measured'].sum():.0f} minutes** "
                   "(container clock; excludes report writing). This is not analyst time; see the assessment for a labelled "
                   "analyst-equivalent estimate.\n")
    ys = _read(cfg.path("manual_dir") / "phase2_source_yield.csv")
    if len(ys):
        out.append(_md(ys))
    assess = cfg.root / "docs" / "outcome_recovery_assessment.md"
    if assess.exists():
        out.append("\n" + assess.read_text())
    return "\n".join(out)
