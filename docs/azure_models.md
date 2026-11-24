# Azure에서 크레딧으로 쓸 수 있는 모델

생성 모델과 검증 모델을 고르기 위한 자료입니다([plan.md](plan.md) 2-5, [decisions.md](decisions.md) D2). 2026-11-18에 Azure CLI로 구독의 모델 목록과 할당량을 조회한 결과입니다.

- **확인한 것:** 리전별 모델 카탈로그, 구독 할당량, 현재 배포, 구독 유형
- **확인하지 못한 것:** 모델별 단가, 한국어 품질, 일부 모델의 과금 경로. 해당 칸에 "확인 필요"로 적었습니다.

## 1. 결론

- 채팅 모델이 여러 개라 **생성과 검증을 모두 Azure 안에서 서로 다른 모델로 둘 수 있습니다.** "채팅 모델이 1개뿐이면 검증을 무료 모델로 분리(+8h)" 조건은 해당하지 않습니다.
- 구독은 **무료 체험이고 지출 한도가 켜져 있습니다.** 크레딧 밖으로 과금되는 모델은 배포가 막히므로, 실수로 요금이 나갈 일은 없습니다.
- **크레딧 적용 여부는 제공사가 아니라 모델별 판매 방식으로 갈립니다**(2장).
- 가장 안전한 선택은 생성과 검증을 모두 Azure OpenAI 모델에서 고르는 것입니다. 다른 제공사를 검증에 쓰려면 `grok-4.7`이 1순위 후보입니다(5장).

## 2. 크레딧이 적용되는 기준

| 판매 방식 | 과금 | 무료 체험 구독 |
|---|---|---|
| Azure 직접 판매 | Azure 사용량으로 과금, 크레딧에서 차감 | 사용 가능 |
| 파트너·커뮤니티(Marketplace) 판매 | Azure Marketplace 구독이 필요 | 배포가 막힐 가능성이 큼(확인 필요) |

- 같은 제공사 안에서도 모델마다 다릅니다. 예: Mistral은 `Mistral-Large-3`가 직접 판매, `Ministral-3B`가 파트너 판매입니다.
- 할당량 숫자가 있다고 크레딧으로 쓸 수 있다는 뜻은 아닙니다. Claude도 할당량은 잡혀 있지만 과금 경로는 별개입니다.
- **확인 방법:** Foundry 포털에서 모델 배포 화면을 엽니다. Marketplace 약관 동의·구독 단계가 뜨면 파트너 판매 모델입니다.

근거: [Azure 직접 판매 모델](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure), [파트너·커뮤니티 모델](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-from-partners), [모델 배포 방법](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/deploy-foundry-models)

## 3. Azure OpenAI 모델 (크레딧 사용 가능)

지금 있는 Azure OpenAI 리소스(koreacentral)에 배포만 추가하면 됩니다. 전부 Azure 직접 판매입니다.

### 현재 배포

| 배포 이름 | 모델 | SKU | 용량 |
|---|---|---|---|
| `gpt-5-mini` | gpt-5-mini (2025-08-07) | GlobalStandard | 100 |
| `text-embedding-3-small` | text-embedding-3-small (1) | GlobalStandard | 100 |
| `gpt-6-sol` | gpt-6-sol (2026-09-22) | GlobalStandard | 50 |
| `gpt-6-luna` | gpt-6-luna (2026-09-22) | GlobalStandard | 50 |

2026-11-24에 Azure CLI로 다시 조회한 결과입니다. `gpt-6-sol`·`gpt-6-luna`는 모델 배치 결정(11-19) 뒤에 추가했습니다. `gpt-5-mini`는 처음부터 있던 배포이고 서비스에서는 쓰지 않습니다.

### 배포 가능한 채팅 모델 (GA, GlobalStandard)

| 계열 | 모델 (버전) | 할당량 한도 |
|---|---|---|
| GPT-6.2 | `gpt-6.2-sol`, `gpt-6.2-astra` (2026-11-17) | 각 1000 |
| GPT-6.1 | `gpt-6.1-sol` (2026-09-29) | 250 |
| GPT-6.1 | `gpt-6.1-terra` (2026-10-26) | 1000 |
| GPT-6 | `gpt-6-sol`, `gpt-6-luna` (2026-09-22), `gpt-6-astra` (2026-09-03) | 각 250 |
| GPT-5.6 | `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna` (2026-07-09) | 각 250 |
| GPT-5.5 | `gpt-5.5` (2026-04-24) | 1000 |
| GPT-5.4 | `gpt-5.4` (2026-03-05) | 250 |
| GPT-5.4 | `gpt-5.4-pro` (2026-03-05) | 160 |
| GPT-5.2, 5.1 | `gpt-5.2` (2025-12-11), `gpt-5.1` (2025-11-13) | 각 250 |
| GPT-5 | `gpt-5` (2025-08-07) | 250 |
| GPT-5 | `gpt-5-pro` (2025-10-06) | 160 |

- `sol`, `terra`, `luna`, `astra`가 각각 어떤 등급인지는 확인하지 못했습니다(확인 필요). "가장 성능 좋은 모델을 생성에"(D2)를 적용하려면 모델 카탈로그 설명을 봐야 합니다.
- `-pro` 계열과 최신 상위 모델은 단가가 높을 수 있습니다. 크레딧이 약 200달러이므로 가격표를 확인한 뒤 정합니다.

### 소형 모델

| 모델 (버전) | 할당량 한도 | 비고 |
|---|---|---|
| `gpt-5.4-mini` (2026-03-17) | 1000 | GA |
| `gpt-5.4-nano` (2026-03-17) | 5000 | GA |
| `gpt-5-mini` (2025-08-07) | 1000 | 배포됨(100 사용 중) |
| `gpt-5-nano` (2025-08-07) | 5000 | GA |

### 임베딩

`text-embedding-3-small`(배포됨), `text-embedding-3-large`, `text-embedding-ada-002`. 한도는 각 1000입니다.

### 후보에서 빼는 것

| 모델 | 이유 |
|---|---|
| `o1`, `o3`, `o3-mini`, `o4-mini` | 2026-11-19 종료 |
| `gpt-4.1` 계열, `gpt-4o` 계열 | Legacy·Deprecating(2027년 1~4월 종료) |
| `gpt-chat-latest` | Preview. 버전이 바뀌어 평가 재현성에 불리 |
| `model-router` | 호출마다 실제 응답 모델이 달라져 "한 실행 안에서 생성 모델 고정"과 맞지 않음 |
| `gpt-5-codex` 등 codex 계열 | 코딩용 |

## 4. 다른 제공사 모델

Azure OpenAI 리소스에서는 OpenAI 모델만 나옵니다. 아래 모델은 **Foundry(AIServices) 리소스를 새로 만들어야** 배포할 수 있습니다. koreacentral, eastus2, swedencentral 세 리전을 조회했습니다.

### 크레딧 사용 가능으로 보는 것 (Azure 직접 판매)

| 제공사 | 모델 | 할당량 | 리전 | 판매 방식 확인 |
|---|---|---|---|---|
| xAI | `grok-4.7` | 80 | 세 리전 모두 | 문서에서 확인 |
| Meta | `Llama-3.3-70B-Instruct` | 20 | 세 리전 모두 | 문서에서 확인 |
| Meta | `Llama-4-Maverick-17B-128E-Instruct-FP8` | 확인 필요 | 세 리전 모두 | 문서에서 확인 |
| DeepSeek | `DeepSeek-V4-Pro`, `DeepSeek-V3.2` | 확인 필요 | 세 리전 모두 | 문서에서 확인 |
| Mistral | `Mistral-Large-3` | 확인 필요 | 세 리전 모두 | 문서에서 확인 |
| Microsoft | `Phi-4`, `Phi-4-reasoning`, `Phi-4-mini-instruct`, `Phi-4-mini-reasoning` | 각 20 | 세 리전 모두 | 계열 분류만 확인, 모델별은 확인 필요 |
| OpenAI 오픈웨이트 | `gpt-oss-120b` | 5000 | 세 리전 모두 | 확인 필요 |

"할당량 확인 필요"는 카탈로그에는 있지만 구독 할당량 항목을 찾지 못한 경우입니다. 할당량이 0인지, 이름이 달라 찾지 못한 것인지는 포털에서 배포를 시도해야 알 수 있습니다.

### 크레딧으로 쓸 수 없을 가능성이 있는 것 (파트너·Marketplace 판매)

| 제공사 | 모델 | 판매 방식 확인 |
|---|---|---|
| Anthropic | Claude 전체(`claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-opus-5-5` 등). eastus2와 swedencentral에만 있음 | 확인 필요 |
| Mistral | `mistral-medium-2505`, `Ministral-3B` | 문서에서 확인 |
| Mistral | `mistral-small-2503`, `Codestral-2501`, `Mistral-large` | 확인 필요 |
| Meta | `Llama-4-Scout-17B-16E-Instruct` | 문서에서 확인 |
| Cohere | `cohere-command-a` | 확인 필요 |

### 판매 방식을 확인하지 못한 것

`DeepSeek-V3.2-Speciale`, `DeepSeek-V4-Flash`, `Kimi-K3.1-Pro`, `qwen3-32b`, `gpt-oss-20b`, `grok-4-1-fast-reasoning`

## 5. 생성·검증 모델 후보

검증 모델은 생성 모델과 달라야 하고, 같은 모델의 배포 두 개는 같은 모델로 봅니다([plan.md](plan.md) 2-5).

### 결정된 배치 (11-19)

| 역할 | 모델(배포 이름) | 배포 환경변수 | 가격(100만 토큰당 입력/출력) |
|---|---|---|---|
| 생성 | `gpt-6-sol` | `LLM_MODEL` | $2 / $10 |
| 계획 | `gpt-6-luna` | `PLAN_MODEL` | $0.1 / $0.5 |
| 검증 | `gpt-6-luna` | `JUDGE_MODEL` | $0.1 / $0.5 |
| 임베딩 | `text-embedding-3-small` | `EMBEDDING_MODEL` | 확인 필요 |

- AI Engineer 추천으로 채팅방에서 정했습니다([decisions.md](decisions.md) "모델 배치"). 가격은 그 결정에 적힌 값입니다.
- 배포 환경변수 값은 2026-11-24에 운영 API(`ca-etf-agent-api`)에서 확인했습니다.
- `gpt-6.2-sol`은 가격 확인 전이라 뺐습니다. 생성과 검증이 같은 GPT 계열이라, 개발용 평가에서 레드팀 위반이 검증을 빠져나가면 검증 모델만 다른 계열로 바꾸기로 했습니다.
- 11-21 리허설 때는 계획도 `gpt-6-sol`이 했습니다([infra/azure/README.md](../infra/azure/README.md) 토큰 표). 그 표의 질문당 비용은 지금 배치보다 조금 높게 나온 값입니다.

### 결정 전에 본 후보 (11-18 자료)

| 역할 | 후보 | 장점 | 확인할 것 |
|---|---|---|---|
| 생성 | GPT-6.2 계열(`gpt-6.2-sol` 또는 `gpt-6.2-astra`) | 지금 리소스에 배포만 추가, 크레딧 적용 확실 | 등급 차이, 단가 |
| 검증(같은 제공사) | `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini` | 추가 리소스 없이 "다른 모델" 조건 충족 | 같은 제공사라 독립성이 약함 |
| 검증(다른 제공사) | `grok-4.7` | 제공사가 달라 같은 오류를 낼 가능성이 낮음. GA, koreacentral 할당량 확인 | Foundry 리소스 생성, 단가, 한국어 판정 품질 |
| 검증(저비용) | `gpt-oss-120b` | 할당량이 가장 넉넉함 | 판매 방식, 한국어 판정 품질 |
| 계획 | `gpt-5.4-mini`, `gpt-5.4-nano` | 소형, 크레딧 적용 확실 | JSON 출력 안정성 |

- 3~4B급 초소형 모델(`Phi-4-mini` 등)을 검증에 쓰려면, 위반 문장 인용을 한국어로 안정적으로 하는지 손 테스트가 먼저 필요합니다.
- Phi-4 계열, `gpt-oss`, Llama는 오픈웨이트라 같은 모델을 로컬에서도 돌릴 수 있습니다. D3(로컬 LLM 실측)는 Ollama의 `exaone3.5:2.4b`·`gemma3:12b`로 계획 단계만 쟀습니다([local_llm.md](local_llm.md)).

## 6. 정하기 전에 확인할 것

모델 배치는 11-19에 정해졌습니다(5장). 아래는 결정 전에 적은 확인 항목과 지금 상태입니다.

| 항목 | 방법 | 상태(11-24) |
|---|---|---|
| 모델별 단가 | Azure 가격표. [plan.md](plan.md) 비용 표의 빈칸을 채움 | 쓰는 두 모델만 확인(sol $2/$10, luna $0.1/$0.5). 임베딩과 나머지 모델은 확인 안 함 |
| GPT-6.x 등급 차이 | Foundry 모델 카탈로그 설명 | 확인 안 함(가격이 확인된 sol·luna로 정함) |
| 다른 제공사 모델의 크레딧 적용 | 포털 배포 화면에서 Marketplace 단계가 뜨는지 확인 | 확인 안 함(검증 모델을 다른 계열로 바꿀 때 확인) |
| 한국어 생성·검증 품질 | 11-21 손 테스트 12문항 | 리허설 12문항 가드 통과([infra/azure/README.md](../infra/azure/README.md)). 품질 수치는 개발용·시험용 평가 결과로 봄 |
| 크레딧 만료 | 무료 체험 크레딧이 끝나면 Azure 모델 호출이 멈춤. 소진 시 무료 모델로 전환([plan.md](plan.md) 위험 표) | 그대로 |
