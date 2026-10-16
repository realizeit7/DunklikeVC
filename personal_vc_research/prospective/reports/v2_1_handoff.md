# v2.1 handoff — Republic access and brief quality

Branch `v2.1-republic-briefs` (from `llm-analyst-v2`). Local commits only; **not pushed**. Nothing was deployed or
purchased, no one was contacted, and no investment, approval or ledger entry was made. The investment policy and
budget policy are unchanged; the screening change is a **proposal** that awaits your acknowledgment.

## Results

**A. Republic access** (`reports/republic_access_assessment.md`, `reports/republic_access_attempts.csv`)
- Plain HTTP and an ordinary headless Chromium both get a Cloudflare block page (403) for the two campaign URLs.
- This environment has no integration with your own browser. Whether the pages are public from a home browser is not
  determined (likely, but unverified).
- The Wayback API has no snapshots. Issuer websites are reachable, and all three claim the raise is live; those are
  unverified issuer claims.
- **Recommended route:** you save the page in your own browser and import it with `import-evidence`. Template and
  Korean/English steps: `templates/republic_manual_import/`, and §5 of the assessment.
- The importer now refuses block, challenge, login and error pages and cookie, HAR and token files. Captures made
  while logged in are stored privately.

**B. Brief quality**
- **Four separate dimensions** (table `assessments`): assessment, evidence completeness, operational readiness,
  budget.
- **Per-criterion results with code support rules.** A failure must have a decisive ground, valid evidence, and a
  support check that did not reject it.
- **Deterministic calculations** (`calc.py`, K-ids) with provenance. Authorized shares are never used, convertibles
  with unknown terms withhold the fully diluted figure, and SAFEs get no per-share math.
- **Structured support check** (stage E, labelled model judgment), plus **manual source comparisons** (20 rows: Hope-Neuron 10, Mightylicious 6, TradeFunded 4;
  labelled `manual_source_comparison_by_assistant_not_user`).
- **Freshness.** "No new filings" is shown only for an interval covered by a successful EDGAR check. All three had a
  successful check on 2026-10-15 and no new filings.
- **Korean brief.** A dimension table, then the summary, decisive reasons, missing information, what would change
  the result, and code-ranked next actions; everything else is in the appendix. Nothing is truncated, and overrides
  are not suggested.
- **FORECAST_V2:** one event per forecast, target type, explicit deadline, cancellation treatment, and silence never
  false. Old compound forecast #4 is flagged in `forecast_lineage`; the original is unchanged.
- **Capped targeted repair**, with original and repaired outputs both kept. Per-stage usage is in `stage_usage`; cost
  is an estimate, not billed.
- **Targeted OCR** for image PDFs. TradeFunded: 60 of 172 pages, with the unprocessed pages recorded.

**Development-case results** (all three were used to design v2.1, so they are not evaluation evidence):

| Company | Run | Assessment | Evidence | Availability | Budget | Decisive |
|---|---|---|---|---|---|---|
| Hope-Neuron | 10 (same frozen pack as runs 2–3) | fails_current_screen | sufficient | unknown | incomplete cost info | BT4, PC1, PC3 |
| Mightylicious | 11 → 12 (replay, no model call) | fails_current_screen | sufficient | unknown | incomplete cost info | BT4, PC1, PC3 |
| TradeFunded | 13 (CLI error) → 14 (new OCR pack) | fails_current_screen | **extraction incomplete** | unknown | incomplete cost info | PC1, PC3 |

## Defects found during the runs (all fixed in code, original rows kept)

| Defect | Fix |
|---|---|
| Korean validator counted English in parentheses | validator 0_2 |
| Investor fee "confirmed" from the issuer-paid fee | classifier v2_1_1 |
| A Korean-summary failure voided a valid assessment | pipeline 0_2 + `replay-v2` |
| SAFE $1 unit × common shares shown as equity | calculator v1_1 + `recalc` |
| Supported failure hid unread pages | classifier v2_1_2 |
| CLI error text was not kept | adapter |
| Page classifier flagged a Shopify page's captcha script as a challenge | page_classifier_v2 |

Still open (prompt-level, next version):
- Stage A should list conflicting share counts (Hope-Neuron shows 1 vs 75,000,001 shares, so K1 should be
  `illustrative`).
- Stage A should separate issuer-paid fees from investor-paid fees.
- "either X" slips past the no-"or" forecast check.

## Decisions that are yours

1. **Acknowledge or amend `policies/screening_policy_v1_1_PROPOSED.md`.** Until you do, approvals use policy v1.
2. **PC1/PC3 failed in all three cases**, mostly on standard Reg CF terms, so they do not discriminate. Should they
   be judged relative to the standard form (my suggestion), made informational, or kept?
3. **BT4 threshold:** is going-concern language plus negative equity enough for a fail at the pre-revenue stage?
4. For a live decision, **import the Republic page from your browser** and check the unread TradeFunded Operating
   Agreement pages.

## Tests and files

- **Tests:** 129 in the full suite. New tests are in `tests/prospective/test_v21.py`; they cover every item on the
  spec's test list, and the existing budget and ledger tests still pass.
- **Reports:**
  - `reports/v2_1_hope_neuron_before_after.md`
  - `reports/v2_1_development_cases.md` (including usage accounting)
- **Briefs:** `reports/briefs/v2_1/`.
- **Guide:** `V2_1_GUIDE.md`.
- **Data dictionary:** the v2.1 section of `DATA_DICTIONARY.md`.
- **Model-call usage:** v2.1 used 40 stage calls (34 live), 318,589 output tokens, about 34 minutes, and an
  estimated $16.06 (CLI list-price equivalent; your subscription is not billed this amount).

## Revised Hope-Neuron top summary (analysis 10, brief v2.1)

| 구분 | 결과 |
|---|---|
| 스크리닝 판단 | **현재 기준 탈락** |
| 증거 완결성 | 현재 결론을 내리기에 충분 |
| 실행 가능성 | 모집 진행 여부 확인 불가 |
| 예산 | 비용 정보 불완전(투자자 수수료 미확인) |

_검증되지 않은 연구용 체크리스트에 따른 결과이며 투자 권유가 아닙니다. 분류 규칙은 제안 단계(screening_policy_v1_1, 사용자 확인 전)이고, 기존 정책(v1) 기준 상태는 부록 G에 있습니다._

## 요약

**무엇을 하는 회사인가.** Hope-Neuron Therapeutx는 ALS(루게릭병)를 겨냥한 기기 기반 세포치료(SELtx)를 개발하는 매출 전 단계 회사이며, 향후 환자·클리닉 등이 치료비를 내는 구조를 계획하지만 실제 지불 주체는 아직 특정되지 않았습니다.

현재 점검표(검증되지 않은 연구용 체크리스트) 기준의 화면 결과는 '현 단계 심사 불통과'입니다. 이는 투자 조언이 아니라, 제출된 자료만으로 살펴본 결과입니다. 근거 자료는 현재 결론을 내리기에 충분하다고 판단되었고, 모집이 실제로 진행 중인지는 확인되지 않았습니다.

결정적 이유는 세 가지입니다. 첫째, 재무 상태입니다. 2025-12-31 감사 재무제표상 현금은 $19,213, 총부채는 $268,348이고 이 중 $199,875는 창업자에게 갚을 돈입니다. 매출은 0이고 순손실은 $56,126이며, 회사 위험요소에도 계속기업(going concern) 불확실성이 적혀 있습니다 [A13][A15][A18]. 2026-06-18 현금 $160,487은 회사가 제시한 단독 수치입니다. 지출 자료가 2025년 것뿐이어서 현재 런웨이는 계산하지 않았습니다.

둘째, 현금화 경로입니다. 보통주에는 배당 약속, 환매권, 상장이 없습니다. 1년 양도제한이 있고 그 이후에도 제한이 이어질 수 있으며, 시장이 생긴다는 보장도 없습니다 [A9]. 후속 Reg A 공모로 전환될 수 있다는 것은 회사의 '관심'일 뿐 보장이 없습니다 [A32]. 투자자는 수탁기관을 통해 간접 보유할 수 있습니다 [A31].

셋째, 투자자 권리와 희석입니다. 투자자는 10년간 취소할 수 없는 의결권 위임을 집행의장에게 해야 하고 [A7], 희석 방지 권리가 없습니다 [A8]. 창업자가 투자 전 의결권 100%를 가집니다 [A11]. 전환 조건이 공개되지 않은 전환사채 2건과 계획 중인 $50,000 노트도 희석 요인이 될 수 있습니다 [A19][A22][B2].

판단을 보류한 항목도 있습니다. 수익모델은 회사 추정일 뿐입니다 [A26]. 수요 증거로는 마우스 실험(p=0.008)만 있고 표본 수·설계·대조군이 없습니다 [A25]. IRB 승인, FDA IND, 첫 투약도 확인되지 않습니다 [A24]. 경쟁 우위는 독립 출처가 없고 [A27], 팀의 임상·규제 이력도 문서에 없습니다 [A30]. 가격 $1.00은 '임의' 결정이라는 공시일 뿐 고평가의 증거가 아닙니다. 발행주식 75,000,001주 기준 산술상 약 $75.0M입니다 [K1]. 다만 감사 대차대조표에는 1주만 나와 있고, K4는 전환 조건이 없어 계산되지 않았습니다.

결론을 바꿀 자료로는 월별 지출과 최신 검증 현금, 구속력 있는 추가 자금 약정, 헌장과 전환사채의 구체 조건, 의결권 위임 완화, 마우스 연구 상세와 규제 진행 문서, 임상 계약이 있습니다.

**결정적 이유**

- 2025-12-31 감사 기준 현금 $19,213 대비 부채 $268,348(창업자 채무 $199,875 포함), 매출 0, 계속기업 불확실성 명시 [A13][A15][A18]
- 배당·환매·상장 약속이 없고 1년 양도제한 등 제한이 있으며 후속 Reg A 전환은 보장 없는 '관심'에 불과함 [A9][A32]
- 10년간 취소 불가 의결권 위임, 희석방지 권리 없음, 전환 조건 미공개 전환사채로 인한 희석 가능성 [A7][A8][A19][B2]

**중요한 누락 정보**

- 월별 지출(번레이트)과 최신 런웨이 산정 자료
- 전환사채의 전환가격·상한·할인과 유동성 이벤트 정의
- 회사 헌장·정관 (배당, 청산 조건)
- 대차대조표 1주와 75,000,001주의 불일치 조정 내용
- 마우스 연구 상세, IRB·FDA 진행 문서, 플랫폼 딜 페이지와 모집 진행 여부

**결론을 바꿀 수 있는 것**

- 최신 검증된 현금과 월별 지출, 창업자 대여금 상환 조건, 구속력 있는 추가 자금 약정이 제시되면 재무 항목이 달라질 수 있습니다.
- 헌장상 배당·청산 조건, 구속력 있는 유동성 경로, 실제 매수자나 2차 거래 수단이 문서로 확인되면 현금화 경로 항목이 달라질 수 있습니다.
- 의결권 위임의 완화·종료와 전환사채의 구체적 전환 조건, 풀 다일루티드 지분표가 공개되면 투자자 권리 항목이 달라질 수 있습니다.
- 마우스 연구 상세와 독립 보고서, IRB·FDA 진행 문서, 클리닉·유통 계약이 나오면 수요 관련 항목의 판단이 달라질 수 있습니다.

**다음 조치**

1. 추가 자료 수집은 우선순위가 낮습니다. 결정적 사유가 유지되는 한 결론은 바뀌지 않습니다.
2. 결론을 다시 보려면, 결정적 사유(BT4_financial_condition_and_funding, PC1_security_cash_path, PC3_investor_rights_and_dilution)의 인용 원문을 직접 확인하는 것이 첫 단계입니다.

