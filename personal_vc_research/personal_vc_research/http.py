"""Cached, rate-limited, budgeted HTTP fetching with a retrieval manifest.

Every network retrieval is appended to a JSONL manifest (URL, retrieval time, cache path,
SHA-256, status). Cache hits re-use the original retrieval record so provenance is stable
across resumed runs.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from .config import Config


class BudgetExhausted(RuntimeError):
    pass


class MissingUserAgent(RuntimeError):
    pass


@dataclass
class FetchResult:
    url: str
    path: Path | None
    sha256: str | None
    status: int
    retrieved_at_utc: str
    from_cache: bool
    content_type: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200 and self.path is not None

    def text(self, encoding: str = "utf-8") -> str:
        assert self.path is not None
        return self.path.read_bytes().decode(encoding, errors="replace")

    def bytes(self) -> bytes:
        assert self.path is not None
        return self.path.read_bytes()


def utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def cache_key(url: str) -> str:
    parsed = urlparse(url)
    tail = re.sub(r"[^A-Za-z0-9._-]+", "_", parsed.path.rsplit("/", 1)[-1])[-60:] or "index"
    return f"{hashlib.sha256(url.encode()).hexdigest()[:16]}_{tail}"


class Fetcher:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cache_dir = cfg.path("cache_dir")
        self.manifest_path = cfg.path("manifest")
        h = cfg["http"]
        self.rps = h["requests_per_second_by_host"]
        self.max_retries = int(h["max_retries"])
        self.backoff = list(h["backoff_seconds"])
        self.timeout = int(h["timeout_seconds"])
        self.budget = int(h["request_budget_per_command"])
        self.network_requests = 0
        self._last_request: dict[str, float] = {}
        self._manifest: dict[str, dict] = {}
        if self.manifest_path.exists():
            for line in self.manifest_path.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self._manifest[rec["url"]] = rec  # latest record wins
        self.session = requests.Session()

    def _headers(self, url: str) -> dict[str, str]:
        host = urlparse(url).netloc
        if host.endswith("sec.gov"):
            ua = self.cfg.sec_user_agent()
            if not ua:
                raise MissingUserAgent(
                    f"Set ${self.cfg['sources']['sec_user_agent_env']} to 'project-name contact@email' "
                    "per SEC fair-access guidance before fetching from sec.gov."
                )
            return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}
        return {"User-Agent": "personal_vc_research/0.1 (research; non-commercial)"}

    def _throttle(self, host: str) -> None:
        rps = float(self.rps.get(host, self.rps.get("default", 1)))
        wait = (1.0 / rps) - (time.monotonic() - self._last_request.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        self._last_request[host] = time.monotonic()

    def cached(self, url: str) -> FetchResult | None:
        rec = self._manifest.get(url)
        if rec and rec.get("cache_path"):
            p = self.cfg.root / rec["cache_path"]
            if p.exists():
                return FetchResult(url, p, rec["sha256"], rec["status"], rec["retrieved_at_utc"], True,
                                   rec.get("content_type", ""))
        if rec and rec.get("status") in (404, 410):
            return FetchResult(url, None, None, rec["status"], rec["retrieved_at_utc"], True)
        return None

    def get(self, url: str, source_kind: str = "", use_cache: bool = True) -> FetchResult:
        if use_cache:
            hit = self.cached(url)
            if hit is not None:
                return hit
        if self.network_requests >= self.budget:
            raise BudgetExhausted(f"request budget {self.budget} exhausted")
        host = urlparse(url).netloc
        headers = self._headers(url)
        last_exc: Exception | None = None
        resp = None
        for attempt in range(self.max_retries + 1):
            self._throttle(host)
            self.network_requests += 1
            try:
                resp = self.session.get(url, headers=headers, timeout=self.timeout)
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise requests.HTTPError(f"status {resp.status_code}")
                break
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff[min(attempt, len(self.backoff) - 1)])
        retrieved = utcnow_iso()
        if resp is None:
            rec = {"url": url, "status": -1, "error": repr(last_exc), "retrieved_at_utc": retrieved,
                   "cache_path": None, "sha256": None, "source_kind": source_kind}
            self._append(rec)
            return FetchResult(url, None, None, -1, retrieved, False)
        status = resp.status_code
        path = None
        sha = None
        if status == 200:
            body = resp.content
            sha = hashlib.sha256(body).hexdigest()
            path = self.cache_dir / cache_key(url)
            path.write_bytes(body)
        rec = {"url": url, "status": status, "retrieved_at_utc": retrieved,
               "cache_path": str(path.relative_to(self.cfg.root)) if path else None,
               "sha256": sha, "bytes": len(resp.content), "content_type": resp.headers.get("Content-Type", ""),
               "source_kind": source_kind}
        self._append(rec)
        return FetchResult(url, path, sha, status, retrieved, False, rec["content_type"])

    def _append(self, rec: dict) -> None:
        self._manifest[rec["url"]] = rec
        with open(self.manifest_path, "a") as fh:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")
