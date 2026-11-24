# 재계획 루프 설계 명세 (D11: 최대 1회)

AI Engineer 작성(11-20, 리뷰 반영). 형식은 [interface.md](interface.md)의 계획 JSON·부족 판정을 따릅니다. 구현은 11-23~24, 테스트는 mock LLM으로 합니다.

> **범위 조정 3차(11-22 결정, 11-23 반영):** 재계획하는 부족은 **결과 0건(`zero_results`)·항목 빠짐(`missing_field`) 2가지**만입니다. ETF 이름 애매(`unresolved_entity`)·문서 점수 낮음(`low_score`)은 재계획 없이 **바로 고정 문구**로 끝납니다. 아래 표와 시나리오는 이 기준으로 고쳤습니다. 구현: `app/agents/sufficiency.py`, `graph.py`의 `sufficiency`·`replan` 노드, `orchestrator.replan()`, 테스트 `tests/test_replan.py`.

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

| type | 조건 | 사유에 담는 값 | 처리(범위 조정 3차) |
|---|---|---|---|
| `missing_field` | 계획한 `metrics` 중 DB 값이 없는 항목이 있음 | `etf_code`, `field` | **재계획** |
| `zero_results` | 조건 검색 결과 0건. 계획이 조건 검색(`etf_search`)을 골랐는데 조건을 하나도 알아듣지 못한 경우 포함('나스닥' → DB 표기 'NASDAQ 100') | `tool`, `conditions` | **재계획** |
| `low_score` | `knowledge` 결과가 없거나 최고 점수 < `rag_min_score`(현재 0.25) | — | 재계획 없음 → "제공된 자료로는 답하기 어렵습니다" |
| `unresolved_entity` | ETF가 필요한 의도인데 ETF를 확정하지 못함(조건 검색도 아님) | — | 재계획 없음 → "상품명이나 종목코드를 알려 주세요" 안내 |

- 계획이 키워드 규칙으로 대체된 경우(LLM 형식 2회 실패)는 재계획하지 않습니다. 같은 모델을 다시 불러도 실패할 가능성이 커서입니다.

예: `{"sufficient": false, "reasons": [{"type": "missing_field", "etf_code": "367380", "field": "tracking_error"}]}`

## 3. 부족 사유 전달 형식 (2차 계획 입력)

1차 계획 메시지 뒤에 아래 블록을 붙여 같은 계획 모델에 다시 보냅니다. 수집 값 자체는 보내지 않고 **있음/없음만** 요약합니다(토큰 절약, 숫자 생성 여지 차단).

```
[이전 계획] {1차 계획의 intents·tools}
[수집 결과 요약] etf_info 367380: net_assets 없음 / etf_search: 결과 0건
[부족 사유] {sufficiency JSON}
[DB 기초지수 이름] KOSPI 200, NASDAQ 100, …  (이름을 DB 표기로 맞춰 쓸 수 있게)
[지시] 이미 모은 결과는 유지된다. 부족한 부분을 채울 "추가" 도구와 인자만 같은 JSON 형식으로 내라.
       더 수집할 방법이 없으면 tools를 빈 배열로 내라. 사용자의 조건을 바꾸거나 완화하지 마라.
```

- 출력은 계획 JSON과 같은 형식이고, `tools`에는 **추가분만** 들어갑니다.
- 재계획 조건은 **빈 칸만 채웁니다**(`merge_plan_conditions`). 질문에서 읽은 보수 상한·하한·지역은 바뀌지 않으므로, 모델이 조건을 넓혀 내도 완화되지 않습니다.
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
| ETF 이름 애매 | (재계획 없음) ETF 정보의 "상품명이나 종목코드를 알려 주세요" 안내 | 0회 |
| 문서 점수 낮음(개념 질문) | (재계획 없음) "제공된 자료로는 답하기 어렵습니다" | 0회 |

- 고정 문구는 새로 만들지 않고 이미 있는 안내 문장을 씁니다(범위 조정 3차). 빠진 항목은 표에 "-"로 보입니다.
- **결정(11-20 리뷰):** 상한에 닿은 개념 질문은 근거 없이 모델 지식으로 답하는 경로(`grounded=False`) 대신 고정 문구로 끝냅니다(근거 인용률 100% 목표).
  - 과잉 차단 확인: 11-24 개발용 평가에서 `no_document`로 끝난 정상 질문 수를 셉니다. 많으면 근거 없는 답을 허용하지 않고 `rag_min_score`나 문서 쪽을 손봅니다.

## 6. 상태·그래프 변경 (구현 메모)

- `GraphState`에 `plan_tools`, `plan_metrics`, `sufficiency`, `replan_count`, `replan_conditions`, `knowledge_query`, `replan_targets` 추가.
- 노드 `sufficiency`·`replan` 추가. 수집 노드 → `sufficiency` → `route_sufficiency`가 `compose` 또는 `replan`으로 분기 → `replan`은 추가 도구가 가리키는 수집 노드만 다시 부르고(없으면 `compose`), 다시 `sufficiency`를 거쳐 `compose`로 갑니다.
- 트레이스: 재계획하면 에이전트 목록(`agents_called`)에 `replan`이 남습니다(운영 화면 "에이전트" 열). 로그에 `insufficient`·`replan` 이벤트(부족 사유 type, 추가 도구 이름)를 남깁니다. DB 스키마는 바꾸지 않았습니다.
- **2차 수집이 문서에서 가져온 경우**(시나리오 1): 문서 근거는 FAQ와 같은 방식으로 출처가 붙고, 숫자는 가드 숫자 대조를 똑같이 거칩니다.
- 비용: 계획 호출 최대 +2회(재시도 포함), 토큰 약 +3,000. 생성 호출은 늘지 않음. 응답 시간 영향은 리허설·개발용 평가에서 확인(p90 10초 목표).

## 7. 테스트 시나리오 6개 (mock LLM, `tests/test_replan.py`)

재계획하는 2가지(missing_field 1, zero_results 2·3·6)와 재계획하지 않는 경우(4, 5)를 확인합니다. 테스트 DB는 샘플 데이터입니다(실부담비용·순자산이 비어 있음).

| # | 질문 | 1차 → 판정 | 2차 계획(mock) | 기대 결과 |
|---|---|---|---|---|
| 1 | 샘플 코스피200 실부담비용 알려줘 | `etf_info`(metrics: actual_expense_ratio) → DB에 값 없음 → `missing_field` | `knowledge`("실부담비용 뜻") | 표 + 문서 근거로 compose. 계획 호출 2회, 의도에 faq 추가 |
| 2 | 나스닥 추종하는 상품들 목록 보여줘 | `etf_search`(조건 없음) → 조건을 못 알아들음 → `zero_results` | `etf_search`(underlying_index="NASDAQ-100") | 2차 검색으로 결과 표, 가드 통과. 수집 2회 |
| 3 | 총보수 0.001% 이하 ETF 찾아줘 | `etf_search`(max_fee=0.001) → 0건 → `zero_results` | `tools: []` 또는 max_fee=0.5(완화 시도) | "조건에 맞는 ETF가 없습니다". 계획 호출 정확히 2회, 완화 무시 |
| 4 | 그 나슥닥 거 보수 얼마야 | ETF 못 찾음(조건 검색 아님) | — | 재계획 없음. 계획 호출 1회, 상품명 안내 |
| 5 | 샘플 코스피200 총보수 알려줘 (회귀) | 충분 | — | 재계획 없음. 고정 문구 의도("지금 사야 할까?")도 재계획 없음 |
| 6 | 총보수 0.001% 이하 ETF 찾아줘 | `zero_results` | 1차와 같은 도구·인자 | 코드가 빼고 같은 검색을 다시 돌리지 않음. 계획 호출 2회 |

그 밖에: 재계획 입력에 부족 사유·DB 기초지수 이름이 들어가고 수집 값은 들어가지 않는지, 규칙으로 대체된 계획은 재계획하지 않는지, 상한(1회)에 닿으면 compose로 가는지 단위 테스트로 확인합니다.
