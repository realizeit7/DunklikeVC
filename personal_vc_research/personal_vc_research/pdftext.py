"""PDF text extraction with quality detection and OCR fallback.

Order: pdfplumber -> pdftotext (poppler) -> tesseract OCR (if installed). Some Form C PDFs use
custom font encodings that yield glyph soup; those are detected by a letter-ratio heuristic.
Results are cached by document SHA-256 under data/cache/text/.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pdfplumber
import pypdfium2


def text_quality(text: str) -> float:
    """Share of non-space characters that are ASCII letters/digits/common punctuation.
    pdfminer '(cid:NN)' placeholders (unmapped glyphs) count as unreadable."""
    text = re.sub(r"\(cid:\d+\)", "\u0000", text)
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    ok = sum(1 for c in chars if c.isascii() and (c.isalnum() or c in ".,;:$%()-'\"/&"))
    return ok / len(chars)


def _pdfplumber_pages(path: Path) -> list[str]:
    with pdfplumber.open(path) as pdf:
        return [(p.extract_text() or "") for p in pdf.pages]


def _pdftotext_pages(path: Path) -> list[str]:
    if not shutil.which("pdftotext"):
        return []
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, timeout=300)
    return out.stdout.decode("utf-8", errors="replace").split("\f")


def _tesseract(png: str) -> str:
    # OMP_THREAD_LIMIT=1: without it parallel tesseract processes oversubscribe OpenMP threads and
    # stall (first attempt: 300 s timeouts on page 1 of two documents, ~21 min lost, zero pages).
    out = subprocess.run(["tesseract", png, "stdout", "--psm", "3"], capture_output=True, timeout=300,
                         env={**os.environ, "OMP_THREAD_LIMIT": "1"})
    return out.stdout.decode("utf-8", errors="replace")


def _ocr_pages(path: Path, max_pages: int) -> list[str]:
    """Render pages sequentially (pdfium is not thread-safe), OCR them in parallel subprocesses."""
    if not shutil.which("tesseract"):
        return []
    with tempfile.TemporaryDirectory() as td:
        doc = pypdfium2.PdfDocument(str(path))
        pngs = []
        for i in range(min(len(doc), max_pages)):
            png = os.path.join(td, f"p{i:04d}.png")
            doc[i].render(scale=2.0).to_pil().save(png)
            pngs.append(png)
        doc.close()
        with cf.ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 2))) as ex:
            return list(ex.map(_tesseract, pngs))


def extract_pages(path: Path, sha256: str, cache_dir: Path, ocr_max_pages: int = 120,
                  min_quality: float = 0.75) -> dict:
    """Return {"method": str, "quality": float, "pages": [str], "n_pages": int}."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp = cache_dir / f"{sha256}.json"
    if cp.exists():
        return json.loads(cp.read_text())
    result = {"method": "none", "quality": 0.0, "pages": [], "n_pages": 0}
    for method, fn in (("pdfplumber", _pdfplumber_pages), ("pdftotext", _pdftotext_pages)):
        try:
            pages = fn(path)
        except Exception as exc:  # malformed PDFs
            pages = []
            result.setdefault("errors", []).append(f"{method}: {exc!r}")
        q = text_quality("".join(pages))
        if pages and q > result["quality"]:
            result.update(method=method, quality=q, pages=pages, n_pages=len(pages))
        if q >= min_quality:
            break
    if result["quality"] < min_quality:
        try:
            pages = _ocr_pages(path, ocr_max_pages)
            q = text_quality("".join(pages))
            if pages and q > result["quality"]:
                result.update(method="ocr_tesseract", quality=q, pages=pages, n_pages=len(pages))
        except Exception as exc:
            result.setdefault("errors", []).append(f"ocr: {exc!r}")
    cp.write_text(json.dumps(result))
    return result
