"""Bounded page targeting for large or image-only PDFs (v2.1).

1. Page map: low-resolution OCR (100 dpi) of every page, cached by document hash. Used only to locate sections.
2. Targeting: pages whose map text shows contract, financial-statement or offering-terms markers are selected, in
   that priority order, up to a cap.
3. Extraction: selected pages are OCRed again at 200 dpi, also cached. That text is what enters a NEW evidence pack.
   Pages not selected are recorded as unprocessed gaps in that pack.

OCR text can contain recognition errors, and citations must quote it verbatim. The pack labels the document's
extraction method as OCR, so a reader can trace any oddity back to the page.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .core import Ctx

SECTION_PATTERNS = {
    "contract": re.compile(r"SUBSCRIPTION AGREEMENT|CROWD ?SAFE|SIMPLE AGREEMENT FOR FUTURE|OPERATING AGREEMENT|"
                           r"LIMITED LIABILITY COMPANY AGREEMENT|PROMISSORY NOTE|VALUATION CAP|DISCOUNT RATE|"
                           r"THIS INSTRUMENT|CONVERSION PRICE|REVENUE SHARING|INVESTOR SHALL|THE COMPANY HEREBY", re.I),
    "financials": re.compile(r"BALANCE SHEETS?|STATEMENTS? OF OPERATIONS|INCOME STATEMENT|STATEMENTS? OF CASH FLOWS|"
                             r"CHANGES IN MEMBERS|CHANGES IN STOCKHOLDERS|INDEPENDENT ACCOUNTANT|INDEPENDENT AUDITOR|"
                             r"NOTES TO (THE )?FINANCIAL STATEMENTS|TOTAL LIABILITIES|NET (LOSS|INCOME)", re.I),
    "offering_terms": re.compile(r"MINIMUM INVESTMENT|PRICE PER|TARGET OFFERING|MAXIMUM OFFERING|USE OF PROCEEDS|"
                                 r"INVESTOR FEE|TRANSACTION FEE|DEADLINE|SECURITIES BEING OFFERED|DILUTION", re.I),
}
PRIORITY = ["contract", "financials", "offering_terms"]
OCR_FAILED = "\x00OCR_TIMEOUT"


def _ocr_page(pdf: Path, page: int, dpi: int) -> str:
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), "-gray", "-png", str(pdf), f"{d}/p"],
                       check=True, capture_output=True, timeout=300)
        png = next(Path(d).glob("p-*.png"))
        try:
            return subprocess.run(["tesseract", str(png), "-", "--psm", "3"], capture_output=True, text=True, timeout=180,
                                  env={**os.environ, "OMP_THREAD_LIMIT": "1"}).stdout
        except subprocess.TimeoutExpired:
            return OCR_FAILED


def _n_pages(pdf: Path) -> int:
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    return int(re.search(r"Pages:\s+(\d+)", out).group(1))


def ocr_pages(ctx: Ctx, pdf: Path, sha: str, pages: list[int], dpi: int, workers: int = 4) -> dict[int, str]:
    cache = ctx.root / "data" / "text_cache" / f"{sha}_ocr{dpi}.json"
    have = {int(k): v for k, v in json.loads(cache.read_text()).items()} if cache.exists() else {}
    todo = [p for p in pages if p not in have]
    if todo:
        with ThreadPoolExecutor(workers) as ex:
            for p, t in zip(todo, ex.map(lambda q: _ocr_page(pdf, q, dpi), todo)):
                have[p] = t
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({str(k): v for k, v in sorted(have.items())}))
    return {p: have[p] for p in pages}


def target(ctx: Ctx, document_id: int, cap: int = 60) -> dict:
    d = ctx.con.execute("SELECT * FROM documents WHERE document_id=?", (document_id,)).fetchone()
    pdf = ctx.root / d["blob_path"]
    n = _n_pages(pdf)
    pmap = ocr_pages(ctx, pdf, d["sha256"], list(range(1, n + 1)), 100)
    tags = {p: [k for k in PRIORITY if SECTION_PATTERNS[k].search(t)] for p, t in pmap.items()}
    selected: list[int] = []
    for k in PRIORITY:
        for p in sorted(tags):
            if k in tags[p] and p not in selected and len(selected) < cap:
                selected.append(p)
    selected.sort()
    text = {p: t for p, t in ocr_pages(ctx, pdf, d["sha256"], selected, 200).items() if t != OCR_FAILED}
    unprocessed = [p for p in range(1, n + 1) if p not in text]
    failed_map = [p for p, t in pmap.items() if t == OCR_FAILED]
    return {"document_id": document_id, "n_pages": n, "selected": selected, "cap": cap,
            "by_section": {k: [p for p in selected if k in tags[p]] for k in PRIORITY},
            "unprocessed": unprocessed, "page_map_ocr_failed": failed_map, "pages": text,
            "method": f"targeted OCR: tesseract 200 dpi on {len(selected)} of {n} pages selected from a 100-dpi page map "
                      f"(priority contract > financials > offering terms; cap {cap})"}
