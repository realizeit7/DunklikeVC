"""Short Korean review brief (Markdown) from a validated analysis. Header facts, screening result, budget gate and the
requested user action are deterministic; only the narrative sections come from the LLM."""
from __future__ import annotations

import json
from pathlib import Path

from .core import Ctx, parse_utc

STATUS_KO = {
    "passes_research_screen": "리서치 스크린 통과 — 사용자 검토 대상일 뿐, 투자 권유가 아닙니다",
    "fails_research_screen": "리서치 스크린 불통과",
    "needs_information": "정보 부족 (needs information) — 핵심 정보가 확인되지 않음",
    "analysis_failed": "분석 실패 (출력 검증 실패) — 내용을 신뢰하지 마십시오",
}
GATE_KO = {"evidence_sufficiency": "1. 증거 충분성", "business_thesis": "2. 사업 논리", "price_and_contract": "3. 가격·계약",
           "budget_eligibility": "4. 예산 적격성 (소프트웨어 계산)"}
RESULT_KO = {"pass": "통과", "fail": "불통과", "unknown": "판단 불가"}
EVID_KO = {"issuer_claim": "발행사 주장", "document_supported_fact": "문서로 뒷받침된 사실", "independently_corroborated": "독립 확인",
           "calculation": "계산", "analyst_inference": "분석가 추론", "unverified_assertion": "검증되지 않은 주장"}
CRIT_KO = {"issuer_and_offering_identity": "발행사·공모 식별", "security_type": "증권 종류", "operative_contract": "실제 계약서",
           "price_cap_and_conversion_terms": "가격/상한·전환 조건", "minimum_investment_and_fees": "최소 투자금·수수료",
           "financial_statements_and_dates": "재무제표와 기준일", "closing_or_availability_evidence": "마감/청약 가능 여부"}


def build_brief(ctx: Ctx, analysis_id: int) -> Path:
    a = ctx.con.execute("SELECT * FROM analysis_runs WHERE analysis_id=?", (analysis_id,)).fetchone()
    o = ctx.con.execute("SELECT * FROM offerings WHERE offering_id=?", (a["offering_id"],)).fetchone()
    pack = ctx.con.execute("SELECT * FROM evidence_packs WHERE pack_id=?", (a["pack_id"],)).fetchone()
    combined = json.loads((ctx.root / a["output_path"] / "combined.json").read_text())["outputs"]
    notes = json.loads(a["notes"] or "{}")
    critical = notes.get("critical", {})
    gates = [dict(r) for r in ctx.con.execute("SELECT * FROM analysis_gates WHERE analysis_id=? ORDER BY row_id", (analysis_id,))]
    now = parse_utc(ctx.now())
    age = (now - parse_utc(a["finished_utc"])).days
    newer = ctx.con.execute("SELECT COUNT(*) FROM events WHERE offering_id=? AND observed_utc > ?", (o["offering_id"], pack["cutoff_utc"])).fetchone()[0]
    stale = age > 30 or newer > 0
    contract = critical.get("operative_contract", "not_assessed")
    errors = json.loads(a["validation_errors"] or "[]")
    d = combined.get("D_final") or {}
    bk = d.get("briefing_ko") or {}
    L = [f"# {o['legal_name']} — AI 리서치 브리프 ({o['offering_id']})", "",
         "> 이 문서는 의사결정 보조 자료입니다. 투자 권유가 아니며, AI 판단은 확실성이 아닙니다. 리서치 스크린 통과는 "
         "'사용자 검토 대상'이라는 뜻일 뿐 투자 품질이나 수익성을 의미하지 않습니다.", "",
         "| 항목 | 값 |", "|---|---|",
         f"| 분석일 (analysis date) | {a['finished_utc']} |",
         f"| 증거 기준 시점 (evidence cutoff) | {pack['cutoff_utc']} — 이후 정보는 반영되지 않음 |",
         f"| 모델 (보고된 값) / 프롬프트 / 스키마 / 정책 | {a['model_reported']} / {a['prompt_version']} / {a['schema_version']} / {a['policy_version']} |",
         f"| 증거 팩 (evidence pack) | `{a['pack_id']}` (sha256 {a['pack_sha256'][:12]}…) |",
         f"| 청약 가능 여부 (availability) | **{o['availability_status']}** — 플랫폼 페이지 확인 불가. Form C 마감일 {o['deadline_date']} "
         "(마감일이 남아 있어도 청약 가능을 보장하지 않음) |",
         f"| 계약서 검증 상태 (contract) | {'계약 문구 인용 확인 (AI 판독, 사용자 미검토)' if contract == 'confirmed' else '확인되지 않음'} |",
         f"| 최신성 (staleness) | {'**오래됨(stale)**' if stale else '최신'} — 분석 후 {age}일, 기준 시점 이후 새 공시 {newer}건 |",
         "", "## 한눈에 보기", "",
         f"**AI 스크리닝 결과: {STATUS_KO[a['status']]}**", ""]
    if a["status"] == "analysis_failed":
        L += ["출력이 검증을 통과하지 못했습니다. 오류 (최대 10개):", ""] + [f"* {e}" for e in errors[:10]] + [""]
    else:
        L += [bk.get("summary", ""), ""]
        sections = [("1. 이 회사는 무엇을 하고, 누가 돈을 내는가", "what_it_does"), ("2. 가장 강한 근거", "strongest_evidence"),
                    ("3. 실패할 수 있는 가장 큰 이유", "failure_reasons"),
                    ("4. 이 증권이 투자자에게 현금을 돌려줄 수 있는 경로 (또는 못 돌려주는 이유)", "investor_proceeds_path"),
                    ("5. 가격과 계약에서 중요한 점", "price_and_contract"), ("6. 모르는 것 (unknowns)", "unknowns")]
        for title, k in sections:
            L += [f"## {title}", "", bk.get(k, "_없음_"), ""]
    L += ["## 7. AI 스크리닝 결과 (게이트별, 종합 점수 없음)", "", "| 게이트 | 결과 | 기준·근거 | 남은 불확실성 |", "|---|---|---|---|"]
    for g in gates:
        crit = g["criteria"] or ""
        try:
            crit = "; ".join(json.loads(crit))
        except (json.JSONDecodeError, TypeError):
            pass
        sup = json.loads(g["supporting"] or "[]")
        cnt = json.loads(g["counterevidence"] or "[]")
        L.append(f"| {GATE_KO.get(g['gate'], g['gate'])} | {RESULT_KO[g['result']]} | {crit[:300]} "
                 f"{'(근거 ' + ', '.join(sup) + ')' if sup else ''} {'(반대 근거 ' + ', '.join(cnt) + ')' if cnt else ''} | "
                 f"{(g['uncertainty'] or '')[:200]} |")
    L += ["", "핵심 정보 체크리스트 (소프트웨어 + 인용 검증):", ""]
    for k, v in critical.items():
        L.append(f"* {CRIT_KO.get(k, k)}: {'확인됨' if v == 'confirmed' else ('비차단 미확인 (승인 시 사용자 확인)' if v == 'non_blocking_unknown' else '**미확인**')}")
    if a["status"] != "analysis_failed":
        L += ["", "## 8. 판단을 바꿀 미래 증거", "", bk.get("future_evidence", ""), ""]
        fcs = d.get("forecasts") or []
        if fcs:
            L += ["### 예측 (모델 판단, 보정되지 않음 — model_judgment_uncalibrated)", ""]
            for f in fcs:
                L.append(f"* {f['horizon_months']}개월 · 확률 {f['probability']:.0%} · {f['outcome_definition']} "
                         f"(판정: {f['resolution_evidence']}; 미확인 시: {f['unknown_treatment']})")
        sc = d.get("scenario")
        if sc:
            L += ["", f"### 민감도 시나리오 — {sc['label']}", "", f"가정: {json.dumps(sc['assumptions'], ensure_ascii=False)}", "",
                  sc["explanation_ko"]]
    L += ["", "## 9. 요청하는 사용자 행동", ""]
    if a["status"] == "passes_research_screen":
        L += ["* 원하면 이 브리프와 계약서 페이지를 확인한 뒤 **승인 / 패스 / 보류** 중 하나를 기록하세요. 아무것도 하지 않아도 됩니다 "
              "(주간 3건은 상한이지 할당량이 아님).",
              f"* 승인하려면 금액을 직접 지정해야 합니다 (기본 금액 없음): `python -m prospective approve {o['offering_id']} --amount-usd <금액> "
              f"--fee-usd <수수료 또는 상한> --fee-basis confirmed|upper_bound --issuer-key <확인한 키> --analysis-id {analysis_id} "
              "--min-investment-usd <계약상 최소> --terms \"<적용 조건/티어>\" --availability \"<플랫폼에서 확인한 방법>\" --contract-doc <문서ID>`",
              "* 시스템은 주문을 넣거나 송금하지 않습니다. 실제 투자는 플랫폼에서 직접 하신 뒤 확인서를 기록합니다."]
    elif a["status"] == "needs_information":
        miss = [CRIT_KO.get(k, k) for k, v in critical.items() if v == "not_confirmed"]
        L += [f"* 정보 부족: {', '.join(miss) or '게이트 판단 불가'}. 추가 문서(계약서 등)를 `import-evidence`로 넣고 새 증거 팩으로 재분석하거나, 패스/보류하세요.",
              "* 재정의(override)로 승인하려면 실패 조건과 사유가 기록됩니다. 예산 한도는 재정의할 수 없습니다."]
    elif a["status"] == "fails_research_screen":
        L += ["* 별도 조치 필요 없음. 원하면 패스로 기록하세요. 이 회사도 다른 회사와 동일한 일정으로 계속 추적됩니다."]
    else:
        L += ["* 분석을 다시 실행하세요 (`analyze`). 이 출력은 사용하지 마십시오."]
    L += ["", "## 증거 부록 (evidence appendix)", "",
          "| ID | 유형 | 증거 상태 | 주장 | 출처 (doc/page: 인용) |", "|---|---|---|---|---|"]
    docs = {r["document_id"]: r for r in ctx.con.execute("SELECT document_id, source_url, description FROM documents")}
    for c in ctx.con.execute("SELECT * FROM analysis_claims WHERE analysis_id=? ORDER BY row_id", (analysis_id,)):
        cits = json.loads(c["citations"])
        src = "; ".join(f"[doc {x['doc_id']} p.{x['page']}]({docs[x['doc_id']]['source_url']}): “{x['quote'][:90]}”"
                        for x in cits[:2] if x["doc_id"] in docs)
        L.append(f"| {c['claim_id']} | {c['claim_type']} | {EVID_KO.get(c['evidence_status'], c['evidence_status'])} | "
                 f"{c['claim_text'][:220].replace('|', '/')} | {src.replace('|', '/')} |")
    out = ctx.root / ctx.cfg.raw["paths"]["reports_dir"] / "briefs" / f"brief_{o['offering_id']}_analysis{analysis_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n")
    return out
