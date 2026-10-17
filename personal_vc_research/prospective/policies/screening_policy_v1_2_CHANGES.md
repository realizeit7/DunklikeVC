# screening_policy_v1_2: proposed changes and approval checklist

- **File:** `policies/screening_policy_v1_2_PROPOSED.yaml`
- **sha256:** `112318fa43f87223a95973fd8638f4a0d03aeb035b9ddb615415fff2d5d8fb32`
- **State:** **PROPOSED, NOT ACTIVE.** `python -m prospective policy-status` shows the state. No activation row
  exists.
- **Effect of acceptance.** If you accept, v1_2 becomes the policy for v3 screening results. Until then:
  - every v3 result is labelled "제안된 정책에 따른 잠정 분류";
  - `ledger.approve` refuses any analysis screened under a non-active policy;
  - approvals still need `screening_policy_v1` acknowledged, which has not happened either.
- **Withdrawn proposal.** v1_1 (`screening_policy_v1_1_PROPOSED.md`, never acknowledged) is withdrawn in favour of
  v1_2. Its file is kept unchanged as a record.

## Diff against what exists

| Topic | v1 (used by code, unacknowledged) | v1_1 (proposed, withdrawn) | **v1_2 (proposed)** |
|---|---|---|---|
| Structure | 3 gates with prose bullets; no rule IDs | 8 criteria BT1–5, PC1–3 | 9 rules (R-EV1, R-TECH-1, R-DEM-1, R-REG-1, R-TEAM-1, R-FIN-1, R-TERMS-1/2/3), 2 optional preferences, 3 execution constraints |
| Evidence dimensions | Mixed ("regulatory progress" counted as demand) | Mixed (BT2 text unchanged) | Six separate dimensions. Preclinical efficacy can never be demand evidence (validator rule). |
| What can reject | Any gate-2/3 fail | Any "supported" criterion fail | Only rules marked `independent_rejection: true` whose adverse definition is met by a company-specific, support-checked fact; or a breach of an **enabled** preference |
| Generic early-stage facts | Not addressed | A label-level guard (bypassed in practice) | Fact-level guard G1–G8, applied by model tag **plus** keyword and date rules. These facts can never decide alone, but they stay visible as contributing concerns. |
| Financing | "dated cash position, liabilities and burn" | same | R-FIN-1: cash against next milestones, same-period spending, committed financing and the maximum raise; adverse only on documented inability or default |
| Rights and liquidity | "what usually prevents that" | same | R-TERMS-1: only terms worse than the ordinary Reg CF form. R-TERMS-3 (dilution/priority) cannot reject on its own; missing terms are unknown. |
| Price | "price relative to the path to value" | same | R-TERMS-2: a joint judgment that cannot reject on its own; arithmetic stays separate from judgment |
| Personal preferences | None | None | P-1 (maximum implied pre-money), P-2 (maximum proxy term). **Both disabled**; you would have to enable them and set the parameter. |
| Execution and budget | Mixed into evidence (fees, availability) | Separate dimensions | X-1 availability, X-2 investor fees ("unknown ≠ zero ≠ over budget"), X-3 budget policy v1 **unchanged** |
| Outcome labels | passes / fails / needs_information | fails / passes / indeterminate | provisional_reject / provisional_unresolved / provisional_eligible_for_review. The "provisional_" prefix disappears only after activation. |
| Evidence status | — | "sufficient" (unscoped) | Scoped: "sufficient only for <decision> under <version>"; never "diligence complete" |
| Economic thesis | — | — | Seven questions, including SCHG. "No substantiated advantage identified" is a valid answer and is not "proven inferior". |

## 승인 체크리스트 (한국어)

승인하려면 아래 항목을 모두 읽고 동의해야 합니다. 동의하지 않는 항목이 있으면 승인하지 말고 수정을 요청하세요.

1. 이 정책은 검증되지 않은 연구용 점검표이며, 수익을 예측하거나 SCHG보다 나은 선택을 보장하지 않는다.
2. 다음 사실은 그것만으로는 거절 사유가 되지 않는다. 다만 우려 요인으로는 계속 표시된다.
   - 매출 전 단계
   - 과거 재무제표의 낮은 현금
   - 계속기업 관련 공시
   - 배당·환매·IPO 약속 없음
   - 희석방지권 없음
   - 소수 지분·일반적 비유동성
   - '임의' 가격 공시
   - 의결권 부재 또는 의결권 위임
3. 단독 거절은 다음 두 경우에만 가능하다.
   - 회사 고유의, 문서로 확인되고, 근거 지지 점검을 통과한 불리한 사실이 있을 때
   - 내가 직접 켠 개인 기준(P-1, P-2)을 위반했을 때
4. 개인 기준 P-1(내재 기업가치 상한)과 P-2(의결권 위임 기간 상한)는 꺼져 있다. 켜려면 값을 정해 정책 파일을 바꿔야 하며, 바뀐 파일은 새 해시로 다시 승인해야 한다.
5. 투자자 수수료를 모르면 총비용을 확인할 수 없다. 이는 수수료가 0이라는 뜻도, 예산 초과라는 뜻도 아니다.
6. 예산 정책(연 $12,000, 발행사당 평생 $1,200, 투자자 수수료 포함)은 바뀌지 않는다.
7. 승인 명령은 내가 직접 실행한다. AI는 이 명령을 실행하지 않는다.

    python -m prospective policy-activate screening_policy_v1_2 --sha256 112318fa43f87223a95973fd8638f4a0d03aeb035b9ddb615415fff2d5d8fb32 --i-am-the-user --statement "..."

8. 파일이 한 글자라도 바뀌면 승인은 무효가 되고, 상태는 다시 '제안'으로 돌아간다.
