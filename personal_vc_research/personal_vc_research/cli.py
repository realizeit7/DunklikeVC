"""Command-line interface: discover, sample, collect, audit, report."""
from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from . import dera, frame as frame_mod, sampling
from .config import Config
from .http import Fetcher, MissingUserAgent, utcnow_iso


def cmd_discover(cfg: Config, args) -> int:
    f = Fetcher(cfg)
    log = dera.download_all(cfg, f)
    tables = dera.load_tables(cfg, f)
    fr, ev, linked = frame_mod.build_frame(tables, cfg)
    d = cfg.path("frame_dir")
    ev.to_csv(d / "intermediary_evidence.csv", index=False)
    linked.to_csv(d / "linked_filings.csv", index=False)
    pd.DataFrame(log).to_csv(d / "dera_download_log.csv", index=False)
    h = frame_mod.frame_hash(fr)
    freeze = d / "frame_freeze.json"
    if freeze.exists() and not args.refreeze:
        old = json.loads(freeze.read_text())
        if old["frame_sha256"] != h:
            print(f"ERROR: recomputed frame hash {h} differs from frozen {old['frame_sha256']}. "
                  "Frozen frame left untouched; rerun with --refreeze only if a change is intended.",
                  file=sys.stderr)
            fr.to_csv(d / "sampling_frame_recomputed_UNFROZEN.csv", index=False)
            return 2
        print(f"frame unchanged (sha256 {h[:12]})")
    else:
        sampling.write_freeze(freeze, {
            "frame_sha256": h, "frozen_at_utc": utcnow_iso(), "n_candidates": int(len(fr)),
            "n_eligible": int(fr["eligible"].sum()), "outcome_cutoff_utc": cfg["study"]["outcome_cutoff_utc"],
            "intermediary_ciks": sorted(ev["COMMISSIONCIK"].unique().tolist()),
            "dera_quarters": [l["quarter"] for l in log], "dera_zip_sha256": {l["quarter"]: l["sha256"] for l in log},
        })
    fr.to_csv(d / "sampling_frame_all_candidates.csv", index=False)
    fr[fr["eligible"]].to_csv(d / "sampling_frame.csv", index=False)
    fr[~fr["eligible"]].to_csv(d / "excluded_candidates.csv", index=False)
    print(f"candidates={len(fr)} eligible={int(fr['eligible'].sum())} "
          f"excluded={int((~fr['eligible']).sum())} network_requests={f.network_requests}")
    print(fr.groupby(["cohort_year", "eligible"]).size().unstack(fill_value=0))
    return 0


def cmd_sample(cfg: Config, args) -> int:
    d = cfg.path("frame_dir")
    sd = cfg.path("sample_dir")
    freeze_f = json.loads((d / "frame_freeze.json").read_text())
    fr = pd.read_csv(d / "sampling_frame_all_candidates.csv", dtype=str, keep_default_na=False)
    fr["eligible"] = fr["eligible"] == "True"
    if frame_mod.frame_hash(fr) != freeze_f["frame_sha256"]:
        print("ERROR: sampling frame on disk does not match frozen hash", file=sys.stderr)
        return 2
    st = cfg["study"]
    alloc = {int(k): int(v) for k, v in st["per_year_allocation"].items()}
    s = sampling.stratified_sample(fr, alloc, cfg.seed)
    pilot = set(s.nsmallest(st["pilot_size"], "collection_order")["offering_id"])
    audit = set(sampling.designate(s, st["audit_size"], cfg.seed, "audit"))
    s["is_pilot"] = s["offering_id"].isin(pilot)
    s["is_audit"] = s["offering_id"].isin(audit)
    s["decision_date"] = s["initial_filing_date"].map(lambda x: frame_mod.decision_date(x, cfg.decision_days))
    h = sampling.sample_hash(s)
    sf = sd / "sample_freeze.json"
    if sf.exists():
        old = json.loads(sf.read_text())
        if old["sample_sha256"] != h:
            print("ERROR: recomputed sample differs from frozen sample; refusing to overwrite.", file=sys.stderr)
            return 2
        print(f"sample unchanged (sha256 {h[:12]})")
    else:
        sampling.write_freeze(sf, {"sample_sha256": h, "frame_sha256": freeze_f["frame_sha256"],
                                   "frozen_at_utc": utcnow_iso(), "seed": cfg.seed, "allocation": alloc,
                                   "n": int(len(s)), "pilot": sorted(pilot), "audit": sorted(audit)})
        s.to_csv(sd / "frozen_sample.csv", index=False)
    print(s.groupby(["cohort_year", "security_class"]).size())
    return 0


def cmd_ocr(cfg: Config, args) -> int:
    """Run targeted OCR batches from the recorded page plan (data/manual/ocr_page_plan.csv)."""
    from . import pages
    o = cfg["ocr"]
    plan = pd.read_csv(cfg.root / o["plan_file"], dtype=str, keep_default_na=False)
    if args.batch:
        plan = plan[plan["batch"] == args.batch]
    man = {}
    for line in open(cfg.path("manifest")):
        rec = json.loads(line)
        man[rec["url"]] = rec
    docs = {u: {"path": str(cfg.root / man[u]["cache_path"]), "sha256": man[u]["sha256"]}
            for u in plan["doc_url"].unique()}
    rows = pages.run_plan(plan.to_dict("records"), docs, cfg.root / "data/cache/pages",
                          cfg.path("tables_dir") / "ocr_log.csv", int(o["max_pages_per_offering"]),
                          float(o["max_total_seconds"]), int(o["max_pages_per_batch"]))
    df = pd.DataFrame(rows)
    if len(df):
        print(df.groupby(["offering_id", "status"]).agg(pages=("page", "count"), seconds=("seconds", "sum")))
    else:
        print("nothing to do (all planned pages cached)")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="personal_vc_research")
    p.add_argument("command", choices=["discover", "sample", "ocr", "collect", "audit", "report"])
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--refreeze", action="store_true", help="discover: overwrite a frozen frame")
    p.add_argument("--batch", default="", help="ocr: plan batch id to run")
    p.add_argument("--only", default="", help="collect: comma-separated offering_ids or 'pilot'")
    args = p.parse_args(argv)
    cfg = Config.load(args.config)
    try:
        if args.command == "discover":
            return cmd_discover(cfg, args)
        if args.command == "sample":
            return cmd_sample(cfg, args)
        if args.command == "ocr":
            return cmd_ocr(cfg, args)
        if args.command == "collect":
            from .collect import cmd_collect
            return cmd_collect(cfg, args)
        if args.command == "audit":
            from .audit import cmd_audit
            return cmd_audit(cfg, args)
        if args.command == "report":
            from .report import cmd_report
            return cmd_report(cfg, args)
    except MissingUserAgent as exc:
        print(f"CONFIGURATION REQUIRED: {exc}", file=sys.stderr)
        return 3
    return 1
