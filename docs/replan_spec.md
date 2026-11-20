# 재계획 루프 설계 명세 (D11: 최대 1회)

AI Engineer 작성(11-20). 형식은 [interface.md](interface.md)의 계획 JSON·부족 판정을 따릅니다. 구현은 11-23~24, 테스트는 mock LLM으로 합니다.

## 1. 흐름

```
orchestrate(계획 JSON) → 병렬 수집(etf_info / etf_search / knowledge) → sufficiency(코드, LLM 0회)
   ├ 충분 → compose
   ├ 부족 & replan_count = 0 → orchestrate(부족 사유 전달) → 추가 수집 → sufficiency
   └ 부족 & replan_count = 1(상한) → 5장 처리
```

- **판정은 코드, 추가 계획은 LLM**이 맡습니다. LLM이 "충분한가"를 정하지 않습니다.
- 재계획해도 **이미 모은 결과는 유지**합니다(`results`는 기존 merge 방식 그대로). 2차 계획의 도구만 추가로 부릅니다.
- 1차와 **같은 도구·같은 인자**는 코드가 빼고 부르지 않습니다(같은 실패 반복 방지).
- 재계획하지 않는 경우: 고정 문구 의도만 있음(차단·고위험·추천·범위 밖), 되묻기(`needs_clarification`), 개인정보 차단.

## 2. 부족 판정 (코드)

| type | 조건 | 사유에 담는 값 |
|---|---|---|
| `missing_field` | 계획한 `metrics` 중 수집 결과에 값이 없는 항목이 있음 | `etf_code`, `field` |
| `zero_results` | `etf_search` 결과 0건 | `tool`, `conditions` |
| `low_score` | `knowledge` 결과가 없거나 최고 점수 < `rag_min_score`(현재 0.25) | `tool`, `query`, `top_score` |
| `unresolved_entity` | ETF가 필요한 의도인데 확정 ETF가 0개이고 퍼지 후보만 있음 | `candidates` |

예: `{"sufficient": false, "reasons": [{"type": "missing_field", "etf_code": "367380", "field": "real_cost"}]}`

## 3. 부족 사유 전달 형식 (2차 계획 입력)

1차 계획 메시지 뒤에 아래 블록을 붙여 같은 계획 모델에 다시 보냅니다. 수집 값 자체는 보내지 않고 **있음/없음만** 요약합니다(토큰 절약, 숫자 생성 여지 차단).

```
[이전 계획] {1차 계획 JSON}
[수집 결과 요약] etf_info 367380: total_expense_ratio 있음, real_cost 없음
[부족 사유] {sufficiency JSON}
[지시] 이미 모은 결과는 유지된다. 부족한 부분을 채울 "추가" 도구와 인자만 같은 JSON 형식으로 내라.
       더 수집할 방법이 없으면 tools를 빈 배열로 내라. 사용자의 조건을 바꾸거나 완화하지 마라.
```

- 출력은 계획 JSON과 같은 형식이고, `tools`에는 **추가분만** 들어갑니다.
- 형식 검사 실패 시 1회 재시도(계획 JSON 규칙과 같음). 그래도 실패하면 재계획 없이 5장 처리로 갑니다.

## 4. 계획 프롬프트 변경점

- 분류 프롬프트(`prompts/system/classifier.md`)를 **계획 프롬프트**로 확장: 도구 목록(`etf_info`·`etf_search`·`knowledge`)과 인자 이름(`etf_codes`·`metrics`·`conditions`·`query`), `answer_mode`·`refuse`·`confidence` 규칙, 예시 3개.
- **재계획 지시 절** 추가(3장의 [지시] 문구). "조건 완화 금지", "같은 도구·인자 반복 금지", "방법이 없으면 빈 배열".
- 모델: 계획·재계획 모두 `PLAN_MODEL`(gpt-6-luna). 설정은 11-23 계획 JSON 작업에서 추가합니다.

## 5. 상한(1회)에 닿았을 때

| 상황 | 처리 | LLM 생성 |
|---|---|---|
| 근거가 일부 있음 | 있는 근거로 compose. 빠진 항목은 **코드가** "○○은 아직 확인되지 않았습니다" 문장을 붙임 | 1회 |
| `zero_results`만 남음 | 고정 문구 "조건에 맞는 ETF가 없습니다" + 조건을 바꿔 다시 물어보라는 안내 | 0회 |
| `unresolved_entity`만 남음 | 후보가 있으면 되묻기("혹시 ○○를 말씀하시나요?"), 없으면 "지원하지 않는 상품" 고정 문구 | 0회 |
| `low_score`만 남음(개념 질문) | 고정 문구 "관련 자료를 찾지 못했습니다" | 0회 |

- 필요한 고정 문구: `templates/no_match.md`, `templates/unsupported_etf.md`, `templates/no_document.md`(새로 만듦).
- **확인 필요:** 지금 코드에는 근거 없이 모델 지식으로 답하는 경로(`grounded=False`)가 있습니다. 상한에 닿은 개념 질문은 이 경로 대신 고정 문구로 끝내는 것으로 제안합니다(근거 인용률 100% 목표).

## 6. 상태·그래프 변경 (구현 메모)

- `GraphState`에 `plan`, `sufficiency`, `replan_count` 추가.
- 노드 `sufficiency` 추가. 수집 노드 → `sufficiency` → `route_sufficiency`가 `compose` 또는 `orchestrate`로 분기.
- 트레이스에 `replanned`(bool), 부족 사유 type 목록 기록 → plan.md 1-3 "재계획 발동률·추가 호출" 지표.
- 비용: 계획 호출 최대 +2회(재시도 포함), 토큰 약 +3,000. 생성 호출은 늘지 않음. 응답 시간 영향은 리허설·개발용 평가에서 확인(p90 10초 목표).

## 7. 테스트 시나리오 5개 (mock LLM)

| # | 질문 | 1차 → 판정 | 2차 계획(mock) | 기대 결과 |
|---|---|---|---|---|
| 1 | ACE 미국나스닥100 실부담비용 알려줘 | `etf_info`(367380, real_cost) → DB 값 없음 → `missing_field` | `knowledge`("ACE 미국나스닥100 실부담비용") | 문서 근거로 compose. 계획 호출 2회, 생성 1회, `replanned=true` |
| 2 | 나스닥 추종 ETF 보수 낮은 순으로 보여줘 | `etf_search`(underlying_index="나스닥") → 0건 → `zero_results` | `etf_search`(underlying_index="NASDAQ-100") | 3개 결과로 표 답변(생성 0회) |
| 3 | 총보수 0.01% 이하 해외 ETF 찾아줘 | `etf_search`(max_fee=0.01) → 0건 → `zero_results` | `tools: []` | 상한 처리: "조건에 맞는 ETF가 없습니다" 고정 문구. 계획 호출 정확히 2회, 3차 계획 없음, 조건 완화 없음 |
| 4 | 타이거 나스닥 보수 얼마야 | 퍼지 후보만(133690) → `unresolved_entity` | `etf_info`(133690, total_expense_ratio) | 표 답변. 2차에서 1차와 같은 도구·인자를 내면 코드가 빼고 상한 처리(되묻기) |
| 5 | KODEX 200 총보수 알려줘 (회귀) | `etf_info`(069500) → 충분 | — | 재계획 없음. 계획 호출 1회, `replanned=false`. 고정 문구 의도("지금 사야 할까?")도 재계획 0회 |