"""Configuration loading."""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Config:
    raw: dict[str, Any]
    root: Path

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        path = Path(path).resolve()
        with open(path) as fh:
            raw = yaml.safe_load(fh)
        return cls(raw=raw, root=path.parent)

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def path(self, key: str) -> Path:
        p = self.root / self.raw["paths"][key]
        if key.endswith("_dir"):
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def cutoff(self) -> dt.date:
        return dt.date.fromisoformat(self.raw["study"]["outcome_cutoff_utc"])

    @property
    def seed(self) -> int:
        return int(self.raw["study"]["random_seed"])

    @property
    def decision_days(self) -> int:
        return int(self.raw["decision_rule"]["days_after_initial_filing"])

    def sec_user_agent(self) -> str | None:
        ua = os.environ.get(self.raw["sources"]["sec_user_agent_env"], "").strip()
        return ua or None
