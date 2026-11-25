# 모듈 간 입출력 형식

AI Engineer 초안을 확정한 형식입니다(11-19, [decisions.md](decisions.md)). 개인정보 차단·숫자 대조·데이터 파이프라인을 옮겨 올 때와 계획 JSON·재계획 루프를 만들 때 이 형식을 씁니다. 형식을 바꾸려면 이 문서와 decisions.md를 먼저 고칩니다.

## 1. 계획 JSON

```json
{"intents": [...], "tools": [{"name": "etf_info|etf_search|knowledge", "args": {"etf_codes": [...], "metrics": [...], "conditions": {...}}}], "answer_mode": "generate|table", "refuse": [...], "confidence": 0.0, "needs_clarification": false, "clarify_question": null}
```

### 규칙

- **의도 이름:** FastAPI 기반 이름을 그대로 씁니다. 한 질문에 의도를 여러 개 넣을 수 있습니다.
- **되묻기:** `confidence`가 0.6 미만이면 `needs_clarification`을 켭니다. 그래프에서는 아직 쓰지 않습니다(아래 구현).
- **형식 검사 실패:** 1회 다시 시도하고, 그래도 실패하면 키워드 규칙으로 분류합니다.
- **disclosure:** D5(공시 조회 제외) 결정에 따라 쓰지 않습니다.
- **refuse:** 혼합 질문에서 판단을 요구하는 부분과 범위 밖 부분(공시·뉴스 등)을 거절할 때 씁니다. 섞인 질문은 사실만 답하고 거절 문장을 붙입니다([plan.md](plan.md) 4장 안전장치 4단계, 11-21에 범위 밖 부분까지 넓힘).

### 구현(11-21, `app/agents/orchestrator`)

- **도구 인자:** `etf_info`는 `etf_codes`(6자리, 최대 3개)·`metrics`, `etf_search`는 `conditions`(`region`·`category`·`underlying_index`·`max_fee`·`min_fee`·`sort`·`sort_desc`), `knowledge`는 `query`. 허용 밖 이름·값은 코드가 버립니다.
- **조건 적용:** 질문 문장 규칙이 찾은 조건이 우선이고, 규칙이 못 찾은 칸만 계획 값으로 채웁니다. DB가 쓰는 값(지역·분류·기초지수 이름·정렬 키)만 받습니다.
- **종목코드:** 질문에서 ETF를 못 찾았을 때만 계획의 `etf_codes` 중 DB에 있는 것을 씁니다.
- **refuse:** 사실 의도(etf_info·faq)와 함께 있을 때만 씁니다. 거절 문장은 `prompts/templates/refusals.yaml`, 답 본문 뒤·고지 앞에 코드가 붙입니다. 규칙이 매수 판단·예측을 잡았는데 계획이 high_risk를 적지 않았으면 예전처럼 고위험 고정 답변으로 갑니다.
- **모델:** `PLAN_MODEL`(배포는 gpt-6-luna, 비우면 `LLM_MODEL`).
- **되묻기·답변 방식:** `needs_clarification`·`clarify_question`·`answer_mode`는 계산만 하고 그래프에서 쓰지 않습니다. 11-25 이후 새 기능 금지라 연결하지 않고 남은 일로 둡니다([arch_check.md](arch_check.md) 2장).

## 2. 부족 판정

```json
{"sufficient": false, "reasons": [{"type": "missing_field|zero_results", ...}]}
```

- **코드가 만드는 사유:** `zero_results`(조건 검색 결과 0건)와 `missing_field`(계획한 지표가 수집 결과에 없음) 2종입니다(`app/agents/sufficiency.py`).
- **`low_score`(문서 점수 낮음)·`unresolved_entity`(ETF 이름 애매):** 11-22 범위 조정 3차로 재계획하지 않고 바로 고정 문구로 처리합니다. 부족 사유로 만들지 않습니다.
