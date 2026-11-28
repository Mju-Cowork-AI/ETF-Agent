# 설계 vs 구현 최종 점검 (발표용)

아키텍처 문서와 실제 코드·배포가 맞는지 11-25 최종 점검한 결과입니다. 작성은 AI Solutions Architect이고, 발표 자료의 "설계 vs 구현, 남은 일" 장에 씁니다.

- **기준:** `dev` f9fe0ed(#64까지, 11-25). #60(세금·비ETF 자산 분류, 검색 목록 분배주기, 보장 표현 지시)과 #64를 반영했습니다. #61(가드 대비 설명 예외)은 아직 머지 전이라 넣지 않았습니다. 코드와 문서에서 확인한 사실만 적었고, 확인하지 못한 것은 "확인 필요"로 적었습니다.
- **비교한 문서:** [plan.md](plan.md)(2장 구조·흐름, 4장 안전장치), [README.md](../README.md), [rfp_scope.md](rfp_scope.md), [decisions.md](decisions.md), [interface.md](interface.md), [guard_rules.md](guard_rules.md), [infra/azure/README.md](../infra/azure/README.md)
- **비교한 코드:** `apps/api`(그래프·도구·가드·개인정보 차단·재계획), `apps/web`, `infra/`, `.github/workflows/`, `settings.py`, `.env.example`
- **배포 확인(2026-11-24):** 웹 <https://etf-agent.pages.dev> 응답 200, API `/health` 응답 `{"status":"ok","db":"ok"}`. 키·비밀값은 보지 않았습니다.
- 3장 가운데 AI Solutions Architect 문서(plan.md, interface.md, grading.md, rfp_scope.md, README.md)는 이 PR에서 고쳤습니다. 다른 역할의 문서와 코드는 고치지 않았습니다.

## 1. 실제 동작 경로

질문 하나가 지나가는 경로입니다. 노드 이름은 [`apps/api/app/agents/graph.py`](../apps/api/app/agents/graph.py)의 LangGraph 노드입니다.

| 순서 | 단계 | 노드·파일 | 하는 일 | 외부 호출 |
|---|---|---|---|---|
| 0 | 요청·하루 상한 | `POST /chat` → `services/chat.py` `stream_chat` | 서비스 전체 하루(KST) 질문 수를 DB에서 +1, 넘으면 안내 문구로 끝냄(D13, 배포 값 200). 답은 SSE로 보냄 | 없음 |
| 1 | 개인정보 차단 | `preprocess` → `privacy/__init__.py` `find_pii_to_block` | 원문에서 주민·외국인등록번호·카드·전화·계좌·이메일을 찾으면 바로 `template`(고정 문구)으로 감 | **없음**(LLM·임베딩 전) |
| 1-1 | 정규화·ETF 인식 | `preprocess` → `agents/preprocess` | 정규화, 티커·이름·별칭 인식, 이름 오타는 퍼지 매칭 | 없음 |
| 2 | 계획(JSON) | `orchestrate` → `agents/orchestrator` `plan` | ① 차단 규칙(해킹·불법·지침 무력화)에 걸리면 LLM 없이 `blocked` ② 계획 모델이 의도·도구·인자·`refuse`를 JSON으로 냄, 형식 실패 시 1회 재시도 뒤 키워드 규칙 ③ 매수 판단·세금(세금·과세·양도세 등) 규칙에 걸리면 코드가 고위험으로 고정(`finalize_plan`). 단 계획이 범위 밖만 적었으면 그대로 둠(ETF가 아닌 자산, #60) | 계획 `gpt-6-luna` |
| 2-1 | 문서 선검색(동시) | `orchestrate` → `agents/faq` `retrieve` → `rag/retriever.py` | 계획과 동시에 문서 검색(pgvector, top-k 기본 4) | 임베딩 `text-embedding-3-small` |
| 2-2 | 고정 문구 | `template` → `agents/guard/templates.py`, `prompts/templates/` | 차단·고위험·추천·범위 밖은 생성 없이 고정 문구 | 없음 |
| 3 | 도구(병렬) | `etf_info` → `agents/etf_info`, `tools/etf_search.py`·`compare.py`, `repositories/etf.py` / `faq` → `agents/faq` | DB 조회·조건 검색(표는 코드가 만들고 항목별 기준일을 붙임. 조건 검색 목록에 분배주기 열, #60), 문서 검색 결과 정리. 시세 질문이면 시세 미제공 안내 | 없음(DB) |
| 4 | 충분성 판정 | `sufficiency` → `agents/sufficiency.py` | 결과 0건(`zero_results`)·항목 빠짐(`missing_field`)만 부족으로 봄(11-22 범위 조정 3차) | 없음 |
| 4-1 | 재계획(최대 1회) | `replan` → `agents/orchestrator` `replan` | 부족 사유를 계획 모델에 보내 추가 도구만 받고, 그 수집만 다시 함. 이미 모은 결과는 유지(D11, #47) | 계획 `gpt-6-luna` |
| 5 | 생성 | `compose` → `agents/compose` `synthesize` | 모은 자료로 설명 문장 생성(보장은 부정문으로만 쓰라는 지시 포함, #60). 값 표는 도구가 만든 것을 그대로 붙임. 섞인 질문은 거절 문장(`prompts/templates/refusals.yaml`), 의도별 투자 고지(`prompts/guard/disclaimers.yaml`)를 **코드가** 붙임 | 생성 `gpt-6-sol` |
| 6 | 가드 ① 규칙 | `guard` → `agents/guard/rules.py` `check_rules` | 근거 없는 숫자(숫자 대조: 단위 환산·반올림·상대 오차 5%·날짜), 금지 표현 5범주, 순위 R1~R3, 본문 개인정보, 필수 고지 누락 | 없음 |
| 6-1 | 가드 ② 검증 모델 | `guard` → `agents/guard/judge.py` | 규칙을 통과하고 설명 문장이 있는 답만 근거 대비 판정 | 검증 `gpt-6-luna` |
| 7 | 재작성 / 안전 답변 | `retry` → `compose`(1회) / `safe` → `prompts/templates/safe_answer.md` | 반려되면 합성만 1회 다시. 다시 반려되거나 검증 모델이 판정하지 못하면 안전 답변(고정 문구 + 문의 채널) | 재작성 때 생성 1회 |
| 8 | 저장·기록 | `services/chat.py`, `observability/pg_tracer.py` | 대화는 개인정보 마스킹 뒤 저장, 트레이스(단계별 소요 시간)에는 질문 원문을 남기지 않음 | 없음 |

**배포에서 실제로 쓰는 것**([infra/azure/README.md](../infra/azure/README.md) "리허설 배포 구성", [`containerapp-api.example.yaml`](../infra/azure/containerapp-api.example.yaml))

| 구분 | 실제 |
|---|---|
| 모델 | Azure OpenAI `etf-agent-local-22eaff`(koreacentral): 생성 `gpt-6-sol`, 계획·검증 `gpt-6-luna`, 임베딩 `text-embedding-3-small`(1024차원). 예비 모델 없음(`FALLBACK_PROVIDER=none`) |
| API | Azure Container Apps `ca-etf-agent-api`(koreacentral, 복제본 1개 고정) |
| DB | Azure Database for PostgreSQL flexible server B1ms `pg-etf-agent-japaneast`(Japan East, PostgreSQL 17, pgvector) |
| 웹 | Cloudflare Pages `etf-agent`(<https://etf-agent.pages.dev>) |
| 비밀값 | Key Vault `kv-etf-agent-b084`, 앱은 관리 ID로 읽음 |
| 접근 | 로그인 없이 익명 토큰(`ANON_ACCESS_ENABLED=true`), 운영 화면은 운영 토큰(`ADMIN_AUTH=token`), 하루 상한 200건 |
| 배포 | `main` 머지 시 GitHub Actions [`deploy.yml`](../.github/workflows/deploy.yml)이 API 이미지를 올리고 `/health`를 확인한 뒤 웹을 배포. 설정 작업(마이그레이션·적재)은 수동 실행에서 골랐을 때만 |

## 2. 설계했지만 구현하지 않은 것

- **11-25부터 새 기능 금지라 되묻기·표 모드는 연결하지 않고 "남은 일"로 둡니다.** 계획 JSON에 값은 있지만 그래프는 쓰지 않습니다.

| 항목 | 문서 위치 | 왜 안 했는지 | 남은 일 |
|---|---|---|---|
| 되묻기(계획 `confidence` 0.6 미만이면 되묻기) | [interface.md](interface.md) 1장 "되묻기", [decisions.md](decisions.md) "모듈 간 입출력 형식" | 결정 번호 없음. 계획 JSON에서 `needs_clarification`·`clarify_question`을 계산만 하고 그래프가 쓰지 않음. 재계획 루프 PR(#47)에도 들어가지 않았고, 11-25 이후 새 기능 금지라 연결하지 않음 | 그래프에서 `needs_clarification`이면 `clarify_question`으로 답하게 연결 |
| 표 모드(`answer_mode: table`이면 생성 LLM 0회) | [plan.md](plan.md) 2-1 흐름, 2-6 호출 수("표 모드: 계획만 1~2회") | 결정 번호 없음. `answer_mode`는 계산만 하고 `compose`가 쓰지 않음. 자료가 있으면 설명 문장을 생성함(값 표는 코드가 만듦). 11-25 이후 새 기능 금지라 연결하지 않음 | `answer_mode`가 `table`이면 설명 문장 생성을 건너뛰게 연결(plan.md 2-6은 실제 동작으로 고침) |
| 재계획 조건 4가지 중 2가지(문서 점수 낮음, ETF 이름 애매) | [plan.md](plan.md) 2-3(11-22 반영됨), [interface.md](interface.md) 2장 | 11-22 범위 조정 3차(5h → 3h) | 두 조건을 다시 켬 |
| 공시 조회 | [plan.md](plan.md) 1-2 | D5 제외 | D5 포함안(실데이터 연결 약 8h) |
| 시세 자동 수집(종가·NAV·괴리율·거래량) | [plan.md](plan.md) 3장 | 11-21 범위 조정 2차(공공데이터 API 자동 수집 뺌) | 공식 API 연결 후 숨긴 시세 행을 보여 줌 |
| 투자설명서 색인 | [plan.md](plan.md) 3장 | D6 변경(11-22) | 표 처리 방법을 정한 뒤 색인 |
| 앱 토큰 집계 | [plan.md](plan.md) 1-2 | 11-18 범위 조정 1차(Azure 포털 사용량으로 대신) | — |
| 레드팀 자동 검사·출처 부착률 실행기 연결 | [grading.md](grading.md) 8장 8·9번 | 11-22 범위 조정 3차(채점 때 손으로) | 실행기에 넣음 |
| 익명 발급 반복 호출 제한 | [decisions.md](decisions.md) "익명 토큰·익명 발급" | 11-22 범위 조정 3차(이슈 #18, 넣지 않음) | 로그인 수단을 붙인 뒤 사용자별 상한 |
| 무료 예비 모델 체인 | [plan.md](plan.md) 2-5 "장애 대비(선택)" | D14(선택, 약 41h라 하지 않음). 배포는 `FALLBACK_PROVIDER=none` | 예비 체인을 켜되 검증 모델은 생성 모델과 다르게 |
| 계획만 로컬 모델, 생성·검증은 Azure | [local_llm.md](local_llm.md) 4장 | D3는 계획 단계 실측만(11-24). 계획·생성·검증이 같은 주소(`LLM_BASE_URL`)를 써서 계획 전용 주소 설정이 없음 | 계획 전용 주소 설정 추가 |
| 시연 질문 캐시 | [decisions.md](decisions.md) D10 | 결정됨: 실시간 + 발표 직전 워밍업, 전날 캐시 안 함(11-28, D10) | 없음(11-30 절차는 [infra/azure/README.md](../infra/azure/README.md), #79) |

## 3. 구현했지만 문서에 없거나 문서와 다른 것

| 항목 | 실제 동작 | 고칠 문서 |
|---|---|---|
| 인젝션·해킹 차단 위치 | 문서는 `preprocess`에서 개인정보와 함께 막는다고 그림. 실제로 `preprocess`는 개인정보만 막고, 해킹·불법·지침 무력화는 `orchestrate`의 `plan`에서 규칙으로 먼저 걸러 LLM 없이 `blocked`로 보냄. 차단이면 문서 선검색(임베딩)도 건너뜀 | [plan.md](plan.md) 2-1 흐름도 → **고침(이 PR)** |
| `finalize` 노드 | 문서에는 `finalize`(기준일·고지·거절 문장)가 있지만 그래프에 없음. 고지·거절 문장은 `compose`가 붙이고, 기준일은 도구가 만든 표에 붙음. 가드는 붙인 뒤의 답을 검사함 | [plan.md](plan.md) 2-1 흐름도 → **고침(이 PR)** |
| 안전 답변의 내용 | 문서는 "DB 값 표(LLM 0회)". 실제는 고정 문구(`safe_answer.md`: 답하기 어렵다는 안내 + 문의 채널 + 투자 권유 아님). LLM 0회는 같음 | [plan.md](plan.md) 2-1·4장 3단계, [rfp_scope.md](rfp_scope.md) "오류 대응"·"장애 분류·복구" 행 → **고침(이 PR)** |
| 검증 모델을 부르는 조건 | 문서는 모든 생성 답변을 검증한다고 읽힘. 실제로는 규칙에 걸리면 검증 모델을 부르지 않고 바로 반려, 설명 문장 없이 표·목록만인 답과 일반 대화는 검증하지 않음(`agents/guard/__init__.py`) | [plan.md](plan.md) 2-1, 2-6, 4장 2단계 → **고침(이 PR)** |
| 검증 모델 판정 불가 | 판정하지 못하면 재작성 없이 바로 안전 답변 | [plan.md](plan.md) 2-1(문서와 같음, 확인만) |
| 멀티턴 보정 | ETF 없이 항목만 묻는 후속 질문은 직전 ETF의 정보 질문으로 봄. 직전 답이 차단이면 범위 밖 후속 질문도 계속 차단 | [plan.md](plan.md) 1-2 → **고침(이 PR)** |
| FAQ 답변 캐시 | 가드를 통과한 FAQ 단독 답변을 수준별로 메모리에 캐시하고, 다시 쓸 때 고지만 다시 검사 | [plan.md](plan.md) 2-1 → **고침(이 PR)** |
| 일반 대화 모드 | `GENERAL_CHAT_ENABLED`(로컬 전용)이면 범위 밖 질문을 일반 대화로 답함. 배포에서는 꺼져 있음 | [plan.md](plan.md) 1-2 → **고침(이 PR)**(범위 밖이며 로컬 전용이라고 적음) |
| 부족 판정 사유 종류 | 문서는 4종(`missing_field`·`zero_results`·`low_score`·`unresolved_entity`). 코드는 2종만 만듦 | [interface.md](interface.md) 2장 → **고침(이 PR)** |
| 되묻기 연결 예정 문구 | "재계획 루프 PR에서 연결"이라고 적혀 있으나 #47 뒤에도 연결 안 됨 | [interface.md](interface.md) 1장 → **고침(이 PR)**: 계산만 하고 그래프에서 쓰지 않음, 새 기능 금지로 남은 일 |
| 웹 배포 담당 | infra 문서는 "웹은 Cloud Engineer만 배포할 수 있다". 실제로는 `main` 머지 시 `deploy.yml`이 웹도 배포(#43, 11-24 결정) | [infra/azure/README.md](../infra/azure/README.md) 57행(Cloud Engineer 문서) |
| 지금 배포된 이미지 | infra 문서 12행은 11-22 재배포 기준. 지금 배포된 이미지 태그는 **확인 필요**(자동 배포 뒤 바뀜) | [infra/azure/README.md](../infra/azure/README.md) 12행(Cloud Engineer 문서) |
| `gpt-6-luna` 용도 | 리소스 표는 "`gpt-6-luna`(검증)". 실제는 계획·검증 둘 다(같은 문서 47행은 맞음) | [infra/azure/README.md](../infra/azure/README.md) 20행(Cloud Engineer 문서) |

## 4. 코드에는 있지만 이번 범위에서 쓰지 않는 것

**발표 아키텍처 그림에서는 모두 뺍니다.** 배포 설정에서 켜지 않았거나 구현되지 않은 것입니다.

| 이름 | 위치 | 상태 |
|---|---|---|
| Supabase 인증 | `apps/api/app/auth/supabase_jwt.py` | 미구현(`NotImplementedError`) |
| Entra External ID 인증 | `apps/api/app/auth/entra_jwt.py` | 미구현 |
| Cloudflare Access 인증 | `apps/api/app/auth/cf_access.py` | 미구현 |
| Azure Blob 저장소 | `apps/api/app/storage/azure_blob.py` | 미구현 |
| Supabase 저장소 | `apps/api/app/storage/supabase_storage.py` | 미구현 |
| Langfuse 트레이서 | `apps/api/app/observability/langfuse_tracer.py` | 미구현(고르면 API가 뜨지 않음, README) |
| 공시 수집 노드·도구 | `apps/api/app/agents/disclosure/`, `apps/api/app/tools/disclosure_lookup.py`, `apps/api/app/repositories/disclosures.py` | 그래프에 연결 안 됨(D5) |
| 일반 대화 | `apps/api/app/agents/general/` | 로컬 전용, 배포에서 꺼짐 |
| 예비 모델 라우터 | `apps/api/app/llm/router.py` | 배포 `FALLBACK_PROVIDER=none` |
| 개발용 로그인 | `apps/api/app/auth/local_jwt.py`의 `/auth/dev-login`, `apps/web/src/components/Login.tsx` | 로컬 전용(배포는 익명 접근) |
| MVP 배포 예시(cloudflared 터널) | `infra/mvp/` | 쓰지 않음 |
| vLLM 설정 예시 | `infra/azure/vllm.env.example` | 쓰지 않음 |
| 파인튜닝 | `ml/finetune/`(빈 패키지) | 범위 밖([plan.md](plan.md) 1-2) |

## 5. 발표용 3줄 요약

- **구현된 것:** 질문 → 외부 호출 전 개인정보 차단 → LLM 계획(JSON) → DB·문서 도구 → 부족하면 재계획 1회 → 생성 → 규칙(숫자 대조 포함)과 다른 모델의 검증 → 재작성 1회 또는 안전 답변. 기준일·고지·거절 문장은 코드가 붙이고, Azure(API·DB·모델)와 Cloudflare Pages(웹)에 배포했습니다.
- **의도적으로 뺀 것:** 공시(D5), 시세 자동 수집(11-21), 투자설명서 색인(D6), 재계획 조건 2가지·실행기 자동 검사·익명 발급 제한(11-22), 예비 모델 체인(D14). 로컬 LLM은 계획 단계만 실측했습니다(D3).
- **남은 일:** 되묻기와 표 모드는 계획 JSON에 값만 있고 그래프에 연결하지 않았습니다(11-25 이후 새 기능 금지). 흐름도(plan.md 2-1)는 실제 경로(`finalize` 없음, 안전 답변은 고정 문구, 재계획 조건 2가지)에 맞췄습니다.
