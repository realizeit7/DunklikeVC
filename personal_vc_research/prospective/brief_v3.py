"""Korean research brief for analyst v3 / screening_policy_v1_2.

Layout:
* One research-status notice.
* Top table: policy and state, screening, evidence scope, economic thesis, availability, budget and fees.
* Six sections, then the appendix.
* Decision chains are built by code from the stored rule findings, so every decisive reason carries: rule ID and exact
  text, policy version and state, facts with source/page/date/attribution, interpretation, counterevidence,
  unresolved facts, scope, independence and what would change it.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import assess_v3
from .core import Ctx
from .llm.schemas_v3 import QUESTIONS
from .packs import load_pack

SCREEN_KO = {"provisional_reject": "잠정 거절", "provisional_unresolved": "잠정 미결", "provisional_eligible_for_review": "잠정 검토 대상",
             "reject": "거절", "unresolved": "미결", "eligible_for_review": "검토 대상", "analysis_failed": "분석 실패(미완료)"}
EVID_KO = {"sufficient_for_named_decision": "해당 결론에 한해 충분", "insufficient": "불충분", "conflicting": "상충"}
THESIS_KO = {"supported": "뒷받침됨", "incomplete": "불완전", "contradicted": "반박됨"}
AVAIL_KO = {"available_verified": "모집 진행 확인됨", "availability_unknown": "확인 불가", "unavailable_or_closed": "마감 또는 철회",
            "not_checked": "확인하지 않음"}
FINAL_KO = {"adverse_decisive": "불리 — 단독 결정 사유", "adverse_contributing": "불리 — 기여 요인(단독 결정 아님)",
            "not_adverse": "불리하지 않음", "unknown": "알 수 없음", "not_applicable": "해당 없음"}
SCOPE_KO = {"economic_concern": "경제적 우려", "execution_blocker": "실행 차단 요소", "factual_gap": "사실 공백", "none": "-",
            "preference_breach": "개인 기준 위반"}
QSTAT_KO = {"supported": "근거 있음", "unknown": "알 수 없음", "contradicted": "반박됨",
            "specific_reason_supported": "구체적 근거 있음", "no_substantiated_advantage_identified": "입증된 투자 우위 없음"}
Q_KO = {"Q1_value_creation": "큰 가치를 만들려면 무엇이 맞아떨어져야 하는가", "Q2_next_milestones": "다음 한두 개의 의미 있는 이정표",
        "Q3_advantage_evidence": "주장하는 우위의 근거", "Q4_financing_needed": "이정표까지 필요한 자금",
        "Q5_holder_value_path": "이 증권 보유자가 가치를 받으려면", "Q6_terms_affecting_proceeds": "회수금에 영향을 주는 가격·전환·우선순위·희석·수수료 조건",
        "Q7_vs_schg": "SCHG 대신 이 투자를 고를 구체적 이유"}


def _q(ctx, sql, *a):
    return [dict(r) for r in ctx.con.execute(sql, a)]


def _fact_line(x: dict, docs: dict) -> str:
    cits = "; ".join(f"doc {c['doc_id']} p.{c['page']} \"{c['quote']}\"" for c in x.get("citations", [])) or "(인용 없음/계산)"
    gen = ", ".join(assess_v3.GENERIC_LABEL_KO.get(g, g) for g in x.get("generic_effective", [])) or "없음"
    return (f"  - **{x['claim_id']}** ({'지지' if x['role'] == 'supporting' else '반대'}; 증거 종류 {x.get('evidence_kind')}; "
            f"기준일 {x.get('as_of') or '미기재'}; 출처 주체: {x.get('attribution') or '-'}; 일반적 요인: {gen}; "
            f"모델 지지 점검: {x.get('support_check') or '점검 안 함'}) {x.get('claim_text', '')}\n    - 원문: {cits}")


def chain(r: dict, policy_version: str, policy_state: str, docs: dict) -> list[str]:
    st = "제안·미승인" if policy_state != "active" else "승인됨"
    L = [f"**{r['rule_id']}** — {FINAL_KO[r['final_result']]}",
         f"- 규칙 문구 ({policy_version}, {st}): \"{r['rule_text']}\"",
         f"- 범위: {SCOPE_KO.get(r['scope'], r['scope'])}; 이 사유 단독으로 분류를 결정하는가: {'예' if r['independently_decisive'] else '아니오'}"
         + (f" (판정 근거: {'; '.join(r['validator_notes'])})" if r["validator_notes"] else ""),
         "- 근거 사실:"]
    L += [_fact_line(x, docs) for x in r["facts"]] or ["  - 없음"]
    L += [f"- 해석: {r['interpretation_ko']}", f"- 반대 근거: {r['counterevidence_ko'] or '없음'}",
          f"- 미해결 사실: {r['unresolved_ko'] or '없음'}", f"- 결론을 바꿀 수 있는 것: {r['what_would_change_ko']}", ""]
    return L


def build_brief_v3(ctx: Ctx, analysis_id: int, out_dir: Path | None = None) -> Path:
    a = _q(ctx, "SELECT * FROM analysis_runs WHERE analysis_id=?", analysis_id)[0]
    asm = _q(ctx, "SELECT * FROM assessments_v3 WHERE analysis_id=? ORDER BY assessment_id DESC", analysis_id)[0]
    o = _q(ctx, "SELECT * FROM offerings WHERE offering_id=?", a["offering_id"])[0]
    v = _q(ctx, "SELECT * FROM analyst_versions WHERE version_id=?", a["version_id"])[0]
    comb = json.loads((ctx.root / a["output_path"] / "combined.json").read_text())
    outs = comb["outputs"]
    pack, _ = load_pack(ctx, a["pack_id"])
    docs = {d["doc_id"]: d for d in pack["documents"]}
    rows = _q(ctx, "SELECT * FROM rule_findings WHERE analysis_id=? ORDER BY row_id", analysis_id)
    for r in rows:
        r["facts"] = json.loads(r["facts"])
        r["validator_notes"] = json.loads(r["validator_notes"] or "[]")
        r["independently_decisive"] = bool(r["independently_decisive"])
        r["counterevidence_ko"] = r.pop("counterevidence")
        r["independent_rejection_allowed"] = r["final_result"] != "not_applicable"
    budget, execution = json.loads(asm["budget"]), json.loads(asm["execution"])
    pstate = asm["policy_state"]
    f = outs.get("F_brief_ko") or {}
    dev = a["offering_id"] in json.loads(v["development_offering_ids"])
    L = [f"# {o['legal_name']} — 연구 브리프 (분석 #{analysis_id}, 분석기 v3)", ""]
    L += ["> **연구 상태:** " + ("제안된 정책에 따른 잠정 분류. " if pstate != "active" else "승인된 정책에 따른 분류. ")
          + "검증되지 않은 연구용 점검표의 결과이며 투자 권유나 수익 예측이 아닙니다."
          + (" 이 회사는 규칙을 다듬는 데 쓰인 개발 사례라 성능 평가에 쓰이지 않습니다." if dev else ""), ""]
    fee = ("투자자 부담 수수료 미확인 → 총비용 확인 불가(수수료 0으로 가정하지 않으며 예산 초과도 아님)"
           if not budget.get("total_cost_verifiable") else "수수료 확인됨")
    L += ["| 구분 | 결과 |", "|---|---|",
          f"| 정책 | {asm['policy_version']} ({'제안·미승인' if pstate != 'active' else '승인됨'}; sha256 {asm['policy_sha256'][:12]}…) |",
          f"| 스크리닝 | **{SCREEN_KO[asm['screening']]}** |",
          f"| 증거 | {EVID_KO[asm['evidence_status']]} |",
          f"| 투자 논리(경제성) | {THESIS_KO[asm['thesis_status']]} |",
          f"| 모집 진행 | {AVAIL_KO.get(execution['availability'], execution['availability'])} |",
          f"| 예산·수수료 | 연간 잔여 {budget['annual_remaining_usd']}, 발행사 잔여 {budget['issuer_remaining_usd']}; {fee} (확인 {budget['checked_utc']}) |",
          "", f"_증거 범위: {asm['evidence_scope']}_", ""]
    L += ["## 1. 회사가 하는 일", "", f.get("company_ko") or "(요약 단계가 검증을 통과하지 못했습니다. 부록의 주장 목록을 보세요.)", ""]
    th = {t["question_id"]: t for t in _q(ctx, "SELECT * FROM thesis_answers WHERE analysis_id=?", analysis_id)}
    L += ["## 2. 이 투자가 성공할 수 있는 이유", "", f.get("why_could_work_ko") or "", ""]
    if "Q7_vs_schg" in th:
        L += [f"**SCHG 대비:** {QSTAT_KO.get(th['Q7_vs_schg']['status'], th['Q7_vs_schg']['status'])} — {th['Q7_vs_schg']['answer_ko']}", ""]
    dec = [r for r in rows if r["independently_decisive"]]
    contrib = [r for r in rows if r["final_result"] == "adverse_contributing"]
    L += ["## 3. 결정적 우려", ""]
    if dec:
        for r in dec:
            L += chain(r, asm["policy_version"], pstate, docs)
    else:
        L += ["단독으로 분류를 결정하는 검증된 사유는 없습니다.", ""]
    prefs = json.loads(asm["notes"] or "{}").get("preferences", [])
    for p in prefs:
        if p["breached"] == "yes":
            L += [f"**{p['pref_id']} (개인 기준 위반, 단독 결정)** — \"{p['text']}\" — 근거: {p['basis']}", ""]
    if contrib:
        L += ["**결정적이지 않은 불리한 요인** (사라지지 않고 남아 있으나 단독으로 거절 사유가 되지 않음):", ""]
        L += [f"- {r['rule_id']}: {r['interpretation_ko']} (판정: {'; '.join(r['validator_notes'])})" for r in contrib] + [""]
    L += ["## 4. 중요한 미확인 사항", ""]
    L += [f"- {x}" for x in f.get("unknowns_ko", [])]
    L += [f"- {r['rule_id']}(알 수 없음): {r['unresolved_ko']}" for r in rows if r["final_result"] == "unknown" and r["unresolved_ko"]] + [""]
    L += ["## 5. 결론을 바꿀 수 있는 것", ""] + [f"- {x}" for x in f.get("what_would_change_ko", [])] + [""]
    res = {"screening": asm["screening"], "decisive": json.loads(asm["decisive"]),
           "findings": [{**r, "independent_rejection_allowed": True} for r in rows]}
    L += ["## 6. 다음 조치", ""] + [f"{i}. {x}" for i, x in enumerate(assess_v3.next_actions(res, pack), 1)] + [""]

    L += ["---", "", "# 부록", "", "## 부록 A. 투자 논리 7문항 (모델 답변, 인용 포함)", ""]
    for q in QUESTIONS:
        t = th.get(q)
        if t:
            L += [f"- **{Q_KO[q]}** — {QSTAT_KO.get(t['status'], t['status'])}: {t['answer_ko']} (근거 {', '.join(json.loads(t['claim_ids'])) or '없음'})"]
    L += ["", f"판정: {THESIS_KO[asm['thesis_status']]} — " + "; ".join(json.loads(asm["thesis_notes"] or "[]")), "",
          "## 부록 B. 규칙별 결정 사슬 (전체)", ""]
    for r in rows:
        L += chain(r, asm["policy_version"], pstate, docs)
    L += ["## 부록 C. 결정적 계산 (코드 계산)", "", "내재 기업가치는 가격×주식 수의 산술이며 고평가 판단이 아닙니다. 회사 가치와 투자자 현금 회수는 다릅니다.", ""]
    allc = _q(ctx, "SELECT * FROM calculations WHERE analysis_id=? ORDER BY calc_id", analysis_id)
    latest_cv = max((k["calculator_version"] for k in allc), default="")
    if len({k["calculator_version"] for k in allc}) > 1:
        L += [f"_계산은 최신 계산기 {latest_cv} 기준입니다. 이전 버전 행도 기록에 남아 있습니다._", ""]
    for k in [k for k in allc if k["calculator_version"] == latest_cv]:
        L += [f"- **{k['calc_type']}** ({k['result_kind']}, {k['calculator_version']}): "
              + (f"{k['result_value']:,.1f} {k['units']}" if k["result_value"] is not None else "산출 보류")
              + (f" — 보류 사유: {k['withheld_reason']}" if k["withheld_reason"] else "")]
        for i in json.loads(k["inputs"] or "[]"):
            L.append(f"  - 입력 {i.get('name')} = {i.get('value')} (기준일 {i.get('as_of') or i.get('period_end') or '-'}; 출처 {i.get('claim_id')})")
        L += [f"  - 가정/메모: {x}" for x in json.loads(k["assumptions"] or "[]")]
        L += [f"  - 제외: {x['instrument']} — {x['reason']}" for x in json.loads(k["excluded_instruments"] or "[]")]
    L += ["", "## 부록 D. 근거 지지 점검", "", "모델 판단이며 독립 검증이 아닙니다. 인용문의 실재는 기계적으로 확인했고, 아래는 의미상 지지 여부입니다.", ""]
    for c in _q(ctx, "SELECT * FROM support_checks WHERE analysis_id=? ORDER BY row_id", analysis_id):
        L.append(f"- **{c['claim_id']}** [{c['checker']}; {c['judgment_label']}]: {c['verdict']} (과장 {c['overstatement']}). {c['note']}"
                 + (f" 누락된 단서: {c['omitted_qualifications']}" if c["omitted_qualifications"] else ""))
    L += ["", "## 부록 E. 실행·예산", "", f"- 투자 전 필요: {', '.join(execution['required_before_any_investment'])}",
          f"- 예산(budget_policy_v1, 투자자 수수료 포함): 기간 {budget['period']}, 연간 잔여 {budget['annual_remaining_usd']}, "
          f"발행사 {budget['issuer_key']} 잔여 {budget['issuer_remaining_usd']}, 최소 투자금 {budget.get('minimum_investment_usd')}, "
          f"투자자 수수료 {budget['investor_fee_status']}. {budget['note']}", "", "## 부록 F. 추출된 주장", ""]
    for c in _q(ctx, "SELECT * FROM analysis_claims WHERE analysis_id=? ORDER BY row_id", analysis_id):
        meta = json.loads(c["calculation_inputs"] or "{}")
        L.append(f"- **{c['claim_id']}** [{c['evidence_status']}; {meta.get('evidence_kind')}; {','.join(meta.get('dimensions', []))}; "
                 f"{meta.get('attribution', '')}; {meta.get('as_of') or '-'}] {c['claim_text']}")
        L += [f"  - doc {x['doc_id']} p.{x['page']}: \"{x['quote']}\"" for x in json.loads(c["citations"])]
    notes = json.loads(a["notes"] or "{}")
    L += ["", "## 부록 G. 메타데이터", "",
          f"- 분석 버전 {a['version_id']} (prompt {a['prompt_version']}, schema {a['schema_version']}, {notes.get('pipeline_version')}); "
          f"분류기 {asm['classifier_version']}",
          f"- 정책 {asm['policy_version']} sha256 {asm['policy_sha256']} — 상태 {pstate}",
          f"- 증거팩 {a['pack_id']} (sha256 {a['pack_sha256'][:16]}…), cutoff {pack['cutoff_utc']}",
          f"- 모델(보고값) {a['model_reported']}; 실행 {a['started_utc']} → {a['finished_utc']}; 구분 {a['split']}",
          f"- analysis_runs.status = `{a['status']}` (자리 표시 값: v3 결과는 승인 절차에 쓰이지 않음)", ""]
    use = _q(ctx, "SELECT * FROM stage_usage WHERE analysis_id=? ORDER BY row_id", analysis_id)
    if use:
        L += ["| 단계 | 시도 | 초 | 출력 토큰 | 추정 비용(USD) | 결과 |", "|---|---|---|---|---|---|"]
        L += [f"| {u['stage']} | {u['attempt']} | {u['seconds']} | {u['output_tokens']} | {u['cost_estimate_usd']} | {u['outcome']} |" for u in use]
        L += ["", "비용은 CLI가 보고한 정가 기준 추정치이며 구독 사용 시 실제 청구액이 아닙니다.", ""]
    out = out_dir or (ctx.root / ctx.cfg.raw["paths"].get("reports_dir", "reports") / "briefs" / "v2_2")
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"brief_{a['offering_id']}_analysis{analysis_id}.md"
    p.write_text("\n".join(L) + "\n")
    return p
