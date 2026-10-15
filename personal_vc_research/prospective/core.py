"""Run context, content-addressed snapshot store, gap logging, scheduling and the pilot clock."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

from personal_vc_research.config import Config
from personal_vc_research.http import Fetcher, FetchResult, utcnow_iso

from . import db

UTC = dt.timezone.utc


def parse_utc(s: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def iso(d: dt.datetime) -> str:
    return d.astimezone(UTC).replace(microsecond=0).isoformat()


def norm_utc(s: str) -> str:
    """Normalize any ISO timestamp (or date) to the canonical 'YYYY-MM-DDTHH:MM:SS+00:00' string."""
    if len(s) == 10:
        s += "T00:00:00+00:00"
    return iso(parse_utc(s))


class Ctx:
    """One CLI invocation: config, database connection, fetcher, run record."""

    def __init__(self, config_path: str | Path, command: str, now: str | None = None, offline: bool = False):
        self.cfg = Config.load(config_path)
        self.root = self.cfg.root
        self.con = db.connect(self.cfg.path("db"), self.cfg.root / self.cfg.raw["paths"].get("backups_dir", "data/backups"))
        self.fetcher = None if offline else Fetcher(self.cfg)
        self._now = now
        self.run_id = f"{command}-{dt.datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
        self.command = command
        self.cache_hits = 0
        self.errors = 0
        sha = hashlib.sha256(Path(config_path).read_bytes()).hexdigest()[:16]
        self.con.execute("INSERT INTO runs(run_id, command, started_utc, config_sha, status) VALUES (?,?,?,?,?)",
                         (self.run_id, command, self.now(), sha, "running"))
        self.con.commit()

    def now(self) -> str:
        return norm_utc(self._now) if self._now else utcnow_iso()

    # ---- fetching -------------------------------------------------------------------------
    def fetch(self, url: str, kind: str, use_cache: bool = True, log_gap: bool = True) -> FetchResult:
        assert self.fetcher is not None, "offline context"
        r = self.fetcher.get(url, source_kind=kind, use_cache=use_cache)
        if r.from_cache:
            self.cache_hits += 1
        if r.status != 200 and log_gap:
            self.errors += 1
            self.gap("access_blocked" if r.status in (401, 403, 429, 525) else "http_error", url,
                     f"HTTP {r.status}")
        return r

    def gap(self, kind: str, url: str = "", detail: str = "", offering_id: str = "") -> None:
        self.con.execute("INSERT INTO gaps(run_id, utc, offering_id, kind, url, detail) VALUES (?,?,?,?,?,?)",
                         (self.run_id, self.now(), offering_id, kind, url, detail))

    # ---- snapshots ------------------------------------------------------------------------
    def store_blob(self, data: bytes) -> tuple[str, str]:
        sha = hashlib.sha256(data).hexdigest()
        rel = Path(self.cfg.raw["paths"]["blobs_dir"]) / sha[:2] / sha
        p = self.root / rel
        if not p.exists():  # identical content shares bytes; existing blobs are never overwritten
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        return sha, str(rel)

    def record_document(self, *, url: str, source_type: str, offering_id: str = "", issuer_cik: str = "",
                        accession: str = "", data: bytes | None = None, retrieved_utc: str | None = None,
                        http_status: int = 200, content_type: str = "", claimed_publication_date: str = "",
                        verified_public_date: str = "", description: str = "", visibility: str = "public",
                        extraction_method: str = "", parse_status: str = "", access_error: str = "",
                        blob_override: tuple[str, str] | None = None) -> int:
        """Append one retrieval/check record. Returns document_id."""
        retrieved = retrieved_utc or self.now()
        sha = blob = None
        size = None
        if data is not None:
            sha, blob = blob_override or self.store_blob(data)
            size = len(data)
        prev = self.con.execute(
            "SELECT MIN(first_observed_utc) FROM documents WHERE source_url=? AND sha256 IS ? AND sha256 IS NOT NULL",
            (url, sha)).fetchone()[0]
        first = prev or retrieved
        cur = self.con.execute(
            """INSERT INTO documents(offering_id, issuer_cik, accession, source_url, source_type, visibility, description,
               claimed_publication_date, verified_public_date, retrieved_utc, first_observed_utc, sha256, blob_path, bytes,
               content_type, http_status, extraction_method, parse_status, access_error, run_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (offering_id, issuer_cik, accession, url, source_type, visibility, description, claimed_publication_date,
             verified_public_date, retrieved, first, sha, blob, size, content_type, http_status, extraction_method,
             parse_status, access_error, self.run_id))
        return cur.lastrowid

    def snapshot_url(self, url: str, source_type: str, use_cache: bool = True, **kw) -> tuple[int, FetchResult]:
        r = self.fetch(url, source_type, use_cache=use_cache)
        data = r.bytes() if r.ok else None
        # a cache hit keeps the ORIGINAL retrieval time: the content was observed then, not now
        doc_id = self.record_document(url=url, source_type=source_type, data=data,
                                      retrieved_utc=norm_utc(r.retrieved_at_utc), http_status=r.status,
                                      content_type=r.content_type, access_error="" if r.ok else f"HTTP {r.status}", **kw)
        return doc_id, r

    # ---- offering state -------------------------------------------------------------------
    def set_offering(self, offering_id: str, evidence: str = "", **fields) -> None:
        row = self.con.execute("SELECT * FROM offerings WHERE offering_id=?", (offering_id,)).fetchone()
        for k, v in fields.items():
            old = row[k] if row is not None else None
            if str(old) != str(v):
                self.con.execute("INSERT INTO offering_status_log(offering_id, utc, run_id, field, old_value, new_value, evidence)"
                                 " VALUES (?,?,?,?,?,?,?)", (offering_id, self.now(), self.run_id, k, old, v, evidence))
        sets = ", ".join(f"{k}=?" for k in fields)
        self.con.execute(f"UPDATE offerings SET {sets} WHERE offering_id=?", (*fields.values(), offering_id))

    def finish(self, status: str = "ok", notes: str = "") -> None:
        n = self.fetcher.network_requests if self.fetcher else 0
        self.con.execute("UPDATE runs SET finished_utc=?, network_requests=?, cache_hits=?, errors=?, status=?, notes=? "
                         "WHERE run_id=?", (self.now(), n, self.cache_hits, self.errors, status, notes, self.run_id))
        self.con.commit()


# ---- scheduling (identical for selected, passed, deferred and unreviewed offerings) ----------
def next_check_due(availability_status: str, closing_status: str, last_check_utc: str, cfg: Config) -> str:
    """Due date depends ONLY on availability/closing state, never on any decision."""
    s = cfg["schedule"]
    closed = closing_status in ("close_reported_c_u", "withdrawn_c_w") or availability_status in ("closed_reported", "withdrawn")
    days = s["followup_days_after_close"] if closed else s["change_check_days_open_or_unknown"]
    return iso(parse_utc(last_check_utc) + dt.timedelta(days=int(days)))


# ---- pilot clock -------------------------------------------------------------------------
def clock_path(cfg: Config) -> Path:
    return cfg.root / "pilot_clock.json"


def get_clock(ctx: Ctx) -> dict:
    rows = {r["key"]: r["value"] for r in ctx.con.execute("SELECT key, value FROM pilot_clock")}
    if not rows and clock_path(ctx.cfg).exists():  # restore the committed clock into a fresh database
        saved = json.loads(clock_path(ctx.cfg).read_text())
        for k, v in saved.items():
            ctx.con.execute("INSERT INTO pilot_clock(key, value, set_utc, run_id) VALUES (?,?,?,?)",
                            (k, v, saved.get("pilot_start_utc", ""), "restored_from_pilot_clock_json"))
        ctx.con.commit()
        rows = saved
    return rows


def start_clock(ctx: Ctx, start_utc: str) -> dict:
    """Set the pilot clock once (first successful live discovery). Never backdated, never reset."""
    existing = get_clock(ctx)
    if existing:
        return existing
    start = parse_utc(start_utc)
    tz = ZoneInfo(ctx.cfg["pilot"]["timezone"])
    end = start + dt.timedelta(days=int(ctx.cfg["pilot"]["duration_days"]))
    clock = {"pilot_start_utc": iso(start), "pilot_start_local_date": start.astimezone(tz).date().isoformat(),
             "pilot_end_utc": iso(end), "pilot_end_local_date": end.astimezone(tz).date().isoformat(),
             "timezone": ctx.cfg["pilot"]["timezone"], "set_by_run": ctx.run_id}
    for k, v in clock.items():
        ctx.con.execute("INSERT INTO pilot_clock(key, value, set_utc, run_id) VALUES (?,?,?,?)", (k, v, ctx.now(), ctx.run_id))
    clock_path(ctx.cfg).write_text(json.dumps(clock, indent=2) + "\n")
    return clock


def copy_private(src: Path, cfg: Config) -> Path:
    d = cfg.root / cfg.raw["paths"]["private_dir"]
    d.mkdir(parents=True, exist_ok=True)
    dst = d / src.name
    shutil.copy2(src, dst)
    return dst
