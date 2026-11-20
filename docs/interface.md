# 모듈 간 입출력 형식

AI Engineer 초안을 확정한 형식입니다(11-19, [decisions.md](decisions.md)). 개인정보 차단·숫자 대조·데이터 파이프라인을 옮겨 올 때와 계획 JSON·재계획 루프를 만들 때 이 형식을 씁니다. 형식을 바꾸려면 이 문서와 decisions.md를 먼저 고칩니다.

## 1. 계획 JSON

```json
{"intents": [...], "tools": [{"name": "etf_info|etf_search|knowledge", "args": {"etf_codes": [...], "metrics": [...], "conditions": {...}}}], "answer_mode": "generate|table", "refuse": [...], "confidence": 0.0, "needs_clarification": false, "clarify_question": null}
```

### 규칙

- **의도 이름:** FastAPI 기반 이름을 그대로 씁니다. 한 질문에 의도를 여러 개 넣을 수 있습니다.
- **되묻기:** `confidence`가 0.6 미만이면 되묻습니다.
- **형식 검사 실패:** 1회 다시 시도하고, 그래도 실패하면 키워드 규칙으로 분류합니다.
- **disclosure:** D5(공시 조회 제외) 결정에 따라 쓰지 않습니다.
- **refuse:** 혼합 질문에서 판단을 요구하는 부분과 범위 밖 부분(공시·뉴스 등)을 거절할 때 씁니다. 섞인 질문은 사실만 답하고 거절 문장을 붙입니다([plan.md](plan.md) 4장 안전장치 4단계, 11-21에 범위 밖 부분까지 넓힘).

## 2. 부족 판정

```json
{"sufficient": false, "reasons": [{"type": "missing_field|zero_results|low_score|unresolved_entity", ...}]}
```
