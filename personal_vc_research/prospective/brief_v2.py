"""Korean research brief, v2.1 layout.

The top of the brief is a short summary (Stage F) under four separate dimension labels, plus code-generated next
actions. Everything else goes in the appendix: criteria, calculations, support checks, freshness, forecasts, claims
and metadata. Nothing is truncated: long text is rendered as lists, not table cells. Overrides are not suggested.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import assess
from .core import Ctx
from .packs import load_pack

LABEL = {
    "fails_current_screen": "현재 기준 탈락", "passes_current_screen": "현재 기준 통과(사용자 검토 대상)",
    "indeterminate": "판단 보류(미결 기준 있음)", "analysis_failed": "분석 실패(미완료)",
    "sufficient_for_current_conclusion": "현재 결론을 내리기에 충분", "material_gaps": "중요한 정보 공백 있음",
    "extraction_incomplete": "문서 추출 미완료",
    "available_verified": "모집 진행 확인됨", "availability_unknown": "모집 진행 여부 확인 불가",
    "unavailable_or_closed": "마감 또는 철회", "not_checked": "확인하지 않음",
    "eligible": "예산 범위 내", "ineligible": "예산 한도 초과",
    "incomplete_cost_information": "비용 정보 불완전(투자자 수수료 미확인)",
    "pass": "통과", "fail": "탈락", "unresolved": "미결", "unknown": "알 수 없음",
}
CRIT_KO = {
    "BT1_customer_and_revenue_model": "고객·수익 모델", "BT2_demand_evidence": "수요 근거", "BT3_competition": "경쟁",
    "BT4_financial_condition_and_funding": "재무 상태·자금 필요", "BT5_team_evidence": "팀 근거",
    "PC1_security_cash_path": "이 증권의 현금화 경로", "PC2_price_vs_path_to_value": "가격 대비 가치 경로",
    "PC3_investor_rights_and_dilution": "투자자 권리·희석",
}


def _q(ctx, sql, *a):
    return [dict(r) for r in ctx.con.execute(sql, a)]


def _latest_calcs(ctx, analysis_id: int) -> dict:
    rows = _q(ctx, "SELECT * FROM calculations WHERE analysis_id=? ORDER BY calc_id", analysis_id)
    if not rows:
        return {}
    latest = max(r["calculator_version"] for r in rows)
    out = {}
    for r in rows:
        if r["calculator_version"] != latest:
            continue
        cid, ctype = r["calc_type"].split(":", 1)
        out[cid] = {"calc_id": cid, "calc_type": ctype, "formula": r["formula"], "inputs": json.loads(r["inputs"]),
                    "assumptions": json.loads(r["assumptions"] or "[]"), "included_instruments": json.loads(r["included_instruments"] or "[]"),
                    "excluded_instruments": json.loads(r["excluded_instruments"] or "[]"), "units": r["units"],
                    "result_value": r["result_value"], "result_kind": r["result_kind"], "withheld_reason": r["withheld_reason"],
                    "calculator_version": r["calculator_version"]}
    return out


def build_brief_v2(ctx: Ctx, analysis_id: int, out_dir: Path | None = None) -> Path:
    a = _q(ctx, "SELECT * FROM analysis_runs WHERE analysis_id=?", analysis_id)[0]
    asm = _q(ctx, "SELECT * FROM assessments WHERE analysis_id=? ORDER BY assessment_id DESC", analysis_id)[0]
    o = _q(ctx, "SELECT * FROM offerings WHERE offering_id=?", a["offering_id"])[0]
    v = _q(ctx, "SELECT * FROM analyst_versions WHERE version_id=?", a["version_id"])[0]
    comb = json.loads((ctx.root / a["output_path"] / "combined.json").read_text())
    outs = comb["outputs"]
    calcs = _latest_calcs(ctx, analysis_id) or comb.get("calcs") or {}
    pack, _ = load_pack(ctx, a["pack_id"])
    crit = _q(ctx, "SELECT * FROM criterion_results WHERE analysis_id=? ORDER BY row_id", analysis_id)
    checks = _q(ctx, "SELECT * FROM support_checks WHERE analysis_id=? ORDER BY row_id", analysis_id)
    human = [c for c in checks if not c["checker"].startswith("model:")]
    fresh_now = assess.freshness(ctx, a["offering_id"], a["finished_utc"], pack, outs if outs.get("A_extraction") else None)
    res = {"assessment": asm["assessment"], "evidence_completeness": asm["evidence_completeness"],
           "operational_readiness": asm["operational_readiness"], "budget_status": asm["budget_status"],
           "decisive": json.loads(asm["decisive_criteria"]),
           "criteria": [{"criterion_id": c["criterion_id"], "final_result": c["final_result"],
                         "what_would_change_ko": next((x["what_would_change_ko"] for x in (outs.get("D_final") or {}).get("criteria", [])
                                                       if x["criterion_id"] == c["criterion_id"]), "")} for c in crit],
           "extraction_gaps": [g["detail"] for g in pack.get("gaps", [])]}
    actions = assess.next_actions(res, fresh_now)
    dev = a["offering_id"] in json.loads(v["development_offering_ids"])
    f = outs.get("F_brief_ko") or {}
    L: list[str] = [f"# {o['legal_name']} — 연구 브리프 (분석 #{analysis_id})", ""]
    if dev:
        L += ["> **개발 사례(development case).** 이 회사는 분석 규칙(프롬프트·분류기)을 고칠 때 사용되었습니다. "
              "따라서 이 결과는 새 버전의 성능 평가에 쓰이지 않습니다.", ""]
    L += ["| 구분 | 결과 |", "|---|---|",
          f"| 스크리닝 판단 | **{LABEL[asm['assessment']]}** |",
          f"| 증거 완결성 | {LABEL[asm['evidence_completeness']]} |",
          f"| 실행 가능성 | {LABEL[asm['operational_readiness']]} |",
          f"| 예산 | {LABEL[asm['budget_status']]} |", "",
          "_검증되지 않은 연구용 체크리스트에 따른 결과이며 투자 권유가 아닙니다. 분류 규칙은 제안 단계(screening_policy_v1_1, "
          "사용자 확인 전)이고, 기존 정책(v1) 기준 상태는 부록 G에 있습니다._", ""]
    L += ["## 요약", ""]
    if f:
        L += [f"**무엇을 하는 회사인가.** {f['business_one_liner_ko']}", "", f["summary_ko"], "",
              "**결정적 이유**", ""] + [f"- {x}" for x in f["decisive_reasons_ko"]] + [""]
        if f["material_missing_ko"]:
            L += ["**중요한 누락 정보**", ""] + [f"- {x}" for x in f["material_missing_ko"]] + [""]
        L += ["**결론을 바꿀 수 있는 것**", ""] + [f"- {x}" for x in f["what_would_change_ko"]] + [""]
    else:
        if asm["assessment"] == "analysis_failed":
            L += ["요약이 생성되지 않았습니다(분석이 완료되지 않음). 아래 다음 조치를 보세요.", ""]
        else:
            L += ["한국어 요약 단계가 검증을 통과하지 못해 요약을 표시하지 않습니다. 위 판단은 검증을 통과한 A~E 단계 결과로 "
                  "코드가 계산한 것입니다. 기준별 이유는 부록 A에 있습니다.", ""]
            L += ["**결정적 이유**", ""] + ([f"- {x}" for x in json.loads(asm["reasons"])] or ["- 없음(결정적 탈락 기준 없음)"]) + [""]
    L += ["**다음 조치**", ""] + [f"{i}. {x}" for i, x in enumerate(actions, 1)] + [""]
    if f.get("terms_explained_ko"):
        L += ["**용어 풀이**", ""] + [f"- **{t['term']}**: {t['explanation_ko']}" for t in f["terms_explained_ko"]] + [""]

    L += ["---", "", "# 부록", "", "## 부록 A. 기준별 결과", "",
          "모델의 판단(model)과, 코드의 근거 규칙을 적용한 최종 결과(final)를 함께 표시합니다. 탈락은 근거가 확인된 경우에만 "
          "유지되고, 그렇지 않으면 미결로 바뀝니다.", ""]
    dmap = {x["criterion_id"]: x for x in (outs.get("D_final") or {}).get("criteria", [])}
    for c in crit:
        d = dmap.get(c["criterion_id"], {})
        L += [f"### {c['criterion_id']} ({CRIT_KO.get(c['criterion_id'], '')})", "",
              f"- 모델 판단: {LABEL.get(c['model_result'], c['model_result'])} → 최종: **{LABEL[c['final_result']]}** "
              f"(근거 상태: `{c['support']}`)",
              f"- 이유: {c['reason_ko']}",
              f"- 근거 ID: {', '.join(json.loads(c['claim_ids'])) or '없음'}; 반대 근거 ID: {', '.join(d.get('counter_claim_ids', [])) or '없음'}",
              f"- 탈락 근거 유형: {', '.join(d.get('failure_grounds', [])) or '해당 없음'}",
              f"- 결론을 바꿀 수 있는 것: {d.get('what_would_change_ko', '')}",
              f"- 검증 메모: {'; '.join(json.loads(c['validator_notes'] or '[]'))}", ""]
    L += [f"## 부록 B. 결정적 계산 (코드 계산, {next(iter(calcs.values()))['calculator_version'] if calcs else '-'})", "",
          "내재 기업가치(implied equity value)는 공모 가격 × 주식 수의 산술입니다. 가치 평가 의견이 아니며 비교 기업은 쓰지 않았습니다.", ""]
    for k in calcs.values():
        L += [f"### {k['calc_id']} — {k['calc_type']} ({k['result_kind']})", "",
              f"- 결과: {('$' + format(k['result_value'], ',.0f')) if k['result_value'] is not None else '산출 보류'}"
              + (f" — 보류 사유: {k['withheld_reason']}" if k['withheld_reason'] else ""),
              f"- 식: `{k['formula']}` (단위 {k['units']})"]
        for i in k["inputs"]:
            cit = ", ".join(f"doc {x['doc_id']} p.{x['page']}" for x in i["citations"]) or "인용 없음"
            L.append(f"- 입력 {i['name']} = {i['value']:,} {i['unit']} (기준일 {i['as_of'] or '미기재'}; 출처 {i['claim_id']}; {cit})")
        L += [f"- 가정: {x}" for x in k["assumptions"]]
        L += [f"- 포함: {x}" for x in k["included_instruments"]]
        L += [f"- 제외: {x['instrument']} — {x['reason']}" for x in k["excluded_instruments"]] + [""]
    if not calcs:
        L += ["계산 없음.", ""]
    L += ["## 부록 C. 근거 지지 점검", "",
          "**모델 판단(model judgment)이며 검증이 아닙니다.** 인용문이 실제로 존재하는지는 기계적으로 확인했습니다. 아래는 그 인용문이 "
          "주장을 실제로 뒷받침하는지에 대한 모델의 판단입니다.", ""]
    for c in [c for c in checks if c["checker"].startswith("model:")]:
        L += [f"- **{c['claim_id']}**: {c['verdict']} (지지 {c['passage_supports']}, 과장 {c['overstatement']}, 증거 유형 "
              f"{c['evidence_type']}). {c['note']}"
              + (f" 누락된 단서: {c['omitted_qualifications']}" if c["omitted_qualifications"] else "")
              + (f" 상충: {c['conflicts']}" if c["conflicts"] else "")]
    if human:
        L += ["", "**원문 페이지와 직접 대조한 점검(manual spot check, 파이프라인 밖에서 수행)**", ""]
        L += [f"- **{c['claim_id']}** ({c['checker']}; {c['judgment_label']}): {c['verdict']}, 과장 {c['overstatement']} — {c['note']}"
              + (f" 누락된 단서: {c['omitted_qualifications']}" if c["omitted_qualifications"] else "") for c in human]
    L += ["", "## 부록 D. 최신성", ""]
    fz = fresh_now
    L += [f"- 기준 시각: {fz['as_of']}; 분석 완료 {fz['analysis_finished_utc']} (경과 {fz['analysis_age_days']}일)",
          f"- 증거 기준 시점(cutoff): {fz['evidence_cutoff_utc']}",
          f"- 마지막으로 성공한 공시 점검: {fz['last_successful_source_check_utc'] or '없음'}"
          f" (이후 실패 {fz['failed_source_checks_since_last_success']}회)",
          f"- 기준 시점 이후 새 공시: {fz['new_filings_since_cutoff']}",
          f"- 재무제표 기준일: {fz.get('financial_period_end') or '미확인'}"
          + (f" ({fz.get('financial_assurance')}; 기준 시점에서 {fz.get('financial_age_months_at_cutoff')}개월 경과; "
             f"현재 {fz.get('financial_age_months_now')}개월; 오래됨={fz.get('financial_stale')})" if fz.get("financial_period_end") else ""),
          f"- 계약 문서 확보 시각: {', '.join(fz['contract_observed_utc'] or ['없음'])}",
          f"- 모집 진행 관찰: {fz['availability_observation']}",
          f"- 알려진 접근 장애: {'; '.join(fz['known_outages']) or '없음'}", ""]
    L += ["## 부록 E. 예측 (모델 판단, 보정되지 않음)", ""]
    fc = _q(ctx, "SELECT p.*, d.target_type, d.target_scope, d.rationale, d.assumptions, d.cancellation_treatment FROM predictions p JOIN prediction_meta m USING(prediction_id) "
                 "LEFT JOIN forecast_definitions d USING(prediction_id) WHERE m.analysis_id=? ORDER BY prediction_id", analysis_id)
    for p in fc:
        L += [f"### 예측 #{p['prediction_id']}: 확률 {p['probability']:.2f}", "",
              f"- 사건: {p['target_event']}", f"- 대상 유형: {p.get('target_type')}; 범위: {p.get('target_scope')}",
              f"- 마감: {p['deadline_utc']} + 보고 지연 {p['reporting_lag_days']}일; 허용 증거: {p['permitted_evidence']}",
              f"- 근거: {p.get('rationale')}", f"- 가정: {'; '.join(json.loads(p['assumptions'])) if p.get('assumptions') else ''}",
              f"- 미확인 처리: {p['missing_evidence_treatment']}", f"- 취소·철회 처리: {p.get('cancellation_treatment')}",
              "- 사건이 마감 전에 일어나면 조기에 참으로 확정될 수 있습니다. 침묵(공시 없음)은 거짓으로 처리하지 않습니다.", ""]
    if not fc:
        L += ["예측 없음.", ""]
    L += ["## 부록 F. 추출된 주장과 인용", ""]
    for c in _q(ctx, "SELECT * FROM analysis_claims WHERE analysis_id=? ORDER BY row_id", analysis_id):
        cits = json.loads(c["citations"])
        L += [f"- **{c['claim_id']}** [{c['evidence_status']}; {c['claim_type']}; 기간 {c['financial_period'] or '-'}] {c['claim_text']}"]
        L += [f"  - doc {x['doc_id']} p.{x['page']}: \"{x['quote']}\"" for x in cits]
    L += ["", "## 부록 G. 메타데이터", "",
          f"- 분석 버전: {a['version_id']} (prompt {a['prompt_version']}, schema {a['schema_version']}); 분류기 {asm['classifier_version']}",
          f"- 분류 정책: {asm['policy_version']} — 사용자가 확인하기 전까지 제안 단계입니다.",
          f"- 기존 정책(screening_policy_v1) 기준 상태: `{a['status']}` (승인 절차는 이 값을 사용합니다)",
          f"- 증거팩: {a['pack_id']} (sha256 {a['pack_sha256'][:16]}…, 변경 불가)",
          f"- 모델(보고값): {a['model_reported']}; 어댑터 {a['adapter']}; 구분 {a['split']}",
          f"- 실행: {a['started_utc']} → {a['finished_utc']}", ""]
    use = _q(ctx, "SELECT * FROM stage_usage WHERE analysis_id=? ORDER BY row_id", analysis_id)
    if use:
        L += ["| 단계 | 시도 | 초 | 입력 토큰 | 출력 토큰 | 캐시 읽기 | 추정 비용(USD) | 결과 |", "|---|---|---|---|---|---|---|---|"]
        L += [f"| {u['stage']} | {u['attempt']} | {u['seconds']} | {u['input_tokens']} | {u['output_tokens']} | "
              f"{u['cache_read_tokens']} | {u['cost_estimate_usd']} | {u['outcome']} ({u['n_errors']} errors) |" for u in use]
        L += ["", f"비용은 CLI가 보고한 정가 기준 추정치입니다(`{use[0]['cost_label']}`). 구독 사용 시 실제 청구액이 아니며 "
                  "사용 한도에서 차감됩니다.", ""]
    out = out_dir or (ctx.root / ctx.cfg.raw["paths"].get("reports_dir", "reports") / "briefs" / "v2_1")
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"brief_{a['offering_id']}_analysis{analysis_id}.md"
    p.write_text("\n".join(L) + "\n")
    return p
