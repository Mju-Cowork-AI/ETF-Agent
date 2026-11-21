# ETF-Agent: ETF 질의응답 챗봇

> **배포된 서비스(리허설, 샘플 데이터, 최종 URL은 11-28 제출 전 확정):** <https://etf-agent.pages.dev>
>
> API: <https://ca-etf-agent-api.wittyrock-5cacb91d.koreacentral.azurecontainerapps.io> · 구성과 배포 절차는 [infra/azure/README.md](infra/azure/README.md)
>
> AI가 생성한 답변이며 투자 조언이 아닙니다. 수치는 기준일 데이터입니다.

<!-- 스크린샷: 배포 후 docs/images/에 넣고 아래 주석을 풉니다 -->
<!-- ![서비스 화면](docs/images/screenshot_main.png) -->
<!-- ![검증 과정 보기](docs/images/screenshot_guard.png) -->

## 서비스 개요

코멘토 명지대 AI 2조의 팀 프로젝트입니다. 국내 ETF에 대해 물으면 **조회한 근거(ETF DB와 문서)로만** 답하고, **준법 검증을 통과한 답만** 보여 주는 챗봇입니다.

- **할 수 있는 일:** ETF 상품 정보 조회(총보수·실부담비용·순자산·구성종목 등), ETF 비교, ETF 개념·용어 설명, 투자 권유·전망 요청에 대한 안전한 안내
- **에이전트 구조:** LLM이 질문을 보고 어떤 도구(ETF DB 조회, 문서 검색)를 쓸지 계획합니다. 결과가 부족하면 한 번 더 계획하고, 답을 쓴 뒤 다른 LLM이 검증합니다. 반복 횟수와 안전 경계는 코드가 제한합니다.
- **설계 원칙:** LLM은 숫자를 만들지 않습니다. 수치는 DB에서만 가져오고, 기준일과 투자 고지는 코드가 붙입니다.
- **기술 스택:** Python, FastAPI, LangGraph, Postgres(pgvector), React, Docker, Azure OpenAI
- **배포:** API는 **Azure Container Apps**(최소 복제본 1), 웹은 **Cloudflare Pages**, DB는 **Azure Database for PostgreSQL** flexible server(B1ms). 키는 Azure Key Vault에 둡니다([docs/decisions.md](docs/decisions.md) D9)
- **배경:** LLM 기반 ETF 질의응답 챗봇 구축 RFP를 바탕으로 합니다. 자세한 기획은 [docs/plan.md](docs/plan.md)에 있습니다.

## 팀원별 역할

| 역할 | 이름 | 맡은 일 |
|---|---|---|
| AI Solutions Architect | | 아키텍처·재계획 루프 설계, 외부 호출 전 개인정보 차단, 가드레일 기준, 레드팀·정상 질문 평가셋, 일정·범위 관리, README |
| AI Engineer | | 에이전트 그래프(계획·재계획·합성·검증), 숫자 대조, 프롬프트, Azure 모델 연결, 평가 실행 운영 |
| Cloud Engineer | | 저장소 관리, 배포·시크릿, 하루 질문 상한, 예산 알림·사용량 모니터링, 평가 실행 환경(배포 URL·키) 지원, 사용자 테스트 진행 |
| Data Scientist | | ETF 데이터 수집·검증·적재, 문서 검색(RAG) 색인·튜닝, 일반 평가셋 정답값 |

역할별 상세는 [docs/roles.md](docs/roles.md)에 있습니다.

## 로컬 실행 방법 (FastAPI 기반)

### 빠른 시작

Docker와 Compose v2.24 이상이 필요합니다. 테스트·린트에는 [uv](https://docs.astral.sh/uv/)와 Node.js 24가 추가로 필요합니다.

#### API 키 없이 실행

```bash
./scripts/run-fake.sh
```

스크립트가 `.env`를 준비하고 DB·API·웹을 실행한 뒤 마이그레이션, 샘플 데이터 및 문서 적재를 수행합니다. fake 모델의 답변은 실제 모델의 품질을 나타내지 않습니다.

- 웹: <http://localhost:5173> — 이메일로 개발용 로그인
- API 문서: <http://localhost:8000/docs>
- 운영 화면: `admin@local.test`로 로그인 후 **운영** 탭 선택
- 종료: `./scripts/run-fake.sh down` (데이터 볼륨 유지)

#### 실제 모델로 실행

```bash
cp .env.local.example .env.local
# .env.local의 LLM_API_KEY 주석을 해제하고 API 키 입력
./scripts/run-local.sh
```

- Azure 엔드포인트·키·배포 이름은 Key Vault에서 받습니다(키 관리자: Cloud Engineer). 보관 규칙은 [docs/dev-guide.md](docs/dev-guide.md) 6장. **키는 절대 커밋하지 않습니다.**

기본 모델은 `gpt-5.4-nano`, 임베딩은 `text-embedding-3-small`(1024차원)입니다. 질문과 검색된 문서 일부가 모델 제공자에게 전송됩니다. `.env.local.example`은 로컬 일반 대화 모드를 켭니다. 끄려면 `.env.local`에서 `GENERAL_CHAT_ENABLED=false`로 설정하세요.

설정 변경 후 `./scripts/run-local.sh`를 다시 실행합니다. 로그는 `./scripts/run-local.sh logs`, 종료는 `./scripts/run-local.sh down`으로 확인하거나 실행할 수 있습니다. fake와 실제 임베딩을 전환할 때는 해당 실행 스크립트로 문서를 다시 적재하세요. 스크립트는 샘플 문서만 다시 임베딩하므로 운영 화면에서 올린 문서는 다시 업로드해야 합니다.

### 자주 쓰는 명령

```bash
make setup                       # 호스트 테스트·린트 의존성 설치
make test                        # API 테스트 (실행 중인 DB 필요)
make lint                        # Ruff, ESLint, Prettier, TypeScript 검사
make demo PROVIDER=fake          # 예제 질문 실행
make eval PROVIDER=fake          # 평가 리포트
make restart                     # API 재시작 (데이터 갱신 후 캐시 비우기)
make logs                        # API 로그
make down                        # 컨테이너 종료, 볼륨 유지
```

테스트는 `TEST_DATABASE_URL` 또는 `POSTGRES_*`로 지정한 서버에 별도의 `_test` DB를 만들며, **같은 이름의 기존 테스트 DB를 삭제하고 다시 생성합니다**. 실행 전에 대상 서버를 확인하세요.

직접 스택을 관리할 때는 `make up`, `make migrate`, `make seed`, `make ingest`를 사용합니다. `make ingest ARGS="data/samples/docs --force"`는 문서를 강제로 재적재합니다. 경로는 레포 루트 기준 상대 경로(컨테이너 안에서는 `/workspace` 아래)로 주며, 없는 경로면 오류로 끝납니다. `make help`에서 전체 명령을 볼 수 있습니다.

> **데이터를 갱신한 뒤에는 `make restart`로 API를 재시작하세요.** `make seed`, `make ingest`는 API와 다른 프로세스에서 실행되어 API의 메모리 캐시를 비우지 못합니다. 재시작하지 않으면 이전 FAQ 답변·시세는 최대 1시간, ETF 정보는 최대 1일 동안 그대로 나올 수 있습니다. 실행 스크립트(`run-fake.sh`, `run-local.sh`)로 처음 띄울 때와 운영 화면에서 문서를 업로드할 때는 필요 없습니다.

### 설정

실행 스크립트는 비어 있는 `.env` 설정을 채웁니다. `.env.local`이 있으면 같은 이름의 `.env` 값을 덮으며, `run-fake.sh`로 실행할 때도 읽힙니다(모델·임베딩 공급자만 fake로 바뀝니다). API 컨테이너에는 두 파일의 값이 들어가므로 API 설정은 파일에서 바꾸세요. API 설정 가운데 셸 환경변수로 덮을 수 있는 것은 `LLM_PROVIDER`, `EMBEDDING_PROVIDER`(또는 `make up PROVIDER=fake`)뿐입니다. compose와 Makefile이 직접 읽는 `POSTGRES_*`, `TEST_DATABASE_URL`, `VITE_*`는 셸 환경변수가 우선합니다. 설정의 전체 목록과 설명은 [`.env.example`](.env.example), 기본값과 검증 규칙은 [`settings.py`](apps/api/app/settings.py)를 참고하세요.

| 설정 | 용도 |
| --- | --- |
| `DATABASE_URL`, `POSTGRES_*` | PostgreSQL 연결 및 로컬 DB 설정 |
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` | 생성 모델 설정 (`fake` 또는 `openai_compat`) |
| `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_DIM` | 임베딩 설정. DB 벡터 컬럼 차원은 마이그레이션할 때의 `EMBEDDING_DIM`(기본 1024)으로 정해지므로 이후에는 바꾸지 않음 |
| `GENERAL_CHAT_ENABLED` | 일반 대화 활성화. `APP_ENV=local`에서만 허용 |
| `DAILY_QUESTION_LIMIT` | 하루 질문 상한(D13). 서비스 전체가 하루(한국 시간)에 받는 질문 수이며 기본 0(끔). 넘으면 LLM 호출 없이 안내 문구로 끝나고, 카운트는 DB에 있어 재시작해도 유지 |
| `ADMIN_EMAILS`, `LOCAL_JWT_SECRET` | 개발용 관리자 이메일과 JWT 서명 키. 관리자 역할은 로그인할 때 토큰에 담기므로 목록 변경은 다시 로그인한 뒤 반영 |
| `ANON_ACCESS_ENABLED`, `VITE_AUTH_MODE=anonymous` | 로그인 없는 접근(공개 URL). 브라우저마다 익명 사용자를 발급하고, 설명 수준은 채팅 화면 버튼으로 고름(기본 입문). 기본은 꺼짐 |
| `ADMIN_AUTH=token`, `ADMIN_TOKEN` | 공개 URL의 운영 화면 보호. 팀원은 주소 끝에 `#admin`을 붙여 운영 토큰을 넣음 |
| `METRICS_TOKEN` | `/metrics` 수집용 Bearer 토큰. 비우면 `APP_ENV=local`에서만 열림 |

### API

인증이 필요한 API는 개발용 로그인이나 익명 발급으로 받은 JWT를 사용합니다. 상세 요청·응답은 실행 후 `/docs`에서 확인할 수 있습니다.

| 경로 | 기능 |
| --- | --- |
| `GET /health`, `GET /metrics` | 상태 확인과 Prometheus 메트릭(`METRICS_TOKEN` 설정 시 Bearer 토큰 필요) |
| `POST /auth/dev-login`, `GET/PATCH /auth/me` | 로컬 로그인과 설명 수준 설정 |
| `POST /auth/anonymous` | 로그인 없는 접근용 익명 사용자·토큰(30일) 발급. `ANON_ACCESS_ENABLED=true`일 때만 열림 |
| `POST /chat` | 채팅 SSE (`status` → `token` → `sources` → `done`). 질문을 저장하지 못하거나 답변 작업이 예기치 않게 중단되면 `done` 없이 `error`로 끝남 |
| `GET/DELETE /history`, `GET/DELETE /history/{id}` | 대화 조회·삭제 |
| `POST /feedback` | 좋아요·싫어요·정정 피드백 |
| `/admin/traces`, `/admin/feedback`, `/admin/documents`, `/admin/search` | 관리자 전용 운영 API(`ADMIN_AUTH=token`이면 `X-Admin-Token` 헤더 필요) |

대화를 삭제하면 메시지도 삭제되지만 피드백과 트레이스는 남습니다. 대화 내용은 저장 전 개인정보 패턴을 마스킹하며, 트레이스에는 질문 원문을 저장하지 않도록 구성되어 있습니다.

### 현재 범위와 배포

로컬 실행이 중심인 MVP입니다. 배포는 API는 Azure Container Apps(최소 복제본 1), 웹은 Cloudflare Pages, DB는 Azure Database for PostgreSQL flexible server(B1ms)에 둡니다([docs/decisions.md](docs/decisions.md) D9). 공개 URL은 로그인 없는 접근(`ANON_ACCESS_ENABLED=true`, `VITE_AUTH_MODE=anonymous`, `ADMIN_AUTH=token`)으로 엽니다. 하루 질문 수 상한(`DAILY_QUESTION_LIMIT`, D13)은 서비스 전체 하루 질문 수로 셉니다. 실제 로그인 수단 및 Supabase/Entra 인증, Supabase·Azure Blob 저장소, Cloudflare Access, Langfuse 어댑터는 아직 구현이 필요합니다. 구현 전인 인증·저장소를 고르면 해당 요청이 501로 응답하고, Langfuse 트레이서를 고르면 API가 기동하지 않습니다. 자세한 구성은 [Azure 안내](infra/azure/README.md)를 참고하세요.

가드의 검증 모델을 호출하지 못하거나 판정 결과를 두 번 연속 해석하지 못하면 답변을 내보내지 않고 안전 답변으로 대체합니다. 캐시는 프로세스별 메모리에 있으므로 별도 프로세스의 데이터 적재나 다른 API 인스턴스에 캐시 삭제가 전파되지 않습니다. 로컬에서는 `make restart`로 해결하고, API 인스턴스를 여러 개 띄우는 배포에서는 공유 캐시(Redis 등)가 필요합니다.

### 실행할 때 주의할 점

- **Windows:** `make`와 bash 스크립트를 쓰므로 **WSL2** 안에서 실행합니다.
- **Docker Compose v2.24 이상**이 필요합니다(`docker compose version`으로 확인).
- **포트 충돌:** 로컬 Postgres가 5432 포트를 쓰고 있으면 충돌합니다. `.env`의 `POSTGRES_PORT`를 다른 값으로 바꿉니다.
- **`make test`:** DB가 떠 있어야 하고, `_test`로 끝나는 테스트 DB를 지우고 다시 만듭니다.
- **데이터 갱신 뒤:** `make seed`, `make ingest` 다음에는 **`make restart`**를 실행합니다. 안 하면 캐시 때문에 이전 값이 나옵니다.
- **Azure 연결:** `LLM_MODEL`에는 모델 이름이 아니라 **배포 이름**을 넣고, base URL은 **`/openai/v1/`로 끝나야** 합니다.

## 폴더 구조

| 폴더 | 용도 |
|---|---|
| `apps/api/` | FastAPI 서버: 에이전트, LLM 호출 모듈(`app/llm`), 문서 검색, 저장소, 마이그레이션, 테스트 |
| `apps/web/` | React 채팅·운영 화면 |
| `jobs/` | 샘플 시드, 문서 적재, 외부 데이터 수집 |
| `ml/` | 오프라인 평가(`make eval`) |
| `prompts/` | 시스템 프롬프트, 가드 규칙, 답변 템플릿 |
| `data/` | 샘플 데이터와 평가 데이터셋 (`data/raw/` 원본은 커밋 안 함) |
| `infra/` | 로컬 Docker와 배포 설정 예시 |
| `scripts/` | 실행 스크립트, 개발 환경 준비, 키 등록 |
| `docs/` | 문서 |

## 팀 규칙과 문서

| 문서 | 내용 |
|---|---|
| [docs/git-flow.md](docs/git-flow.md) | 처음이라면: 브랜치 만들기부터 머지까지 따라 하는 Git 작업 흐름 |
| [docs/dev-guide.md](docs/dev-guide.md) | 전체 규칙: 로컬 환경, 브랜치·커밋 타입, PR(승인 필수 PR 포함), 릴리스, API 키, CI |
| [docs/team_rules.md](docs/team_rules.md) | 팀이 더한 규칙: 옮겨 온 코드 리뷰, 커밋 금지 파일, 테스트, 크레딧, 데이터, 개인정보 |
| [docs/plan.md](docs/plan.md) | 통합 기획서(목표·범위, 아키텍처, 데이터, 안전장치, 평가, 일정, 위험) |
| [docs/decisions.md](docs/decisions.md) | 결정 기록(결정됨 / 결정 필요) |
| [docs/decision_board.md](docs/decision_board.md) | 채팅방 결정 안건(결정 방식·주도 역할·기한) |
| [docs/roles.md](docs/roles.md) | 역할별 할 일과 날짜별 완료 기준 |
| [CLAUDE.md](CLAUDE.md) | Claude Code 공통 규칙 |
