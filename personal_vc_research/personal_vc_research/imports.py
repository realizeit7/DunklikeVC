"""User-provided browser evidence (campaign pages, updates, PDFs, screenshots, investment documents).

Layout (raw files and investor-only metadata are gitignored):
  data/user_imports/import_register.csv            public items only (committable)
  data/user_imports/private/import_register.csv    investor-only items (gitignored)
  data/user_imports/files/<any>                    raw files referenced by `file` (gitignored)

Rules:
* No credentials are stored or required; the user captures pages in their own browser.
* A page captured today is NOT a historical feature. `historical_feature_eligible` is True only if
  original publication timing is independently verified AND the displayed date is on or before the
  offering's decision date AND the item is publicly visible. Otherwise it may support later outcomes only.
* Investor-only items never appear in public tables or reports (only counts).
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pandas as pd

from .config import Config

REQUIRED = ["item_id", "offering_id", "url_or_document_identity", "file", "capture_date_utc",
            "displayed_publication_or_update_date", "visibility", "security_class", "evidence_locator",
            "publication_timing_independently_verified", "evidence_type", "summary"]
VISIBILITY = {"public", "investor_only"}


def validate_row(r: dict, decision_dates: dict[str, str], root: Path) -> dict:
    errors = [f"missing {k}" for k in REQUIRED if not str(r.get(k, "")).strip() and k != "file"]
    vis = r.get("visibility", "")
    if vis not in VISIBILITY:
        errors.append(f"visibility must be one of {sorted(VISIBILITY)}")
    if r.get("offering_id") not in decision_dates:
        errors.append("offering_id not in frozen sample")
    verified = str(r.get("publication_timing_independently_verified", "")).lower() in ("true", "yes", "1")
    disp = r.get("displayed_publication_or_update_date", "")
    dec = decision_dates.get(r.get("offering_id"), "")
    sha = ""
    if r.get("file"):
        fp = root / "data/user_imports/files" / r["file"]
        if fp.exists():
            sha = hashlib.sha256(fp.read_bytes()).hexdigest()
        else:
            errors.append(f"file not found: {r['file']}")
    eligible = bool(verified and disp and dec and disp <= dec and vis == "public" and not errors)
    use = "historical_feature_and_outcome" if eligible else "outcome_only"
    if disp and dec and disp > dec:
        reason = "displayed date after decision date"
    elif not verified:
        reason = "original publication timing not independently verified"
    elif vis != "public":
        reason = "not publicly visible at the time"
    else:
        reason = ""
    return {**r, "file_sha256": sha, "decision_date": dec, "historical_feature_eligible": eligible,
            "permitted_use": use, "ineligibility_reason": "" if eligible else reason,
            "validation_errors": "; ".join(errors)}


def cmd_import(cfg: Config, args) -> int:
    root = cfg.root
    sample = pd.read_csv(cfg.path("sample_dir") / "frozen_sample.csv", dtype=str, keep_default_na=False)
    dd = dict(zip(sample["offering_id"], sample["decision_date"]))
    out_pub, out_priv = [], []
    for reg, sink in [(root / "data/user_imports/import_register.csv", out_pub),
                      (root / "data/user_imports/private/import_register.csv", out_priv)]:
        if not reg.exists():
            continue
        with open(reg) as fh:
            for r in csv.DictReader(fh):
                v = validate_row(r, dd, root)
                if sink is out_pub and v["visibility"] != "public":
                    v["validation_errors"] = (v["validation_errors"] + "; investor-only item in public register").strip("; ")
                sink.append(v)
    td = cfg.path("tables_dir")
    pd.DataFrame(out_pub, columns=REQUIRED + ["file_sha256", "decision_date", "historical_feature_eligible",
                                             "permitted_use", "ineligibility_reason", "validation_errors"]) \
        .to_csv(td / "user_imports_public.csv", index=False)
    priv_dir = root / "data/user_imports/private"
    priv_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(out_priv).to_csv(priv_dir / "user_imports_private_validated.csv", index=False)
    bad = [x for x in out_pub + out_priv if x["validation_errors"]]
    print(f"public items={len(out_pub)} investor-only items={len(out_priv)} (private, not in git) "
          f"validation errors={len(bad)}")
    for b in bad:
        print(f"  {b.get('item_id')}: {b['validation_errors']}")
    return 0 if not bad else 4
