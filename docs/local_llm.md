# D3 로컬 LLM 실측 (계획 단계만)

RFP 참가 자격의 로컬 LLM 항목([rfp_scope.md](rfp_scope.md))에 대한 실측 기록입니다. 측정일은 2026-11-24, 담당은 Cloud Engineer입니다.

## 1. 결론

- **계획(의도 분류) 단계는 환경변수만 바꿔 로컬 모델로 돌릴 수 있습니다.** 코드는 바꾸지 않았습니다(LLM 호출 모듈 `apps/api/app/llm`의 OpenAI 호환 어댑터를 그대로 씀).
- 개발용 일반 20문항에서 `gemma3:12b`는 18/20(90%), 한국어 소형 모델 `exaone3.5:2.4b`는 15/20(75%)였습니다. 두 모델 모두 계획 JSON 형식은 20문항 전부 한 번에 맞췄습니다.
- 소형 모델(2.4b)은 정확도가 **LLM 없이 키워드 규칙만 쓴 값(15/20)과 같아** 계획 모델로 쓸 이유가 없습니다. 12b는 정확도는 쓸 만하지만 문항당 중앙값 5.8초라, 지금 배포의 응답 시간 목표(p90 10초)에는 맞지 않습니다.
- 배포는 그대로 Azure 모델을 씁니다. 이 문서는 "모델을 바꿔 끼울 수 있는 구조"의 근거와 한계를 적은 것입니다.

## 2. 결과

| 계획 모델 | 의도 정확도 | 조회 | 비교 | 개념 | 고위험 | 추천 | 범위 밖 | 응답 시간 중앙값 | p90 | 최대 | 형식 재시도 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 키워드 규칙만(LLM 없음) | 15/20 (75%) | 7/7 | 4/7 | 2/2 | 1/2 | 1/1 | 0/1 | 0초 | 0초 | 0초 | — |
| `exaone3.5:2.4b` (Q4_K_M, 1.6GB) | 15/20 (75%) | 7/7 | 5/7 | 2/2 | 0/2 | 1/1 | 0/1 | 1.8초 | 3.0초 | 3.6초 | 0 |
| `gemma3:12b` (8.1GB) | 18/20 (90%) | 7/7 | 7/7 | 2/2 | 1/2 | 1/1 | 0/1 | 5.8초 | 7.3초 | 11.5초 | 0 |

- 응답 시간은 계획 호출 한 번의 시간입니다(모델을 메모리에 올리는 시간 제외: exaone 1.0초, gemma 6.5초). 각 1회 실행, 온도 0입니다.
- **Azure 계획 모델과의 직접 비교는 하지 않았습니다.** 같은 스크립트로 Azure를 재지 않았습니다(비용 계산·평가 실행은 AI Engineer 담당). 참고 값으로 11-21 리허설의 "질문 유형 파악" 단계가 평균 1.4초였는데, 이 값에는 문서 검색 시간이 함께 들어 있습니다([infra/azure/README.md](../infra/azure/README.md)). Azure의 의도 정확도는 개발용 평가 결과(`make eval`)의 `intent_accuracy`를 봅니다.

### 틀린 문항

| 문항 | 기대 | 규칙만 | exaone3.5:2.4b | gemma3:12b |
| --- | --- | --- | --- | --- |
| gen13 (비교) | etf_info | 정답 | etf_info + faq | 정답 |
| gen14 (비교) | etf_info | 정답 | etf_info + faq | 정답 |
| gen16 (비교) | etf_info | faq | 정답 | 정답 |
| gen17 (비교) | etf_info | faq | 정답 | 정답 |
| gen19 (비교) | etf_info | faq | 정답 | 정답 |
| gen24 (고위험) | high_risk | faq | faq | faq |
| gen26 (고위험) | high_risk | 정답 | etf_info + faq | 정답 |
| gen29 (범위 밖) | out_of_scope | high_risk | high_risk | high_risk |

- **gen29는 모델과 무관합니다.** "사야 할까"가 고위험 규칙에 걸리면 계획이 고위험을 적지 않아도 코드가 고위험으로 고정합니다(`finalize_plan`의 안전장치). Azure 모델에서도 같은 결과가 나올 수 있으니 개발용 평가 결과에서 확인이 필요합니다.
- **gen24는 세 경우 모두 faq**입니다. 고위험 규칙에 걸리지 않는 문장이라 모델이 고위험으로 분류해야 맞는데 둘 다 개념 질문으로 봤습니다.
- **gen26(지금 사야 할까)을 소형 모델이 사실 질문으로 분류**했습니다. 이 경로는 매수 판단 질문에 답을 만들 수 있어, 소형 모델을 계획에 쓰면 가드에만 기대게 됩니다.

## 3. 측정 방법

- **범위:** `app.agents.orchestrator.plan`만 호출합니다(스크립트 `ml/eval/local_plan.py`). 생성·검증·임베딩·DB는 쓰지 않아 Azure 호출이 없습니다(비용 0). 차단·고위험 규칙과 계획 JSON 형식 검사·재시도는 실제 서비스와 같은 코드를 탑니다.
- **문항:** `data/eval-sets/general.jsonl`의 개발용 20문항. 정답은 `expected_intents`와 집합이 같은지로 봅니다. ETF 이름 인식은 DB 대신 `data/real/etf_master.csv`를 씁니다.
- **환경:** Apple M5, 메모리 32GB, Ollama 0.40.16(OpenAI 호환 주소 `/v1`), GPU 100%.
- **재현:** Ollama에 모델을 받은 뒤(`ollama pull exaone3.5:2.4b`) 아래를 실행합니다. `.env`의 Azure 값은 환경변수가 덮어쓰므로 Azure로 나가지 않습니다.

```bash
cd apps/api
M=exaone3.5:2.4b
DATABASE_URL=postgresql+asyncpg://unused LLM_PROVIDER=openai_compat \
  LLM_BASE_URL=http://localhost:11434/v1 LLM_API_KEY=ollama \
  LLM_MODEL=$M PLAN_MODEL=$M FALLBACK_PROVIDER=none \
  OPENAI_MAX_TOKENS_PARAM=max_tokens OPENAI_OMIT_TEMPERATURE=false OPENAI_REASONING_EFFORT=off \
  PYTHONPATH=../.. uv run python -m ml.eval.local_plan --out ../../eval/results/d3_exaone.json

# 비교 기준: LLM 없이 키워드 규칙만
DATABASE_URL=postgresql+asyncpg://unused PYTHONPATH=../.. \
  uv run python -m ml.eval.local_plan --rules-only
```

- 문항별 결과 파일은 `eval/results/`에 두고 커밋하지 않습니다.

## 4. 한계

- **계획 단계만 쟀습니다.** 생성·검증을 로컬 모델로 바꾼 답변 품질은 재지 않았습니다. 지금 구조는 계획·생성·검증이 같은 주소(`LLM_BASE_URL`)를 쓰고 모델 이름만 다르게 주므로, "계획만 로컬, 생성·검증은 Azure"로 서비스를 띄우려면 계획 전용 주소 설정이 하나 더 필요합니다(만들지 않음).
- 의도만 채점했습니다. 도구와 인자(예: 지표, 검색 조건)가 맞는지는 보지 않았습니다. 소형 모델은 개념 질문에서 `knowledge` 도구를 빼먹었습니다(gen21·23).
- 20문항 1회 실행이라 한두 문항 차이는 의미를 두기 어렵습니다.
- `exaone3.5:2.4b`는 Ollama 서버에 `OLLAMA_KV_CACHE_TYPE=q8_0`이 걸려 있으면 뜨지 않습니다(모델 구조와 맞지 않음). 기본값(f16)으로 띄운 서버에서 쟀습니다.
- EXAONE 3.5는 연구용(비상업) 라이선스입니다. 실측에만 썼고 서비스에는 넣지 않습니다.
