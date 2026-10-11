"""Deterministic stratified sampling and freezing."""
from __future__ import annotations

import hashlib
import json
import random

import pandas as pd


def stratified_sample(frame: pd.DataFrame, allocation: dict[int, int], seed: int) -> pd.DataFrame:
    """Sample eligible offerings per cohort year. Deterministic: frame is sorted by offering_id
    and each stratum uses random.Random(f"{seed}-{year}")."""
    elig = frame[frame["eligible"].astype(str).str.lower() == "true"].sort_values("offering_id")
    picks = []
    for year in sorted(allocation):
        pool = elig[elig["cohort_year"].astype(int) == int(year)]["offering_id"].tolist()
        n = min(int(allocation[year]), len(pool))
        rng = random.Random(f"{seed}-{year}")
        picks.extend(rng.sample(pool, n))
    out = elig[elig["offering_id"].isin(picks)].copy()
    out = out.sort_values(["cohort_year", "offering_id"]).reset_index(drop=True)
    order = random.Random(f"{seed}-pilot").sample(list(out["offering_id"]), len(out))
    out["collection_order"] = out["offering_id"].map({oid: i + 1 for i, oid in enumerate(order)})
    return out


def designate(sample: pd.DataFrame, n: int, seed: int, salt: str) -> list[str]:
    ids = sorted(sample["offering_id"])
    return sorted(random.Random(f"{seed}-{salt}").sample(ids, min(n, len(ids))))


def sample_hash(sample: pd.DataFrame) -> str:
    return hashlib.sha256("\n".join(sorted(sample["offering_id"])).encode()).hexdigest()


def write_freeze(path, payload: dict) -> None:
    with open(path, "w") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
