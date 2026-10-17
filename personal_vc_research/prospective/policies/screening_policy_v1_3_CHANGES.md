# screening_policy_v1_3: changes against v1_2 (PROPOSED, not active)

- **File:** `policies/screening_policy_v1_3_PROPOSED.yaml`
- **sha256:** `c150371d0990b86766ce097afd62ac1a982b294996f3de9ef5c09e8fac635e0c`
- **State:** PROPOSED. There is no activation row. P-1 and P-2 remain disabled.
- **v1_2** (`112318fa43f87223a95973fd8638f4a0d03aeb035b9ddb615415fff2d5d8fb32`) is unchanged and superseded.

## What changes against v1_2

- **Rule texts and adverse definitions:** identical, verified programmatically.
- **New `predicates`:** authored elements and their logic for each independent-rejection rule (R-FIN-1, R-TECH-1,
  R-DEM-1, R-REG-1, R-TEAM-1, R-TERMS-1).
- **New `evidence_must_mention`:** a floor on the factual elements.
- **New `compatible_classifiers`:** `[assessment_classifier_v3_1]`. Only analyses classified this way could become
  approval-eligible after activation.
- **New `not_sufficient_alone`** for R-FIN-1: older low cash, going-concern language, an obligation without a stated
  maturity, a planned financing.

## 승인 체크리스트 (한국어)

1. v1_2의 모든 항목에 동의한다(`screening_policy_v1_2_CHANGES.md`).
2. 규칙이 단독 거절 사유가 되려면 다음이 모두 충족되어야 한다.
   - 정해진 요소들이 '확인됨'이어야 한다.
   - 2차 모델 검토가 동의해야 하고, 중대한 미해결 이의가 없어야 한다.
   - 모델이 더 쉬운 기준을 스스로 만들 수 없다.
3. R-FIN-1은 둘 중 하나가 문서로 확인될 때만 단독 거절 사유가 된다.
   - (a) 같은 기간의 수치로 볼 때, 최대 모집액으로도 다음 이정표에 필요한 자금이 부족하다.
   - (b) 채무불이행·지급불능·기한이익상실이 실제로 발생했다.
   - 다음은 그것만으로는 충분하지 않다: 만기 미기재 채무, 계획 중인 노트, 과거의 낮은 현금, 계속기업 문구.
4. 키워드 기준은 최소 조건일 뿐 증명이 아니다. 판단은 모델 해석과 검토에 의존한다(독립 검증 아님).
5. 승인은 사용자가 대화형 터미널에서 해시 앞 12자리를 직접 입력해야만 기록된다.

    python -m prospective policy-activate screening_policy_v1_3 --sha256 c150371d0990b86766ce097afd62ac1a982b294996f3de9ef5c09e8fac635e0c --statement "..." --i-am-the-user

6. 승인하더라도, 이 버전의 분류기(v3_1)와 같은 해시로 분석된 결과만 승인 근거로 쓸 수 있다. 이전 분석에는 소급되지 않는다.
