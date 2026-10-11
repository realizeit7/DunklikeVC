"""Per-page text access for cached PDFs: native extraction first, targeted OCR only on planned pages.

* Native text (pdfplumber) is extracted for every page and scored with `text_quality`.
* OCR runs only for pages listed in data/manual/ocr_page_plan.csv (batches of <= 10 pages),
  subject to per-offering page caps and a total OCR time budget (config `ocr`).
* Every OCR'd page is cached under data/cache/pages/<sha256>/pNNN.ocr.txt and logged in
  data/tables/ocr_log.csv with batch, rationale and processing seconds.
* Pages never OCR'd and natively unreadable are "not extracted within budget", not "not disclosed".
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pdfplumber
import pypdfium2

from .pdftext import text_quality

READABLE = 0.75


def native_pages(pdf_path: Path, sha256: str, cache_root: Path) -> list[dict]:
    d = cache_root / sha256
    d.mkdir(parents=True, exist_ok=True)
    cp = d / "native.json"
    if cp.exists():
        return json.loads(cp.read_text())
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, pg in enumerate(pdf.pages):
            try:
                t = pg.extract_text() or ""
            except Exception as exc:  # noqa: BLE001
                t = ""
            out.append({"page": i + 1, "text": t, "quality": round(text_quality(t), 3), "n_chars": len(t)})
    cp.write_text(json.dumps(out))
    return out


def ocr_cached(sha256: str, page: int, cache_root: Path) -> str | None:
    p = cache_root / sha256 / f"p{page:03d}.ocr.txt"
    return p.read_text() if p.exists() else None


def _tesseract(png: str) -> str:
    out = subprocess.run(["tesseract", png, "stdout", "--psm", "3"], capture_output=True, timeout=300,
                         env={**os.environ, "OMP_THREAD_LIMIT": "1"})
    return out.stdout.decode("utf-8", errors="replace")


def ocr_batch(pdf_path: Path, sha256: str, pages: list[int], cache_root: Path) -> dict[int, tuple[str, float]]:
    """OCR the given 1-based pages (skipping cached). Returns {page: (text, seconds)} for new pages."""
    import concurrent.futures as cf
    if not shutil.which("tesseract"):
        raise RuntimeError("tesseract not installed")
    (cache_root / sha256).mkdir(parents=True, exist_ok=True)
    todo = [p for p in pages if ocr_cached(sha256, p, cache_root) is None]
    res: dict[int, tuple[str, float]] = {}
    if not todo:
        return res
    with tempfile.TemporaryDirectory() as td:
        doc = pypdfium2.PdfDocument(str(pdf_path))
        pngs = {}
        for p in todo:
            t0 = time.monotonic()
            png = os.path.join(td, f"p{p:03d}.png")
            doc[p - 1].render(scale=2.0).to_pil().save(png)
            pngs[p] = (png, time.monotonic() - t0)
        doc.close()

        def run(p):
            t0 = time.monotonic()
            txt = _tesseract(pngs[p][0])
            return p, txt, time.monotonic() - t0 + pngs[p][1]

        with cf.ThreadPoolExecutor(max_workers=max(1, os.cpu_count() or 2)) as ex:
            for p, txt, secs in ex.map(run, todo):
                (cache_root / sha256 / f"p{p:03d}.ocr.txt").write_text(txt)
                res[p] = (txt, secs)
    return res


def best_page_text(native: list[dict], sha256: str, page: int, cache_root: Path) -> tuple[str, str]:
    """Return (text, method) for a page: native if readable, else cached OCR, else ('', 'not_extracted')."""
    n = native[page - 1]
    if n["quality"] >= READABLE:
        return n["text"], "native"
    o = ocr_cached(sha256, page, cache_root)
    if o is not None:
        return o, "ocr_tesseract"
    return "", "not_extracted_within_budget"


def run_plan(plan_rows: list[dict], docs: dict[str, dict], cache_root: Path, log_path: Path,
             max_pages_per_offering: int, max_total_seconds: float, max_batch: int = 10) -> list[dict]:
    """Execute OCR plan rows: {offering_id, doc_url, batch, pages ('5-10,23'), rationale}.
    docs: doc_url -> {path, sha256}. Appends to log_path; returns new log rows."""
    existing = []
    if log_path.exists():
        with open(log_path) as fh:
            existing = list(csv.DictReader(fh))
    used_secs = sum(float(r["seconds"]) for r in existing if r.get("status") == "ocr_done")
    pages_by_off: dict[str, set] = {}
    for r in existing:
        if r.get("status") == "ocr_done":
            pages_by_off.setdefault(r["offering_id"], set()).add((r["doc_url"], int(r["page"])))
    new_rows = []
    for row in plan_rows:
        pages = parse_pages(row["pages"])
        if len(pages) > max_batch:
            raise ValueError(f"batch larger than {max_batch} pages: {row}")
        doc = docs[row["doc_url"]]
        done = pages_by_off.setdefault(row["offering_id"], set())
        allowed = []
        for p in pages:
            if (row["doc_url"], p) in done or ocr_cached(doc["sha256"], p, cache_root) is not None:
                continue
            if len(done) + len(allowed) >= max_pages_per_offering:
                new_rows.append(_log(row, p, "skipped_offering_page_cap", 0.0, ""))
                continue
            allowed.append(p)
        if allowed and used_secs >= max_total_seconds:
            for p in allowed:
                new_rows.append(_log(row, p, "skipped_total_time_budget", 0.0, ""))
            continue
        out = ocr_batch(Path(doc["path"]), doc["sha256"], allowed, cache_root) if allowed else {}
        for p in allowed:
            txt, secs = out.get(p, ("", 0.0))
            used_secs += secs
            done.add((row["doc_url"], p))
            new_rows.append(_log(row, p, "ocr_done", secs, txt))
    if new_rows:
        write_header = not log_path.exists()
        with open(log_path, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(new_rows[0].keys()))
            if write_header:
                w.writeheader()
            w.writerows(new_rows)
    return new_rows


def _log(row: dict, page: int, status: str, secs: float, txt: str) -> dict:
    return {"offering_id": row["offering_id"], "doc_url": row["doc_url"], "batch": row["batch"],
            "page": page, "rationale": row["rationale"], "status": status, "seconds": round(secs, 2),
            "ocr_chars": len(txt), "ocr_quality": round(text_quality(txt), 3) if txt else "",
            "logged_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def parse_pages(spec: str) -> list[int]:
    out: list[int] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out
