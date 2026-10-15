"""Spot checks of real-source extraction and citations (evaluation track 1).

For a seeded random sample of claims, plus every claim used for a critical-information item, the cited quote is
re-found in the ORIGINAL snapshot bytes using a different extractor (poppler `pdftotext` for PDFs; raw bytes for XML),
not in the pack text. Results are stored in `citation_checks`. Semantic agreement between claim and quote is checked
separately by a reviewer and recorded with method 'reviewer_semantic'.
"""
from __future__ import annotations

import json
import random
import subprocess

from .analysis import _norm
from .core import Ctx


def _source_text(ctx: Ctx, doc_id: int, page: int, cache: dict) -> str | None:
    d = ctx.con.execute("SELECT blob_path, description FROM documents WHERE document_id=?", (doc_id,)).fetchone()
    if d is None or not d["blob_path"]:
        return None
    path = ctx.root / d["blob_path"]
    if (d["description"] or "").lower().endswith(".pdf"):
        key = (doc_id, page)
        if key not in cache:
            cache[key] = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-layout", str(path), "-"],
                                        capture_output=True, text=True).stdout
        return cache[key]
    return path.read_text(errors="replace")


def check(ctx: Ctx, analysis_id: int, n_random: int = 6, seed: int = 42) -> dict:
    claims = [dict(r) for r in ctx.con.execute("SELECT * FROM analysis_claims WHERE analysis_id=? ORDER BY row_id", (analysis_id,))]
    a = ctx.con.execute("SELECT output_path FROM analysis_runs WHERE analysis_id=?", (analysis_id,)).fetchone()
    combined = json.loads((ctx.root / a["output_path"] / "combined.json").read_text())["outputs"]
    critical_ids = {cid for ci in combined["A_extraction"]["critical_items"] for cid in ci["claim_ids"]}
    cited = [c for c in claims if json.loads(c["citations"])]
    rng = random.Random(seed)
    sample = {c["claim_id"] for c in rng.sample(cited, min(n_random, len(cited)))} | (critical_ids & {c["claim_id"] for c in cited})
    cache, res = {}, {"checked": 0, "found": 0, "not_found": []}
    for c in claims:
        if c["claim_id"] not in sample:
            continue
        for cit in json.loads(c["citations"]):
            src = _source_text(ctx, cit["doc_id"], cit["page"], cache)
            ok = src is not None and _norm(cit["quote"]) in _norm(src)
            ws = (not ok and src is not None
                  and _norm(cit["quote"]).replace(" ", "") in _norm(src).replace(" ", ""))   # extractor spacing differences
            res["checked"] += 1
            res["found"] += ok
            res["found_whitespace_insensitive"] = res.get("found_whitespace_insensitive", 0) + ws
            if not ok and not ws:
                res["not_found"].append({"claim_id": c["claim_id"], "doc_id": cit["doc_id"], "page": cit["page"], "quote": cit["quote"][:80]})
            ctx.con.execute("INSERT INTO citation_checks(analysis_id, claim_id, checked_utc, checker, method, result, note) VALUES (?,?,?,?,?,?,?)",
                            (analysis_id, c["claim_id"], ctx.now(), "automated (software)", "independent_extractor_recheck",
                             "quote_found" if ok else ("quote_found_whitespace_insensitive" if ws else "quote_not_found"),
                             f"doc {cit['doc_id']} p.{cit['page']} via {'pdftotext' if src is not None else 'no source'}"))
    ctx.con.commit()
    return res


def record_semantic(ctx: Ctx, analysis_id: int, claim_id: str, result: str, note: str, checker: str) -> None:
    ctx.con.execute("INSERT INTO citation_checks(analysis_id, claim_id, checked_utc, checker, method, result, note) VALUES (?,?,?,?,?,?,?)",
                    (analysis_id, claim_id, ctx.now(), checker, "reviewer_semantic", result, note))
    ctx.con.commit()
