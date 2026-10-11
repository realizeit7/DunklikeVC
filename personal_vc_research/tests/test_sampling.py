"""Sampling determinism and frozen-cohort protection (SYNTHETIC frame)."""
import json

import pandas as pd

from personal_vc_research import cli
from personal_vc_research.config import Config
from personal_vc_research.frame import frame_hash
from personal_vc_research.sampling import sample_hash, stratified_sample


def _frame(n_per_year=20):
    rows = []
    for y in (2018, 2019, 2020):
        for i in range(n_per_year):
            rows.append({"offering_id": f"SYN-{y}-{i:03d}", "issuer_cik": f"{y}{i}", "file_number": f"020-{i}",
                         "initial_accession": f"a{y}{i}", "initial_filing_date": f"{y}-03-01", "cohort_year": y,
                         "security_class": "safe", "eligible": True})
    return pd.DataFrame(rows)


def test_sampling_deterministic_and_stratified():
    fr = _frame()
    a = stratified_sample(fr, {2018: 3, 2019: 3, 2020: 4}, 42)
    b = stratified_sample(fr.sample(frac=1, random_state=1), {2018: 3, 2019: 3, 2020: 4}, 42)
    assert sample_hash(a) == sample_hash(b)
    assert a.groupby("cohort_year").size().to_dict() == {2018: 3, 2019: 3, 2020: 4}
    c = stratified_sample(fr, {2018: 3, 2019: 3, 2020: 4}, 43)
    assert sample_hash(a) != sample_hash(c)


def test_ineligible_never_sampled():
    fr = _frame()
    fr.loc[fr["cohort_year"] == 2018, "eligible"] = False
    s = stratified_sample(fr, {2018: 3, 2019: 3, 2020: 4}, 42)
    assert (s["cohort_year"] == 2018).sum() == 0


def _setup(tmp_path, frozen_hash=None):
    (tmp_path / "frame").mkdir()
    (tmp_path / "sample").mkdir()
    fr = _frame()
    fr.to_csv(tmp_path / "frame" / "sampling_frame_all_candidates.csv", index=False)
    (tmp_path / "frame" / "frame_freeze.json").write_text(json.dumps({"frame_sha256": frozen_hash or frame_hash(fr)}))
    raw = {"study": {"random_seed": 42, "per_year_allocation": {2018: 3, 2019: 3, 2020: 4}, "pilot_size": 2,
                     "audit_size": 2},
           "decision_rule": {"days_after_initial_filing": 30},
           "paths": {"frame_dir": "frame", "sample_dir": "sample"}}
    return Config(raw=raw, root=tmp_path)


def test_sample_refuses_when_frame_changed(tmp_path):
    cfg = _setup(tmp_path, frozen_hash="0" * 64)
    assert cli.cmd_sample(cfg, None) == 2


def test_cached_rerun_does_not_change_frozen_sample(tmp_path):
    cfg = _setup(tmp_path)
    assert cli.cmd_sample(cfg, None) == 0
    first = (tmp_path / "sample" / "frozen_sample.csv").read_text()
    assert cli.cmd_sample(cfg, None) == 0
    assert (tmp_path / "sample" / "frozen_sample.csv").read_text() == first
    # tamper with the freeze record -> refusal, file untouched
    f = tmp_path / "sample" / "sample_freeze.json"
    d = json.loads(f.read_text()); d["sample_sha256"] = "x"; f.write_text(json.dumps(d))
    assert cli.cmd_sample(cfg, None) == 2
    assert (tmp_path / "sample" / "frozen_sample.csv").read_text() == first
